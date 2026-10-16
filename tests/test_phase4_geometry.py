import json
import math
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_geometry import (
    bbox_contains, bbox_wgs84_to_epsg3857, candidate_raster_geometry,
    epsg3857_to_wgs84, global_pixel_to_wgs84, meters_per_pixel,
    wgs84_to_epsg3857, wgs84_to_global_pixel,
)
from src.tfg_phase0.f4_preflight import build_coverage_preflight, build_osm_source_reference, load_verified_selection
from src.tfg_phase0.f4_validation import load_verified_f1_catalog, load_verified_f1_50m


ROOT = Path(__file__).resolve().parents[1]


class Phase4GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_region_config(ROOT / "config/madrid.yaml")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.manifest_path = Path(cls.temporary.name) / "manifest-50m.json"
        write_manifest(build_catalog(cls.config, spacing_m=50), cls.manifest_path)
        cls.catalog = load_verified_f1_50m(cls.manifest_path, cls.config)
        cls.selection, cls.selection_hash = load_verified_selection(ROOT / "config/madrid_f4_visual_fixture.json", cls.catalog)
        cls.full_selection, cls.full_selection_hash = load_verified_selection(ROOT / "config/madrid_f4_visual_gallery_50m.json", cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_web_mercator_round_trip(self):
        latitude, longitude = 40.4157983231, -3.7040304835
        x, y = wgs84_to_epsg3857(latitude, longitude)
        recovered = epsg3857_to_wgs84(x, y)
        self.assertAlmostEqual(recovered[0], latitude, places=10)
        self.assertAlmostEqual(recovered[1], longitude, places=10)

    def test_xyz_global_pixel_round_trip_and_orientation(self):
        latitude, longitude = 40.4157983231, -3.7040304835
        pixel = wgs84_to_global_pixel(latitude, longitude, 18)
        recovered = global_pixel_to_wgs84(*pixel, 18)
        self.assertAlmostEqual(recovered[0], latitude, places=10)
        self.assertAlmostEqual(recovered[1], longitude, places=10)
        north_y = wgs84_to_global_pixel(latitude + 0.001, longitude, 18)[1]
        self.assertLess(north_y, pixel[1])

    def test_native_z18_footprint_and_subpixel_centering(self):
        geometry = candidate_raster_geometry(40.4157983231, -3.7040304835)
        expected_mpp = 2 * math.pi * 6_378_137 / (256 * 2**18)
        self.assertAlmostEqual(meters_per_pixel(18), expected_mpp, places=12)
        self.assertAlmostEqual(geometry.request_bbox.max_x - geometry.request_bbox.min_x, expected_mpp * 256, places=8)
        self.assertAlmostEqual(geometry.request_bbox.max_y - geometry.request_bbox.min_y, expected_mpp * 256, places=8)
        self.assertAlmostEqual(geometry.output_bbox.max_x - geometry.output_bbox.min_x, expected_mpp * 256, places=8)
        self.assertAlmostEqual(geometry.crop_left_px + 128, geometry.candidate_pixel_x, places=10)
        self.assertAlmostEqual(geometry.crop_top_px + 128, geometry.candidate_pixel_y, places=10)
        self.assertTrue(bbox_contains(geometry.source_mosaic_bbox, geometry.output_bbox))

    def test_preflight_f2_covers_eight_and_rejects_east_probe(self):
        snapshot = ROOT / "data/raw/osm/snapshots/osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141"
        provenance = json.loads((snapshot / "provenance.json").read_text(encoding="utf-8"))
        result = build_coverage_preflight(self.catalog, self.selection, provenance)
        self.assertEqual(result["covered_count"], 8)
        self.assertEqual(result["requires_margin_count"], 1)
        missing = [row for row in result["candidates"] if not row["covered"]]
        self.assertEqual(missing[0]["candidate_id"], "MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0004_C0016")
        self.assertAlmostEqual(missing[0]["margin_deficit_m"]["east_m"], 43.3295, places=3)
        source = build_osm_source_reference(snapshot, ROOT)
        self.assertEqual(source["source_id"], provenance["osm_snapshot_id"])
        self.assertEqual(source["data_sha256"], provenance["raw_sha256"])
        self.assertEqual(source["coverage_bbox_wgs84"], provenance["bbox"])

    def test_selection_is_fixed_and_independent_of_text(self):
        self.assertEqual(len(self.selection["candidates"]), 9)
        self.assertFalse(self.selection["evaluation_use"])
        self.assertFalse(self.selection["text_or_ground_truth_used"])
        self.assertEqual(len({item["candidate_id"] for item in self.selection["candidates"]}), 9)
        self.assertEqual(self.selection_hash, "40cd0cf8e684aea65f6c782971bae8b8152824587e8a009fbce072e4706ffa6e")

    def test_full_selection_is_exact_catalog_order(self):
        selected = [row["candidate_id"] for row in self.full_selection["candidates"]]
        expected = [candidate.candidate_id for candidate in self.catalog.candidates]
        self.assertEqual(selected, expected)
        self.assertEqual(len(selected), 253)
        self.assertEqual(len(set(selected)), 253)
        self.assertTrue(selected[0].endswith("R0001_C0001"))
        self.assertTrue(selected[-1].endswith("R0016_C0016"))
        self.assertFalse(self.full_selection["text_or_ground_truth_used"])
        self.assertEqual(self.full_selection_hash, "2758a291222646cc84ec1ee1bcbfd69759a066d968129d202f457754de712389")

    def test_full_25m_selection_is_exact_catalog_order(self):
        catalog = load_verified_f1_catalog(ROOT / "data/processed/catalog/manifest-25m.json", self.config)
        selection, digest = load_verified_selection(ROOT / "config/madrid_f4_visual_gallery_25m.json", catalog)
        selected = [row["candidate_id"] for row in selection["candidates"]]
        self.assertEqual(selected, [candidate.candidate_id for candidate in catalog.candidates])
        self.assertEqual(len(selected), 1115)
        self.assertTrue(selected[0].endswith("R0001_C0001"))
        self.assertTrue(selected[-1].endswith("R0034_C0033"))
        self.assertEqual(digest, "e5f28809d3fb85277a4211c6871ce165aacc0a15a69e7393bbd6299672acb5f0")


if __name__ == "__main__":
    unittest.main()
