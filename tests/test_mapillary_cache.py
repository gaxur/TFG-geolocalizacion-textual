import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.mapillary_cache import MapillaryCache, MapillaryCacheError


class MapillaryCacheTests(unittest.TestCase):
    def test_store_reuses_same_id_and_rejects_different_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = MapillaryCache(Path(temporary), max_gb=1, ttl_hours=1)
            first = cache.store("123", b"jpeg-data", {"provider": "Mapillary"})
            second = cache.store("123", b"jpeg-data", {"provider": "Mapillary"})
            self.assertEqual(first["sha256"], second["sha256"])
            with self.assertRaises(MapillaryCacheError):
                cache.store("123", b"other-data", {"provider": "Mapillary"})

    def test_cleanup_skips_active_and_pinned_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = MapillaryCache(Path(temporary), max_gb=0.000000001, ttl_hours=1)
            cache.store("123", b"one", {})
            cache.store("456", b"two", {})
            cache.pin("456", "frozen-experiment")
            with cache.in_use(["123"]):
                report = cache.cleanup(now=10**10)
                self.assertEqual(report["removed_image_ids"], [])
            report = cache.cleanup(now=10**10)
            self.assertEqual(report["removed_image_ids"], ["123"])
            self.assertTrue(cache.image_path("456").exists())


if __name__ == "__main__":
    unittest.main()
