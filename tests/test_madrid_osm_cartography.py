from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.madrid_osm_cartography import (
    build_mvt_tiles,
    build_study_context,
    parse_explicit_height_m,
    validate_pmtiles_archive,
    vector_layer_metadata,
    write_pmtiles,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_GEO_AVAILABLE = all(
    importlib.util.find_spec(name) is not None
    for name in ("osmium", "shapely", "mapbox_vector_tile", "pmtiles", "mercantile")
)


class MadridOSMCartographyTests(unittest.TestCase):
    def test_height_parser_accepts_only_explicit_positive_metre_values(self) -> None:
        self.assertEqual(parse_explicit_height_m("12.5"), 12.5)
        self.assertEqual(parse_explicit_height_m(" 9 m "), 9.0)
        for raw in (None, "", "0", "-2", "3 ft", "4;5", "unknown", "4 floors"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_explicit_height_m(raw))

    @unittest.skipUnless(OPTIONAL_GEO_AVAILABLE, "requiere requirements-cartography.txt")
    def test_buffer_uses_metric_epsg25830_and_contains_d004(self) -> None:
        from shapely.geometry import box

        config = __import__("json").loads((PROJECT_ROOT / "config/madrid.yaml").read_text(encoding="utf-8"))
        context = build_study_context(config["region"]["bbox"], margin_m=250)
        inner = context["d004_utm"].bounds
        outer = context["coverage_utm"].bounds
        self.assertAlmostEqual(inner[0] - outer[0], 250, delta=0.01)
        self.assertAlmostEqual(inner[1] - outer[1], 250, delta=0.01)
        self.assertAlmostEqual(outer[2] - inner[2], 250, delta=0.01)
        self.assertAlmostEqual(outer[3] - inner[3], 250, delta=0.01)
        self.assertTrue(context["coverage_wgs84"].covers(box(-3.709, 40.412, -3.699, 40.420)))

    @unittest.skipUnless(OPTIONAL_GEO_AVAILABLE, "requiere requirements-cartography.txt")
    def test_builds_and_reads_a_small_pmtiles_mvt_without_overwriting(self) -> None:
        from shapely.geometry import LineString, Polygon

        bbox = {"west": -3.709, "south": 40.412, "east": -3.699, "north": 40.420}
        context = build_study_context(bbox, margin_m=250)
        minx, miny, _, _ = context["coverage_utm"].bounds
        features = [
            {
                "layer": "building", "source_type": "way", "osm_id": 10,
                "geometry": Polygon([(minx + 10, miny + 10), (minx + 40, miny + 10),
                                      (minx + 40, miny + 40), (minx + 10, miny + 40)]),
                "properties": {"building": "yes", "height": 12.5, "min_height": 2.0},
            },
            {
                "layer": "transportation", "source_type": "way", "osm_id": 11,
                "geometry": LineString([(minx + 5, miny + 5), (minx + 80, miny + 80)]),
                "properties": {"class": "minor", "highway": "residential"},
            },
        ]
        tiles, tile_stats = build_mvt_tiles(features, context, min_zoom=15, max_zoom=15)
        layers = vector_layer_metadata(features, min_zoom=15, max_zoom=15)
        self.assertTrue(tiles)
        self.assertEqual(tile_stats["extent"], 4096)
        self.assertIn("height", next(layer for layer in layers if layer["id"] == "building")["fields"])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "test.pmtiles"
            audit = {
                "height_coverage_base_buildings": {"denominator": 1, "explicit_numeric_metre_height": 1},
                "source": {
                    "provenance_sha256": "b" * 64,
                    "data_timestamp_utc": "2026-10-14T20:21:12Z",
                    "bbox_wgs84": {"west": -4.6, "south": 39.8, "east": -3.0, "north": 41.2},
                    "source_url": "https://example.invalid/source.osm.pbf",
                },
            }
            write_pmtiles(
                output, tiles, context, source_id="f4-test", source_sha256="a" * 64,
                feature_stats={"audit": audit, "vector_layers": layers, "toolchain": {"test": "fixture"}},
            )
            validation = validate_pmtiles_archive(output, context["map_bounds_wgs84"])
            self.assertEqual(validation["tile_type"], "MVT")
            self.assertGreater(validation["explicit_height_features_in_tiles"], 0)
            with self.assertRaises(FileExistsError):
                write_pmtiles(
                    output, tiles, context, source_id="f4-test", source_sha256="a" * 64,
                    feature_stats={"audit": audit, "vector_layers": layers, "toolchain": {"test": "fixture"}},
                )


if __name__ == "__main__":
    unittest.main()
