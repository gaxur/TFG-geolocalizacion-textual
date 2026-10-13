import json
import math
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from shapely import LineString, Point, Polygon

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.crs import wgs84_to_epsg25830
from src.tfg_phase0.f3_geometry import (
    GEOMETRY_POLICY,
    F3GeometryError,
    geometry_software_versions,
    normalize_osm_geometries,
    _normalize_way,
    validate_geometry_runtime,
)
from src.tfg_phase0.f3_inputs import (
    OSMInventory,
    OSMNodeInput,
    OSMWayInput,
    load_d049_rules,
    load_verified_f3_inputs,
)
from src.tfg_phase0.osm_snapshot import (
    build_overpass_query,
    build_snapshot_provenance,
    publish_snapshot,
    validate_osm_xml,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "f3" / "geometry_cases.json"
INPUT_OSM = ROOT / "tests" / "fixtures" / "f3" / "inputs" / "source.osm"
RULES_PATH = ROOT / "third_party" / "osm-polygon-features" / "v0.9.2" / "polygon-features.json"


class Phase3GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.nodes = tuple(OSMNodeInput(
            osm_id=item["osm_id"],
            latitude=item["latitude"],
            longitude=item["longitude"],
            tags=tuple(tuple(tag) for tag in item["tags"]),
            source_role=item["source_role"],
        ) for item in fixture["nodes"])
        cls.ways = {
            item["osm_id"]: OSMWayInput(
                osm_id=item["osm_id"],
                ordered_node_refs=tuple(item["ordered_node_refs"]),
                tags=tuple(tuple(tag) for tag in item["tags"]),
            )
            for item in fixture["ways"]
        }
        cls.nodes_by_id = {node.osm_id: node for node in cls.nodes}
        cls.rules = load_d049_rules(RULES_PATH)

    def normalize(self, osm_id):
        return _normalize_way(
            self.ways[osm_id], nodes_by_id=self.nodes_by_id, rules=self.rules
        )

    @staticmethod
    def inputs(inventory, rules):
        class Inputs:
            pass
        result = Inputs()
        result.inventory = inventory
        result.rules = rules
        return result

    def test_runtime_versions_are_fixed(self):
        validate_geometry_runtime()
        self.assertEqual(dict(geometry_software_versions()), {
            "numpy_version": "2.5.4",
            "shapely_version": "2.1.2",
            "geos_version": "3.13.1",
        })

    def test_runtime_mismatch_is_rejected(self):
        with patch("src.tfg_phase0.f3_geometry.F3_SHAPELY_VERSION", "0.0.0"):
            with self.assertRaises(F3GeometryError):
                validate_geometry_runtime()

    def test_projection_reuses_f1_transformation(self):
        inventory = normalize_osm_geometries(self.inputs(
            OSMInventory(nodes=(self.nodes[0],), ways=(), relations=()), self.rules
        ))
        self.assertEqual(
            inventory.objects[0].geometry.coords[0],
            wgs84_to_epsg25830(self.nodes[0].latitude, self.nodes[0].longitude),
        )

    def test_node_roles(self):
        inventory = normalize_osm_geometries(self.inputs(
            OSMInventory(nodes=(self.nodes[0], self.nodes[4]), ways=(), relations=()),
            self.rules,
        ))
        node_bbox, added = inventory.objects
        self.assertIsInstance(node_bbox.geometry, Point)
        self.assertTrue(node_bbox.associable)
        self.assertIsInstance(added.geometry, Point)
        self.assertFalse(added.associable)
        self.assertEqual(
            added.geometry_reason, "added_way_node_direct_association_forbidden"
        )
        self.assertEqual(node_bbox.tags, (("name", "inside"),))

    def test_open_and_closed_line(self):
        opened = self.normalize(100)
        closed_by_area_no = self.normalize(104)
        closed_by_table = self.normalize(113)
        self.assertIsInstance(opened.geometry, LineString)
        self.assertFalse(opened.is_closed)
        self.assertEqual(
            tuple(opened.geometry.coords),
            tuple(
                wgs84_to_epsg25830(
                    self.nodes_by_id[ref].latitude,
                    self.nodes_by_id[ref].longitude,
                )
                for ref in self.ways[100].ordered_node_refs
            ),
        )
        self.assertIsInstance(closed_by_area_no.geometry, LineString)
        self.assertTrue(closed_by_area_no.is_closed)
        self.assertIsInstance(closed_by_table.geometry, LineString)
        self.assertTrue(closed_by_table.is_closed)

    def test_valid_polygon_and_area_yes(self):
        for osm_id in (101, 102):
            result = self.normalize(osm_id)
            self.assertIsInstance(result.geometry, Polygon)
            self.assertEqual(result.geometry_role, "area")
            self.assertTrue(result.geometry.is_valid)
            self.assertGreater(result.geometry.area, 0)
        self.assertEqual(
            tuple(self.normalize(101).geometry.exterior.coords),
            tuple(
                wgs84_to_epsg25830(
                    self.nodes_by_id[ref].latitude,
                    self.nodes_by_id[ref].longitude,
                )
                for ref in self.ways[101].ordered_node_refs
            ),
        )

    def test_open_area_yes_is_invalid(self):
        result = self.normalize(103)
        self.assertEqual(result.geometry_reason, "invalid_area_open_way")
        self.assertIsNone(result.geometry)

    def test_unknown_and_conflicting_closed_ways(self):
        no_votes = self.normalize(105)
        conflict = self.normalize(106)
        unknown_area = self.normalize(112)
        self.assertEqual(no_votes.geometry_reason, "unknown_closed_way_no_votes")
        self.assertEqual(conflict.geometry_reason, "unknown_closed_way_conflict")
        self.assertEqual(
            unknown_area.geometry_reason,
            "unknown_closed_way_unrecognized_area_value",
        )
        self.assertTrue(all(item.geometry is None for item in (no_votes, conflict, unknown_area)))

    def test_open_unrecognized_area_value_preserves_diagnostic(self):
        result = self.normalize(115)
        self.assertEqual(result.geometry_status, "valid")
        self.assertEqual(result.geometry_role, "line")
        self.assertIsNone(result.geometry_reason)
        self.assertEqual(result.classification_diagnostic, "unrecognized_area_value")

    def test_d049_rule_semantics(self):
        expected = {
            116: ("area", "valid", None),  # whitelist included
            117: ("line", "valid", None),  # blacklist excluded
            118: ("area", "valid", None),  # blacklist non-excluded
            119: ("none", "not_associable", "unknown_closed_way_no_votes"),
            120: ("none", "not_associable", "unknown_closed_way_no_votes"),
            121: ("area", "valid", None),  # multiple equal votes
        }
        for osm_id, classification in expected.items():
            with self.subTest(osm_id=osm_id):
                result = self.normalize(osm_id)
                self.assertEqual(
                    (result.geometry_role, result.geometry_status, result.geometry_reason),
                    classification,
                )

    def test_invalid_polygon_is_not_repaired(self):
        result = self.normalize(107)
        self.assertEqual(result.geometry_reason, "invalid_area_invalid_polygon")
        self.assertIsNone(result.geometry)

    def test_zero_area_and_empty_polygon_branches(self):
        zero = self.normalize(114)
        self.assertEqual(zero.geometry_reason, "invalid_area_non_positive")
        with patch("src.tfg_phase0.f3_geometry.Polygon", return_value=Polygon()):
            empty = self.normalize(102)
        self.assertEqual(empty.geometry_reason, "invalid_area_empty")

    def test_missing_node_too_few_and_non_finite(self):
        self.assertEqual(
            self.normalize(108).geometry_reason,
            "invalid_way_geometry_too_few_positions",
        )
        self.assertEqual(
            self.normalize(110).geometry_reason,
            "invalid_way_geometry_missing_node",
        )
        invalid_node = OSMNodeInput(99, math.nan, -3.7, (), "node_bbox")
        way = OSMWayInput(200, (99, 1), (("highway", "service"),))
        result = _normalize_way(
            way, nodes_by_id={**self.nodes_by_id, 99: invalid_node}, rules=self.rules
        )
        self.assertEqual(
            result.geometry_reason, "invalid_way_geometry_non_finite_coordinate"
        )
        for osm_id in (103, 107, 108, 109, 110, 114):
            with self.subTest(osm_id=osm_id):
                self.assertFalse(self.normalize(osm_id).associable)

    def test_repeated_internal_node_can_remain_valid(self):
        result = self.normalize(111)
        self.assertEqual(result.geometry_status, "valid")
        self.assertIsInstance(result.geometry, LineString)

    def test_classification_is_independent_of_rule_iteration_order(self):
        reversed_rules = type(self.rules)(
            path=self.rules.path,
            size_bytes=self.rules.size_bytes,
            sha256=self.rules.sha256,
            policy=self.rules.policy,
            release=self.rules.release,
            commit=self.rules.commit,
            rules=tuple(reversed(self.rules.rules)),
        )
        for osm_id in (101, 104, 105, 106, 113):
            expected = self.normalize(osm_id)
            actual = _normalize_way(
                self.ways[osm_id],
                nodes_by_id=self.nodes_by_id,
                rules=reversed_rules,
            )
            self.assertEqual(
                (actual.geometry_role, actual.geometry_status, actual.geometry_reason),
                (expected.geometry_role, expected.geometry_status, expected.geometry_reason),
            )

    def test_order_and_relations_are_preserved_without_geometry(self):
        relation = type("Relation", (), {"osm_id": 300})()
        inventory = normalize_osm_geometries(self.inputs(OSMInventory(
            nodes=(self.nodes[1], self.nodes[0]),
            ways=(self.ways[101], self.ways[100]),
            relations=(relation,),
        ), self.rules))
        self.assertEqual(
            tuple((item.osm_type, item.osm_id) for item in inventory.objects),
            (("node", 1), ("node", 2), ("way", 100), ("way", 101)),
        )
        self.assertEqual(inventory.relations, (relation,))
        self.assertFalse(hasattr(inventory.relations[0], "geometry"))
        self.assertEqual(inventory.geometry_policy, GEOMETRY_POLICY)

    def test_normalization_is_deterministic(self):
        original_inputs = self.inputs(OSMInventory(
            nodes=self.nodes,
            ways=tuple(self.ways.values()),
            relations=(),
        ), self.rules)
        reversed_inputs = self.inputs(OSMInventory(
            nodes=tuple(reversed(self.nodes)),
            ways=tuple(reversed(tuple(self.ways.values()))),
            relations=(),
        ), self.rules)
        first = normalize_osm_geometries(original_inputs)
        second = normalize_osm_geometries(reversed_inputs)
        self.assertEqual(
            tuple(
                (
                    item.osm_type,
                    item.osm_id,
                    item.tags,
                    item.geometry_role,
                    item.geometry_status,
                    item.geometry_reason,
                    item.classification_diagnostic,
                    item.metric_bbox,
                )
                for item in first.objects
            ),
            tuple(
                (
                    item.osm_type,
                    item.osm_id,
                    item.tags,
                    item.geometry_role,
                    item.geometry_status,
                    item.geometry_reason,
                    item.classification_diagnostic,
                    item.metric_bbox,
                )
                for item in second.objects
            ),
        )
        self.assertEqual(
            tuple(None if item.geometry is None else item.geometry.wkb for item in first.objects),
            tuple(None if item.geometry is None else item.geometry.wkb for item in second.objects),
        )

    def test_integration_from_verified_f32_inputs(self):
        config = load_region_config(ROOT / "config" / "madrid.yaml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            write_manifest(build_catalog(config, spacing_m=50), manifest_path)
            raw = INPUT_OSM.read_bytes()
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
                raw_part=part,
                snapshots_root=root / "snapshots",
                provenance=provenance,
            )
            inputs = load_verified_f3_inputs(
                manifest_path=manifest_path,
                snapshot_dir=snapshot_dir,
                config_path=ROOT / "config" / "madrid.yaml",
                rules_path=RULES_PATH,
            )
            normalized = normalize_osm_geometries(inputs)
            self.assertEqual(len(normalized.objects), 3)
            self.assertEqual(len(normalized.relations), 2)
            self.assertEqual(normalized.shapely_version, "2.1.2")
            self.assertEqual(normalized.geos_version, "3.13.1")


if __name__ == "__main__":
    unittest.main()
