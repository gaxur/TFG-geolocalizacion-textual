import json
import unittest
from pathlib import Path

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.provenance import sha256_json
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]


def valid_llm_query():
    return {
        "schema_version": "1.0",
        "query_id": "q-001",
        "input": {"text": "Una plaza con una iglesia cerca", "language": "es"},
        "region": {
            "kind": "catalog_region",
            "source": "configuration",
            "catalog_region_id": "madrid_pilot",
            "name": None,
            "bbox": None,
            "center_radius": None,
            "confidence": 1.0,
        },
        "objects": [
            {
                "id": "o1",
                "mention": "plaza",
                "canonical_type": "public_square",
                "name": None,
                "negated": False,
                "certainty": "explicit",
                "confidence": 0.9,
                "attributes": [],
            }
        ],
        "relations": [],
        "visual_clues": [],
        "unparsed_clues": [],
        "warnings": [],
    }


def valid_evaluation():
    return {
        "schema_version": "1.0",
        "sample_id": "MADRID_TEST_0001",
        "location_id": "MADRID_LOC_0001",
        "split": "development",
        "description": {
            "text": "Una plaza con una iglesia cerca",
            "language": "es",
            "source_type": "manual_controlled",
            "instructions_version": "dev-1",
        },
        "search_scope": {"region_id": "madrid_pilot", "scope_type": "catalog_region"},
        "ground_truth": {
            "latitude": 40.4168,
            "longitude": -3.7038,
            "crs": "EPSG:4326",
            "capture_method": "fixture",
            "catalog_assignment": None,
        },
        "provenance": {"synthetic": True},
        "reproducibility": {"protocol_version": "1.0"},
        "quality": {"status": "example"},
    }


def valid_manifest():
    return {
        "schema_version": "1.0",
        "manifest_id": "manifest-fixture",
        "region_id": "madrid_pilot",
        "catalog_version": "catalog-fixture",
        "osm_snapshot_id": None,
        "generation": {
            "region_bbox_wgs84": {"north": 40.42, "south": 40.412, "east": -3.699, "west": -3.709},
            "source_crs": "EPSG:4326",
            "projected_crs": "EPSG:25830",
            "spacing_m": 25,
            "cell_size_m": 25,
            "border_policy": "full_cell_within_bbox",
            "order": "row_south_to_north_then_column_west_to_east",
            "grid_hash": "0123456789ab",
            "generator_version": "phase1-grid-v1",
        },
        "provenance": {
            "schema_version": "1.0",
            "artifact_id": "manifest-fixture",
            "source": "fixture",
            "source_version": None,
            "input_hashes": {"fixture": "0" * 64},
            "parameters_hash": "0" * 64,
            "code_version": None,
        },
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "latitude": 40.4168,
                "longitude": -3.7038,
                "cell_geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-3.704, 40.416], [-3.703, 40.416], [-3.703, 40.417], [-3.704, 40.417], [-3.704, 40.416]]],
                },
                "artifacts": {
                    "osm_image": None,
                    "osm_embedding": None,
                    "satellite_image": None,
                    "satellite_embedding": None,
                    "scene_id": None,
                    "scene_graph": None,
                    "scene_embedding": None,
                },
                "generation": {
                    "row": 0,
                    "column": 0,
                    "center_easting_m": 440000.0,
                    "center_northing_m": 4474000.0,
                },
            }
        ],
    }


def valid_experiment_parameters():
    return {
        "schema_version": "1.0",
        "experiment_id": "pending-values-fixture",
        "parameters": {
            "candidate_spacing_m": None,
            "min_candidates": None,
            "target_candidates": None,
            "max_candidates": None,
            "proximity_radii_m": None,
            "relaxation_factors": None,
            "scoring_weights": None,
            "confidence_thresholds": None,
            "language_strategy": None,
            "distance_thresholds_m": None,
            "confidence_interval_method": None,
        },
    }


class Phase0Tests(unittest.TestCase):
    def test_region_config_is_valid(self):
        config = load_region_config(ROOT / "config" / "madrid.yaml")
        self.assertEqual(config["region"]["name"], "madrid_pilot")
        self.assertIsNone(config["catalog"]["candidate_spacing_m"])

    def test_bbox_invalid(self):
        config = json.loads((ROOT / "config" / "madrid.yaml").read_text(encoding="utf-8"))
        config["region"]["bbox"]["south"] = config["region"]["bbox"]["north"]
        with self.assertRaises(SchemaValidationError):
            validate_document(config, "region_config")

    def test_unknown_config_field_is_invalid(self):
        config = json.loads((ROOT / "config" / "madrid.yaml").read_text(encoding="utf-8"))
        config["unexpected"] = True
        with self.assertRaises(SchemaValidationError):
            validate_document(config, "region_config")

    def test_llm_schema_valid(self):
        validate_document(valid_llm_query(), "llm_geo_query")

    def test_llm_missing_required_field_is_invalid(self):
        document = valid_llm_query()
        del document["input"]["text"]
        with self.assertRaises(SchemaValidationError):
            validate_document(document, "llm_geo_query")

    def test_llm_unknown_field_is_invalid(self):
        document = valid_llm_query()
        document["overpass_query"] = "never generated by the LLM"
        with self.assertRaises(SchemaValidationError):
            validate_document(document, "llm_geo_query")

    def test_coordinates_are_validated(self):
        document = valid_evaluation()
        document["ground_truth"]["latitude"] = 95
        with self.assertRaises(SchemaValidationError):
            validate_document(document, "evaluation_example")

    def test_evaluation_schema_valid(self):
        validate_document(valid_evaluation(), "evaluation_example")

    def test_evaluation_version_is_required(self):
        document = valid_evaluation()
        document["schema_version"] = "2.0"
        with self.assertRaises(SchemaValidationError):
            validate_document(document, "evaluation_example")

    def test_experimental_parameters_are_nullable(self):
        validate_document(valid_experiment_parameters(), "experiment_parameters")

    def test_experiment_unknown_field_is_invalid(self):
        document = valid_experiment_parameters()
        document["parameters"]["min_candidates"] = 100
        document["parameters"]["new_parameter"] = 1
        with self.assertRaises(SchemaValidationError):
            validate_document(document, "experiment_parameters")

    def test_manifest_schema_valid(self):
        validate_document(valid_manifest(), "manifest")

    def test_manifest_unknown_nested_field_is_invalid(self):
        document = valid_manifest()
        document["candidates"][0]["artifacts"]["unknown"] = "x"
        with self.assertRaises(SchemaValidationError):
            validate_document(document, "manifest")

    def test_provenance_hash_is_deterministic(self):
        self.assertEqual(sha256_json({"b": 2, "a": 1}), sha256_json({"a": 1, "b": 2}))


if __name__ == "__main__":
    unittest.main()
