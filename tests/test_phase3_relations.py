import json
import tempfile
import unittest
import copy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import jsonschema
from shapely import LineString, Point, Polygon

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f3_associations import (
    CandidateAssociationInventory,
    CandidateOSMAssociation,
    associate_candidates_with_osm,
)
from src.tfg_phase0.f3_geometry import (
    GEOMETRY_POLICY,
    MetricBBox,
    NormalizedGeometryInventory,
    NormalizedOSMObject,
    normalize_osm_geometries,
)
from src.tfg_phase0.f3_inputs import (
    OSMInventory,
    OSMMemberInput,
    OSMNodeInput,
    OSMRelationInput,
    VerifiedF3Inputs,
    load_d049_rules,
    load_verified_f3_inputs,
)
from src.tfg_phase0.f3_relations import F3RelationError, build_relation_context
from src.tfg_phase0.osm_snapshot import (
    build_overpass_query,
    build_snapshot_provenance,
    publish_snapshot,
    validate_osm_xml,
)
from src.tfg_phase0.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "third_party/osm-polygon-features/v0.9.2/polygon-features.json"
SOURCE = ROOT / "tests/fixtures/f3/inputs/source.osm"
SCHEMA = json.loads((ROOT / "schemas/f3_relation_context.schema.json").read_text())


def node(osm_id, role="node_bbox"):
    return OSMNodeInput(osm_id, 40.4168, -3.7038, (("name", f"node-{osm_id}"),), role)


def relation(osm_id, members=(), tags=()):
    return OSMRelationInput(osm_id, tuple(tags), tuple(members))


def member(kind, ref, role="", present=True):
    return OSMMemberInput(kind, ref, role, present)


def normalized_object(osm_id, osm_type="node", associable=True):
    geometry = (
        Point(osm_id, osm_id)
        if osm_type == "node"
        else LineString(((osm_id, osm_id), (osm_id + 1, osm_id + 1)))
    )
    return NormalizedOSMObject(
        osm_type=osm_type,
        osm_id=osm_id,
        osm_ref=f"{osm_type}/{osm_id}",
        tags=(("name", f"{osm_type}-{osm_id}"),) if osm_type == "node" else (),
        source_role="node_bbox" if osm_type == "node" else "way_bbox_intersection",
        geometry_role="point" if osm_type == "node" else ("line" if associable else "none"),
        geometry_status="valid" if associable else "not_associable",
        geometry_reason=None if associable else "unknown_closed_way_no_votes",
        classification_diagnostic=None,
        is_closed=None if osm_type == "node" else True,
        metric_bbox=MetricBBox(*geometry.bounds) if associable else None,
        geometry=geometry if associable else None,
    )


def association(candidate_id, osm_id, osm_type="node", role=None):
    geometry_role = role or ("point" if osm_type == "node" else "line")
    return CandidateOSMAssociation(
        candidate_id, osm_type, osm_id, f"{osm_type}/{osm_id}", geometry_role,
        True, False, True, False, False, False, False, 0.0,
    )


def make_inputs(candidates, nodes, ways, relations):
    catalog = SimpleNamespace(candidates=tuple(SimpleNamespace(candidate_id=value) for value in candidates))
    return SimpleNamespace(
        catalog=catalog,
        inventory=OSMInventory(tuple(nodes), tuple(ways), tuple(relations)),
    )


def make_normalized(objects, relations):
    return NormalizedGeometryInventory(
        tuple(objects), tuple(relations), "2.1.2", "3.13.1", GEOMETRY_POLICY
    )


def make_associations(rows, candidate_count, indexed_object_count):
    return CandidateAssociationInventory(tuple(rows), candidate_count, indexed_object_count)


def document(row):
    result = asdict(row)
    result["tags"] = dict(row.tags)
    result["associated_members"] = list(result["associated_members"])
    for item in result["associated_members"]:
        item["candidate_ids"] = list(item["candidate_ids"])
    return result


class Phase3RelationTests(unittest.TestCase):
    def test_propagates_node_and_way_and_preserves_tags_roles(self):
        nodes = (node(1),)
        ways = (SimpleNamespace(osm_id=10, tags=()),)
        relations = (relation(20, (
            member("way", 10, "vía"), member("node", 1, ""),
        ), (("type", "ruta"), ("name", "Águila"))),)
        inputs = make_inputs(("C2", "C1"), nodes, ways, relations)
        normalized = make_normalized(
            (normalized_object(10, "way"), normalized_object(1)), relations
        )
        associations = make_associations(
            (association("C2", 10, "way"), association("C1", 1)), 2, 2
        )
        result = build_relation_context(inputs, normalized, associations)
        row = result.relations[0]
        self.assertEqual(row.tags, (("name", "Águila"), ("type", "ruta")))
        self.assertEqual(
            tuple((item.member_type, item.member_id, item.role, item.candidate_ids) for item in row.associated_members),
            (("node", 1, "", ("C1",)), ("way", 10, "vía", ("C2",))),
        )

    def test_multiple_candidates_and_multiple_parent_relations(self):
        nodes = (node(1),)
        relations = (
            relation(30, (member("node", 1),)),
            relation(20, (member("node", 1),)),
        )
        inputs = make_inputs(("C2", "C1"), nodes, (), relations)
        normalized = make_normalized((normalized_object(1),), tuple(reversed(relations)))
        associations = make_associations(
            (association("C2", 1), association("C1", 1)), 2, 1
        )
        result = build_relation_context(inputs, normalized, associations)
        self.assertEqual(tuple(item.relation_id for item in result.relations), (20, 30))
        self.assertTrue(all(item.associated_members[0].candidate_ids == ("C1", "C2") for item in result.relations))

    def test_counts_absent_unassociated_and_relation_members_without_propagating(self):
        nodes = (node(1), node(2, "added_way_node"))
        child = relation(20, (member("node", 1),))
        parent = relation(21, (
            member("node", 2), member("node", 999, present=False),
            member("relation", 20), member("relation", 999, present=False),
        ))
        inputs = make_inputs(("C1",), nodes, (), (parent, child))
        normalized = make_normalized(
            (normalized_object(1), replace(normalized_object(2), source_role="added_way_node", geometry_status="not_associable", geometry_reason="added_way_node_direct_association_forbidden")),
            (child, parent),
        )
        associations = make_associations((association("C1", 1),), 1, 1)
        result = build_relation_context(inputs, normalized, associations)
        self.assertEqual(tuple(item.relation_id for item in result.relations), (20,))
        self.assertEqual(result.relations_without_associated_members, 1)
        self.assertEqual(asdict(result.present_member_counts), {"node": 2, "way": 0, "relation": 1})
        self.assertEqual(asdict(result.unresolved_member_counts), {"node": 1, "way": 0, "relation": 1})

    def test_empty_relations_and_relation_without_members(self):
        inputs = make_inputs((), (), (), ())
        result = build_relation_context(inputs, make_normalized((), ()), make_associations((), 0, 0))
        self.assertEqual(result.relations, ())
        self.assertEqual(result.relations_input, 0)
        empty_relation = relation(1)
        result = build_relation_context(
            make_inputs((), (), (), (empty_relation,)),
            make_normalized((), (empty_relation,)),
            make_associations((), 0, 0),
        )
        self.assertEqual(result.relations, ())
        self.assertEqual(result.relations_without_associated_members, 1)

    def test_duplicate_members_are_grouped_but_all_entries_are_counted(self):
        nodes = (node(1),)
        relations = (relation(20, (
            member("node", 1, "same"), member("node", 1, "same"),
            member("node", 1, "other"),
        )),)
        result = build_relation_context(
            make_inputs(("C1",), nodes, (), relations),
            make_normalized((normalized_object(1),), relations),
            make_associations((association("C1", 1),), 1, 1),
        )
        row = result.relations[0]
        self.assertEqual(row.member_count, 3)
        self.assertEqual(row.present_member_counts.node, 3)
        self.assertEqual(len(row.associated_members), 2)
        self.assertEqual(tuple(item.role for item in row.associated_members), ("other", "same"))
        self.assertEqual(result.duplicate_members_grouped, 1)

    def test_output_is_schema_compatible_and_deterministic(self):
        nodes = (node(2), node(1))
        relations = (relation(20, (member("node", 2), member("node", 1))),)
        inputs = make_inputs(("C2", "C1"), nodes, (), relations)
        normalized = make_normalized((normalized_object(2), normalized_object(1)), relations)
        association_rows = (association("C2", 2), association("C1", 1))
        first = build_relation_context(
            inputs, normalized, make_associations(association_rows, 2, 2)
        )
        second = build_relation_context(
            inputs, normalized, make_associations(tuple(reversed(association_rows)), 2, 2)
        )
        self.assertEqual(first, second)
        row = document(first.relations[0])
        jsonschema.validate(row, SCHEMA)
        validate_document(row, "f3_relation_context")

    def test_inputs_remain_unchanged(self):
        nodes = (node(1),)
        relations = (relation(20, (member("node", 1),)),)
        inputs = make_inputs(("C1",), nodes, (), relations)
        normalized = make_normalized((normalized_object(1),), relations)
        associations = make_associations((association("C1", 1),), 1, 1)
        before = copy.deepcopy((inputs.inventory, normalized, associations))
        build_relation_context(inputs, normalized, associations)
        self.assertEqual((inputs.inventory, normalized, associations), before)

    def test_rejects_duplicate_unknown_or_incoherent_associations(self):
        nodes = (node(1),)
        relations = (relation(20, (member("node", 1),)),)
        inputs = make_inputs(("C1",), nodes, (), relations)
        normalized = make_normalized((normalized_object(1),), relations)
        valid = association("C1", 1)
        variants = (
            make_associations((valid, valid), 1, 1),
            make_associations((replace(valid, candidate_id="missing"),), 1, 1),
            make_associations((replace(valid, osm_id=2, osm_ref="node/2"),), 1, 1),
            make_associations((replace(valid, osm_ref="node/2"),), 1, 1),
            make_associations((replace(valid, geometry_role="line"),), 1, 1),
        )
        for associations in variants:
            with self.subTest(associations=associations), self.assertRaises(F3RelationError):
                build_relation_context(inputs, normalized, associations)

    def test_rejects_non_associable_objects_and_mismatched_inventories(self):
        nodes = (node(1),)
        relations = (relation(20, (member("node", 1),)),)
        inputs = make_inputs(("C1",), nodes, (), relations)
        not_associable = replace(
            normalized_object(1), geometry_status="not_associable",
            geometry_reason="added_way_node_direct_association_forbidden",
        )
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs,
                make_normalized((not_associable,), relations),
                make_associations((association("C1", 1),), 1, 0),
            )
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs,
                make_normalized((not_associable,), relations),
                make_associations((), 1, 0),
            )
        wrong_added_reason = replace(
            normalized_object(1), source_role="added_way_node",
            geometry_status="not_associable",
            geometry_reason="unknown_closed_way_no_votes",
        )
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs(("C1",), (node(1, "added_way_node"),), (), relations),
                make_normalized((wrong_added_reason,), relations),
                make_associations((), 1, 0),
            )
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs,
                make_normalized((normalized_object(1),), (relation(21),)),
                make_associations((association("C1", 1),), 1, 1),
            )
        wrong_role = replace(normalized_object(1), source_role="added_way_node")
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs,
                make_normalized((wrong_role,), relations),
                make_associations((association("C1", 1),), 1, 1),
            )
        invalid_geometry_role = replace(normalized_object(1), geometry_role="line")
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs,
                make_normalized((invalid_geometry_role,), relations),
                make_associations((replace(association("C1", 1), geometry_role="line"),), 1, 1),
            )
        invalid_bbox = replace(normalized_object(1), metric_bbox=None)
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs,
                make_normalized((invalid_bbox,), relations),
                make_associations((), 1, 1),
            )
        area_geometry = Polygon(((0, 0), (1, 0), (1, 1), (0, 0)))
        open_area = replace(
            normalized_object(1, "way"),
            geometry_role="area",
            is_closed=False,
            geometry=area_geometry,
            metric_bbox=MetricBBox(*area_geometry.bounds),
        )
        way_inputs = make_inputs(("C1",), (), (SimpleNamespace(osm_id=1, tags=()),), relations)
        with self.assertRaises(F3RelationError):
            build_relation_context(
                way_inputs,
                make_normalized((open_area,), relations),
                make_associations((), 1, 1),
            )
        wrong_version = replace(
            make_normalized((normalized_object(1),), relations),
            shapely_version="0.0.0",
        )
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs, wrong_version,
                make_associations((association("C1", 1),), 1, 1),
            )

    def test_rejects_incoherent_association_counts_and_predicates(self):
        nodes = (node(1),)
        relations = (relation(20, (member("node", 1),)),)
        inputs = make_inputs(("C1",), nodes, (), relations)
        normalized = make_normalized((normalized_object(1),), relations)
        valid = association("C1", 1)
        variants = (
            make_associations((valid,), 2, 1),
            make_associations((valid,), 1, 0),
            make_associations((replace(valid, contains=1),), 1, 1),
            make_associations((replace(valid, touches=True, boundary_contact_only=False),), 1, 1),
            make_associations((replace(valid, center_distance_m=float("inf")),), 1, 1),
        )
        for associations in variants:
            with self.subTest(associations=associations), self.assertRaises(F3RelationError):
                build_relation_context(inputs, normalized, associations)

    def test_rejects_invalid_relation_member_and_duplicate_relation_id(self):
        nodes = (node(1),)
        bad_relation = relation(20, (member("invalid", 1),))
        inputs = make_inputs((), nodes, (), (bad_relation,))
        with self.assertRaises(F3RelationError):
            build_relation_context(
                inputs, make_normalized((normalized_object(1),), (bad_relation,)),
                make_associations((), 0, 1),
            )
        duplicate = relation(20)
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs((), (), (), (duplicate, duplicate)),
                make_normalized((), (duplicate, duplicate)),
                make_associations((), 0, 0),
            )
        invalid_id = relation(0)
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs((), (), (), (invalid_id,)),
                make_normalized((), (invalid_id,)),
                make_associations((), 0, 0),
            )

    def test_rejects_incoherent_presence_candidate_ids_and_tags(self):
        nodes = (node(1),)
        wrong_presence = relation(20, (member("node", 1, present=False),))
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs((), nodes, (), (wrong_presence,)),
                make_normalized((normalized_object(1),), (wrong_presence,)),
                make_associations((), 0, 1),
            )

        relations = (relation(20, (member("node", 1),)),)
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs(("",), nodes, (), relations),
                make_normalized((normalized_object(1),), relations),
                make_associations((), 1, 1),
            )

        invalid_tags = (relation(20, (member("node", 1),), (("name", 1),)),)
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs((), nodes, (), invalid_tags),
                make_normalized((normalized_object(1),), invalid_tags),
                make_associations((), 0, 1),
            )

    def test_rejects_boolean_source_and_association_ids(self):
        invalid_node = node(True)
        relations = (relation(20, (member("node", 1),)),)
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs(("C1",), (invalid_node,), (), relations),
                make_normalized((normalized_object(1),), relations),
                make_associations((association("C1", 1),), 1, 1),
            )

        nodes = (node(1),)
        invalid_association = replace(
            association("C1", 1), osm_id=True, osm_ref="node/True"
        )
        with self.assertRaises(F3RelationError):
            build_relation_context(
                make_inputs(("C1",), nodes, (), relations),
                make_normalized((normalized_object(1),), relations),
                make_associations((invalid_association,), 1, 1),
            )

    def test_integration_full_pipeline_does_not_propagate_subrelations(self):
        config = load_region_config(ROOT / "config/madrid.yaml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            write_manifest(build_catalog(config, spacing_m=50), manifest_path)
            raw = SOURCE.read_bytes()
            counts = validate_osm_xml(raw, len(raw), config["region"]["bbox"])
            provenance = build_snapshot_provenance(
                config=config,
                query=build_overpass_query(config["region"]["bbox"], 60),
                raw=raw,
                counts=counts,
                acquired_at=datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc),
                attempts=1,
                http_status=200,
                content_type="application/xml",
            )
            part = root / "source.part"
            part.write_bytes(raw)
            snapshot_dir, _ = publish_snapshot(
                raw_part=part, snapshots_root=root / "snapshots", provenance=provenance
            )
            inputs = load_verified_f3_inputs(
                manifest_path=manifest_path,
                snapshot_dir=snapshot_dir,
                config_path=ROOT / "config/madrid.yaml",
                rules_path=RULES,
            )
            normalized = normalize_osm_geometries(inputs)
            associations = associate_candidates_with_osm(inputs.catalog, normalized)
            result = build_relation_context(inputs, normalized, associations)
            self.assertEqual(tuple(item.relation_id for item in result.relations), (20,))
            row = result.relations[0]
            self.assertEqual(row.associated_members[0].member_ref, "way/10")
            self.assertEqual(row.associated_members[0].role, "local")
            self.assertEqual(row.present_member_counts.way, 1)
            self.assertEqual(row.unresolved_member_counts.way, 1)
            self.assertEqual(row.unresolved_member_counts.node, 1)
            self.assertEqual(row.unresolved_member_counts.relation, 1)
            self.assertFalse(hasattr(row, "geometry"))
            jsonschema.validate(document(row), SCHEMA)


if __name__ == "__main__":
    unittest.main()
