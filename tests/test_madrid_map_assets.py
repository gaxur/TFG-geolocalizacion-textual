from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_madrid_map_assets import build_map_assets
from src.tfg_phase0.catalog import build_catalog
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.madrid_map_assets import MapAssetError, validate_catalog_geometry


ROOT = Path(__file__).resolve().parents[1]


class MadridMapAssetsTests(unittest.TestCase):
    def test_regenerates_exact_f1_cells_for_both_galleries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            assets = build_map_assets(
                config_path=ROOT / "config/madrid.yaml",
                output_dir=output,
                regenerate_grid=True,
            )

            expected = {"madrid-25m": 1115, "madrid-50m": 253}
            for gallery_id, count in expected.items():
                entry = assets["galleries"][gallery_id]
                size = 25 if gallery_id.endswith('25m') else 50
                selection = json.loads((ROOT / "config" / f"madrid_f4_visual_gallery_{size}m.json").read_text(encoding="utf-8"))
                self.assertEqual(entry["manifest_sha256"], selection["source_manifest_sha256"])
                self.assertEqual(entry["expected_f4_manifest_sha256"], selection["source_manifest_sha256"])
                document = json.loads((output / entry["geojson_file"]).read_text(encoding="utf-8"))
                self.assertEqual(document["type"], "FeatureCollection")
                self.assertEqual(len(document["features"]), count)
                feature = document["features"][0]
                self.assertEqual(feature["id"], feature["properties"]["candidate_key"])
                self.assertEqual(feature["properties"]["gallery_id"], gallery_id)
                self.assertEqual(feature["properties"]["cell_size_m"], entry["cell_size_m"])
                ring = feature["geometry"]["coordinates"][0]
                self.assertEqual(ring[0], ring[-1])
                self.assertTrue(all(len(point) == 2 for point in ring))
                self.assertTrue(all(-180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in ring))
            self.assertIsNone(assets["osm_snapshot_id"])
            self.assertEqual(assets["source_mode"], "canonical_f1_grid_regeneration")

    def test_asset_build_is_deterministic_and_does_not_overwrite_different_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = build_map_assets(
                config_path=ROOT / "config/madrid.yaml",
                output_dir=output,
                regenerate_grid=True,
            )
            first_bytes = (output / "cells-25m.geojson").read_bytes()
            second = build_map_assets(
                config_path=ROOT / "config/madrid.yaml",
                output_dir=output,
                regenerate_grid=True,
            )
            self.assertEqual(first_bytes, (output / "cells-25m.geojson").read_bytes())
            self.assertEqual(first["galleries"], second["galleries"])

            (output / "cells-25m.geojson").write_text("tampered", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                build_map_assets(
                    config_path=ROOT / "config/madrid.yaml",
                    output_dir=output,
                    regenerate_grid=True,
                )

    def test_rejects_a_catalog_polygon_that_differs_from_canonical_f1(self) -> None:
        config = load_region_config(ROOT / "config/madrid.yaml")
        canonical = build_catalog(config, spacing_m=50)
        altered = json.loads(json.dumps(canonical))
        altered["candidates"][0]["cell_geometry"]["coordinates"][0][1][0] += 0.000001
        with self.assertRaises(MapAssetError):
            validate_catalog_geometry(altered, canonical, spacing_m=50)

    def test_missing_f4_manifests_require_explicit_f1_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                build_map_assets(
                    config_path=ROOT / "config/madrid.yaml",
                    output_dir=Path(temporary) / "map-assets",
                )


if __name__ == "__main__":
    unittest.main()
