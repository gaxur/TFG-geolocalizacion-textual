import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.catalog import (
    GRID_GENERATOR_VERSION,
    MANIFEST_GENERATOR_VERSION,
    build_catalog,
    candidate_id,
    f1_config_input,
    write_manifest,
)
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.crs import epsg25830_to_wgs84, wgs84_to_epsg25830
from src.tfg_phase0.provenance import canonical_json, sha256_json
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]


class Phase1CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_region_config(ROOT / "config/madrid.yaml")
        cls.catalog_25 = build_catalog(cls.config, spacing_m=25)
        cls.catalog_50 = build_catalog(cls.config, spacing_m=50)

    def test_bbox_is_valid(self):
        bbox = self.config["region"]["bbox"]
        self.assertLess(bbox["south"], bbox["north"])
        self.assertLess(bbox["west"], bbox["east"])

    def test_wgs84_to_epsg25830(self):
        easting, northing = wgs84_to_epsg25830(40.4168, -3.7038)
        self.assertAlmostEqual(easting, 440291.27, delta=1.0)
        self.assertAlmostEqual(northing, 4474257.38, delta=0.1)

    def test_epsg25830_to_wgs84(self):
        latitude, longitude = epsg25830_to_wgs84(440291.27, 4474257.38)
        self.assertAlmostEqual(latitude, 40.4168, delta=3e-5)
        self.assertAlmostEqual(longitude, -3.7038, delta=1e-5)

    def test_crs_round_trip(self):
        expected = (40.4168, -3.7038)
        actual = epsg25830_to_wgs84(*wgs84_to_epsg25830(*expected))
        self.assertAlmostEqual(actual[0], expected[0], places=7)
        self.assertAlmostEqual(actual[1], expected[1], places=7)

    def test_grid_is_not_empty(self):
        self.assertGreater(len(self.catalog_25["candidates"]), 0)

    def test_candidate_ids_are_unique(self):
        identifiers = [item["candidate_id"] for item in self.catalog_25["candidates"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_candidate_id_is_deterministic(self):
        expected = "MADP_MADRID_PILOT_GRID_V1_G0123456789AB_S025_L025_R0003_C0012"
        self.assertEqual(candidate_id("MADP", "madrid-pilot-grid-v1", "0123456789ab", 25, 25, 3, 12), expected)
        self.assertEqual(candidate_id("MADP", "madrid-pilot-grid-v1", "0123456789ab", 25, 25, 3, 12), expected)

    def test_bbox_change_changes_candidate_identity(self):
        shifted = copy.deepcopy(self.config)
        shifted["region"]["bbox"]["west"] += 0.0001
        other = build_catalog(shifted, spacing_m=25)
        self.assertNotEqual(
            self.catalog_25["generation"]["grid_hash"],
            other["generation"]["grid_hash"],
        )
        self.assertNotEqual(
            self.catalog_25["candidates"][0]["candidate_id"],
            other["candidates"][0]["candidate_id"],
        )

    def test_same_config_produces_same_catalog(self):
        self.assertEqual(
            canonical_json(build_catalog(self.config, spacing_m=25)),
            canonical_json(build_catalog(copy.deepcopy(self.config), spacing_m=25)),
        )

    def test_f1_config_input_contains_exactly_effective_fields(self):
        self.assertEqual(f1_config_input(self.config), {
            "schema_version": "1.0",
            "region": {
                "name": "madrid_pilot",
                "bbox": {
                    "north": 40.4200,
                    "south": 40.4120,
                    "east": -3.6990,
                    "west": -3.7090,
                },
                "crs": "EPSG:4326",
            },
            "catalog": {
                "projected_crs": "EPSG:25830",
                "catalog_version": "madrid-pilot-grid-v1",
                "candidate_id_prefix": "MADP",
                "candidate_generation": "projected_square_grid",
                "border_policy": "full_cell_within_bbox",
            },
        })

    def test_unrelated_config_does_not_change_f1_input_or_manifest(self):
        changed = copy.deepcopy(self.config)
        changed["osm_acquisition"]["endpoint"] = "https://example.test/api"
        changed["artifacts"]["manifest"] = "another/output.json"
        self.assertEqual(f1_config_input(changed), f1_config_input(self.config))
        self.assertEqual(build_catalog(changed, spacing_m=25), self.catalog_25)

    def test_every_relevant_config_field_changes_f1_input_hash(self):
        mutations = {
            "schema_version": lambda value: "2.0",
            "region.name": lambda value: value + "_other",
            "region.bbox.north": lambda value: value + 0.001,
            "region.bbox.south": lambda value: value - 0.001,
            "region.bbox.east": lambda value: value + 0.001,
            "region.bbox.west": lambda value: value - 0.001,
            "region.crs": lambda value: "EPSG:3857",
            "catalog.projected_crs": lambda value: "EPSG:3857",
            "catalog.catalog_version": lambda value: value + "-v2",
            "catalog.candidate_id_prefix": lambda value: "OTHER",
            "catalog.candidate_generation": lambda value: "other",
            "catalog.border_policy": lambda value: "other",
        }
        original_hash = sha256_json(f1_config_input(self.config))
        for path, mutate in mutations.items():
            changed = copy.deepcopy(self.config)
            parts = path.split(".")
            target = changed
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = mutate(target[parts[-1]])
            with self.subTest(path=path):
                self.assertNotEqual(sha256_json(f1_config_input(changed)), original_hash)

    def test_manifest_v2_provenance_and_grid_version_are_separate(self):
        self.assertEqual(
            self.catalog_25["provenance"]["input_hashes"],
            {"f1_config": sha256_json(f1_config_input(self.config))},
        )
        self.assertNotIn("region_config", self.catalog_25["provenance"]["input_hashes"])
        self.assertEqual(self.catalog_25["provenance"]["code_version"], MANIFEST_GENERATOR_VERSION)
        self.assertEqual(self.catalog_25["generation"]["generator_version"], GRID_GENERATOR_VERSION)

    def test_manifest_v2_preserves_catalog_identity_and_geometry(self):
        self.assertEqual(self.catalog_25["manifest_id"], "madrid-pilot-grid-v1-s25-l25")
        self.assertEqual(self.catalog_50["manifest_id"], "madrid-pilot-grid-v1-s50-l50")
        unrelated_change = copy.deepcopy(self.config)
        unrelated_change["osm_acquisition"]["endpoint"] = "https://example.test/api"
        unrelated_change["artifacts"]["manifest"] = "another/output.json"
        other_25 = build_catalog(unrelated_change, spacing_m=25)
        other_50 = build_catalog(unrelated_change, spacing_m=50)
        self.assertEqual(self.catalog_25["generation"], other_25["generation"])
        self.assertEqual(self.catalog_50["generation"], other_50["generation"])
        self.assertEqual(self.catalog_25["candidates"], other_25["candidates"])
        self.assertEqual(self.catalog_50["candidates"], other_50["candidates"])
        self.assertEqual(len(self.catalog_25["candidates"]), 1115)
        self.assertEqual(len(self.catalog_50["candidates"]), 253)

    def test_spacing_is_configurable(self):
        self.assertEqual(self.catalog_25["generation"]["spacing_m"], 25)
        self.assertEqual(self.catalog_50["generation"]["spacing_m"], 50)

    def test_25_and_50_m_catalogs_differ(self):
        self.assertEqual(len(self.catalog_25["candidates"]), 1115)
        self.assertEqual(len(self.catalog_50["candidates"]), 253)
        self.assertNotEqual(len(self.catalog_25["candidates"]), len(self.catalog_50["candidates"]))
        self.assertNotEqual(self.catalog_25["manifest_id"], self.catalog_50["manifest_id"])

    def test_centers_and_vertices_are_inside_bbox(self):
        bbox = self.config["region"]["bbox"]
        for candidate in self.catalog_25["candidates"]:
            self.assertLessEqual(bbox["south"], candidate["latitude"])
            self.assertLessEqual(candidate["latitude"], bbox["north"])
            self.assertLessEqual(bbox["west"], candidate["longitude"])
            self.assertLessEqual(candidate["longitude"], bbox["east"])
            for longitude, latitude in candidate["cell_geometry"]["coordinates"][0]:
                self.assertLessEqual(bbox["south"], latitude)
                self.assertLessEqual(latitude, bbox["north"])
                self.assertLessEqual(bbox["west"], longitude)
                self.assertLessEqual(longitude, bbox["east"])

    def test_manifest_validates_against_contract(self):
        validate_document(self.catalog_25, "manifest")

    def test_manifest_validates_against_json_schema(self):
        import jsonschema

        schema = json.loads((ROOT / "schemas/manifest.schema.json").read_text())
        jsonschema.validate(self.catalog_25, schema)

    def test_serialization_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            write_manifest(self.catalog_25, first)
            write_manifest(build_catalog(self.config, spacing_m=25), second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_future_artifacts_are_null(self):
        for candidate in self.catalog_25["candidates"]:
            self.assertTrue(all(value is None for value in candidate["artifacts"].values()))
        self.assertIsNone(self.catalog_25["osm_snapshot_id"])

    def test_manifest_has_no_ground_truth_dependency(self):
        serialized = canonical_json(self.catalog_25).lower()
        self.assertNotIn("ground_truth", serialized)
        self.assertNotIn("query", serialized)

    def test_invalid_or_duplicate_candidates_are_rejected(self):
        invalid = copy.deepcopy(self.catalog_25)
        invalid["candidates"].append(copy.deepcopy(invalid["candidates"][0]))
        with self.assertRaises(SchemaValidationError):
            validate_document(invalid, "manifest")


if __name__ == "__main__":
    unittest.main()
