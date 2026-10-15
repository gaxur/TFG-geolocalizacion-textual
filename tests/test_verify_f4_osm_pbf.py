import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.verify_f4_osm_pbf import main


class VerifyF4OsmPbfTests(unittest.TestCase):
    def test_accepts_matching_ordered_pbf_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pbf = root / "source.osm.pbf"
            pbf.write_bytes(b"fixture")
            provenance = root / "provenance.json"
            provenance.write_text(json.dumps({
                "bbox": {"west": -4.0, "south": 39.0, "east": -3.0, "north": 41.0},
                "data_timestamp_utc": "2026-10-14T20:21:12Z",
                "raw_size_bytes": 7,
            }), encoding="utf-8")
            metadata = {
                "file": {"size": 7},
                "header": {"boxes": [[-4.0, 39.0, -3.0, 41.0]], "option": {"timestamp": "2026-10-14T20:21:12Z"}},
                "data": {"objects_ordered": True},
            }
            completed = type("Completed", (), {"stdout": json.dumps(metadata)})()
            with patch("subprocess.run", return_value=completed), patch(
                "sys.argv", ["verify_f4_osm_pbf.py", "--pbf", str(pbf), "--provenance", str(provenance)]
            ):
                self.assertEqual(main(), 0)

    def test_rejects_unordered_pbf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pbf = root / "source.osm.pbf"
            pbf.write_bytes(b"fixture")
            provenance = root / "provenance.json"
            provenance.write_text(json.dumps({
                "bbox": {"west": -4.0, "south": 39.0, "east": -3.0, "north": 41.0},
                "data_timestamp_utc": "2026-10-14T20:21:12Z",
                "raw_size_bytes": 7,
            }), encoding="utf-8")
            metadata = {
                "file": {"size": 7},
                "header": {"boxes": [[-4.0, 39.0, -3.0, 41.0]], "option": {"timestamp": "2026-10-14T20:21:12Z"}},
                "data": {"objects_ordered": False},
            }
            completed = type("Completed", (), {"stdout": json.dumps(metadata)})()
            with patch("subprocess.run", return_value=completed), patch(
                "sys.argv", ["verify_f4_osm_pbf.py", "--pbf", str(pbf), "--provenance", str(provenance)]
            ), self.assertRaises(ValueError):
                main()


if __name__ == "__main__":
    unittest.main()
