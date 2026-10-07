import copy
import json
import math
import unittest
from pathlib import Path

import jsonschema

from src.tfg_phase0.f3_contracts import (
    F3_GEOMETRY_REASONS,
    F3_IDENTITY_SOFTWARE_FIELDS,
    F3_INVALID_REASONS,
    F3_NOT_ASSOCIABLE_REASONS,
    F3_PROVENANCE_ONLY_SOFTWARE_FIELDS,
)
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "f3"
SCHEMAS = ROOT / "schemas"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def assert_rejected(test_case, document, schema_name):
    with test_case.assertRaises(SchemaValidationError):
        validate_document(document, schema_name)


class Phase3ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objects = load_fixture("osm_objects.json")
        cls.associations = load_fixture("associations.json")
        cls.relation = load_fixture("relation_context.json")
        cls.provenance = load_fixture("provenance.json")
        cls.schemas = {
            name: json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
            for name in (
                "f3_osm_object", "f3_association", "f3_relation_context",
                "f3_provenance",
            )
        }

    def test_schemas_load_and_accept_valid_fixtures(self):
        for schema in self.schemas.values():
            jsonschema.Draft202012Validator.check_schema(schema)
        for document in self.objects:
            jsonschema.validate(document, self.schemas["f3_osm_object"])
            validate_document(document, "f3_osm_object")
        for document in self.associations:
            jsonschema.validate(document, self.schemas["f3_association"])
            validate_document(document, "f3_association")
        jsonschema.validate(self.relation, self.schemas["f3_relation_context"])
        validate_document(self.relation, "f3_relation_context")
        jsonschema.validate(self.provenance, self.schemas["f3_provenance"])
        validate_document(self.provenance, "f3_provenance")

    def test_osm_object_ref_and_positive_id(self):
        invalid_ref = copy.deepcopy(self.objects[0])
        invalid_ref["osm_ref"] = "node/2"
        assert_rejected(self, invalid_ref, "f3_osm_object")
        invalid_id = copy.deepcopy(self.objects[0])
        invalid_id["osm_id"] = 0
        assert_rejected(self, invalid_id, "f3_osm_object")

    def test_node_forbids_is_closed_and_way_requires_it(self):
        node = copy.deepcopy(self.objects[0])
        node["is_closed"] = False
        assert_rejected(self, node, "f3_osm_object")
        way = copy.deepcopy(self.objects[2])
        del way["is_closed"]
        assert_rejected(self, way, "f3_osm_object")

    def test_geometry_status_and_role_are_coherent(self):
        invalid = copy.deepcopy(self.objects[2])
        invalid["geometry_role"] = "none"
        assert_rejected(self, invalid, "f3_osm_object")
        missing_reason = copy.deepcopy(self.objects[4])
        missing_reason["geometry_reason"] = None
        assert_rejected(self, missing_reason, "f3_osm_object")

    def test_geometry_reason_vocabulary_and_status_matrix(self):
        self.assertEqual(
            F3_GEOMETRY_REASONS,
            (
                "added_way_node_direct_association_forbidden",
                "unknown_closed_way_no_votes",
                "unknown_closed_way_conflict",
                "unknown_closed_way_unrecognized_area_value",
                "invalid_area_open_way",
                "invalid_area_empty",
                "invalid_area_non_positive",
                "invalid_area_invalid_polygon",
                "invalid_way_geometry_missing_node",
                "invalid_way_geometry_too_few_positions",
                "invalid_way_geometry_non_finite_coordinate",
            ),
        )
        for reason in F3_NOT_ASSOCIABLE_REASONS[1:]:
            valid = copy.deepcopy(self.objects[4])
            valid["geometry_reason"] = reason
            validate_document(valid, "f3_osm_object")
        for reason in F3_INVALID_REASONS:
            valid = copy.deepcopy(self.objects[4])
            valid["geometry_status"] = "invalid"
            valid["geometry_reason"] = reason
            valid["is_closed"] = reason != "invalid_area_open_way"
            validate_document(valid, "f3_osm_object")

        wrong_status = copy.deepcopy(self.objects[4])
        wrong_status["geometry_status"] = "invalid"
        wrong_status["geometry_reason"] = "unknown_closed_way_no_votes"
        assert_rejected(self, wrong_status, "f3_osm_object")
        wrong_role = copy.deepcopy(self.objects[4])
        wrong_role["geometry_role"] = "line"
        assert_rejected(self, wrong_role, "f3_osm_object")
        open_unknown = copy.deepcopy(self.objects[4])
        open_unknown["is_closed"] = False
        assert_rejected(self, open_unknown, "f3_osm_object")
        closed_open_area = copy.deepcopy(self.objects[4])
        closed_open_area["geometry_status"] = "invalid"
        closed_open_area["geometry_reason"] = "invalid_area_open_way"
        assert_rejected(self, closed_open_area, "f3_osm_object")

    def test_contract_enums_are_rejected(self):
        invalid_object = copy.deepcopy(self.objects[0])
        invalid_object["source_role"] = "unknown"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid_object, self.schemas["f3_osm_object"])
        assert_rejected(self, invalid_object, "f3_osm_object")
        invalid_relation = copy.deepcopy(self.relation)
        invalid_relation["closure_status"] = "complete"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid_relation, self.schemas["f3_relation_context"])
        assert_rejected(self, invalid_relation, "f3_relation_context")

    def test_added_way_node_is_not_directly_associable(self):
        validate_document(self.objects[1], "f3_osm_object")
        self.assertEqual(self.objects[1]["geometry_role"], "point")
        self.assertEqual(self.objects[1]["geometry_status"], "not_associable")
        self.assertEqual(
            self.objects[1]["geometry_reason"],
            "added_way_node_direct_association_forbidden",
        )
        invalid = copy.deepcopy(self.objects[1])
        invalid["geometry_status"] = "valid"
        invalid["geometry_reason"] = None
        assert_rejected(self, invalid, "f3_osm_object")

    def test_unexpected_osm_object_property_is_rejected(self):
        invalid = copy.deepcopy(self.objects[0])
        invalid["geometry"] = {"type": "Point"}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, self.schemas["f3_osm_object"])
        assert_rejected(self, invalid, "f3_osm_object")

    def test_association_invariants(self):
        invalid_ref = copy.deepcopy(self.associations[0])
        invalid_ref["osm_ref"] = "way/1"
        assert_rejected(self, invalid_ref, "f3_association")
        not_intersecting = copy.deepcopy(self.associations[0])
        not_intersecting["intersects"] = False
        assert_rejected(self, not_intersecting, "f3_association")
        inconsistent_boundary = copy.deepcopy(self.associations[0])
        inconsistent_boundary["boundary_contact_only"] = False
        assert_rejected(self, inconsistent_boundary, "f3_association")

    def test_association_distance_must_be_finite_and_non_negative(self):
        for value in (-1.0, math.nan, math.inf, -math.inf):
            invalid = copy.deepcopy(self.associations[0])
            invalid["center_distance_m"] = value
            with self.subTest(value=value):
                assert_rejected(self, invalid, "f3_association")

    def test_relation_references_and_candidates(self):
        invalid_ref = copy.deepcopy(self.relation)
        invalid_ref["relation_ref"] = "relation/101"
        assert_rejected(self, invalid_ref, "f3_relation_context")
        member_ref = copy.deepcopy(self.relation)
        member_ref["associated_members"][0]["member_ref"] = "node/10"
        assert_rejected(self, member_ref, "f3_relation_context")
        empty = copy.deepcopy(self.relation)
        empty["associated_members"][0]["candidate_ids"] = []
        assert_rejected(self, empty, "f3_relation_context")
        duplicated = copy.deepcopy(self.relation)
        duplicated["associated_members"][0]["candidate_ids"] = ["candidate-001", "candidate-001"]
        assert_rejected(self, duplicated, "f3_relation_context")

    def test_relation_counts_and_additional_properties(self):
        invalid_count = copy.deepcopy(self.relation)
        invalid_count["member_count"] = 4
        assert_rejected(self, invalid_count, "f3_relation_context")
        unexpected = copy.deepcopy(self.relation)
        unexpected["geometry"] = None
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(unexpected, self.schemas["f3_relation_context"])
        assert_rejected(self, unexpected, "f3_relation_context")

    def test_relation_counts_are_coherent_per_type(self):
        total_mismatch = copy.deepcopy(self.relation)
        total_mismatch["unresolved_member_counts"]["relation"] = 2
        assert_rejected(self, total_mismatch, "f3_relation_context")

        for count_group in ("present_member_counts", "unresolved_member_counts"):
            for member_type in ("node", "way", "relation"):
                negative = copy.deepcopy(self.relation)
                negative[count_group][member_type] = -1
                with self.subTest(count_group=count_group, member_type=member_type):
                    with self.assertRaises(jsonschema.ValidationError):
                        jsonschema.validate(negative, self.schemas["f3_relation_context"])
                    assert_rejected(self, negative, "f3_relation_context")

        missing_present_way = copy.deepcopy(self.relation)
        missing_present_way["present_member_counts"]["way"] = 0
        missing_present_way["present_member_counts"]["node"] = 2
        assert_rejected(self, missing_present_way, "f3_relation_context")

        missing_present_node = copy.deepcopy(self.relation)
        missing_present_node["associated_members"] = [{
            "member_type": "node",
            "member_id": 20,
            "member_ref": "node/20",
            "role": "stop",
            "candidate_ids": ["candidate-001"],
        }]
        missing_present_node["present_member_counts"]["node"] = 0
        missing_present_node["present_member_counts"]["way"] = 2
        assert_rejected(self, missing_present_node, "f3_relation_context")

        relation_members_need_not_be_associated = copy.deepcopy(self.relation)
        relation_members_need_not_be_associated["present_member_counts"]["relation"] = 1
        relation_members_need_not_be_associated["unresolved_member_counts"]["relation"] = 0
        validate_document(relation_members_need_not_be_associated, "f3_relation_context")

    def test_provenance_requires_platform_metadata(self):
        for field in ("platform_system", "platform_machine"):
            invalid = copy.deepcopy(self.provenance)
            del invalid["software"][field]
            with self.subTest(field=field), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(invalid, self.schemas["f3_provenance"])
            with self.subTest(field=field):
                assert_rejected(self, invalid, "f3_provenance")

    def test_platform_metadata_is_excluded_from_identity_fields(self):
        self.assertEqual(
            F3_IDENTITY_SOFTWARE_FIELDS,
            ("generator_source_sha256", "python_version", "shapely_version", "geos_version"),
        )
        self.assertEqual(
            F3_PROVENANCE_ONLY_SOFTWARE_FIELDS,
            ("python_implementation", "platform_system", "platform_machine"),
        )
        self.assertTrue(set(F3_IDENTITY_SOFTWARE_FIELDS).isdisjoint({"platform_system", "platform_machine"}))

    def test_provenance_rejects_absolute_paths_and_unexpected_fields(self):
        absolute = copy.deepcopy(self.provenance)
        absolute["inputs"]["catalog"]["logical_path"] = "/tmp/manifest.json"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(absolute, self.schemas["f3_provenance"])
        unexpected = copy.deepcopy(self.provenance)
        unexpected["created_at_utc"] = "2026-10-07T00:00:00Z"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(unexpected, self.schemas["f3_provenance"])
        assert_rejected(self, unexpected, "f3_provenance")


if __name__ == "__main__":
    unittest.main()
