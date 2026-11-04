import json,unittest
from pathlib import Path
from src.tfg_phase0.commons_provider import CommonsMetadataError,normalize_commons_record,validate_commons_use

ROOT=Path(__file__).resolve().parents[1]
class CommonsProviderTests(unittest.TestCase):
 def test_object_coordinate_never_becomes_camera(self):
  raw=json.loads((ROOT/"tests/fixtures/commons_api_record.json").read_text());record=normalize_commons_record(raw,consulted_at_utc="2026-11-03T00:00:00Z",inventory_id="fixture")
  self.assertEqual(record["location"]["kind"],"object");decision=validate_commons_use(record);self.assertFalse(decision["eligible_for_geometric_camera_association"]);self.assertTrue(decision["eligible_for_semantic_object_evidence"])
 def test_camera_requires_explicit_verification(self):
  raw=json.loads((ROOT/"tests/fixtures/commons_api_record.json").read_text());raw["location_kind"]="camera"
  with self.assertRaises(CommonsMetadataError):normalize_commons_record(raw,consulted_at_utc="2026-11-03T00:00:00Z",inventory_id="fixture")
 def test_missing_license_blocks_use(self):
  raw=json.loads((ROOT/"tests/fixtures/commons_api_record.json").read_text());raw["imageinfo"][0]["extmetadata"].pop("LicenseShortName");record=normalize_commons_record(raw,consulted_at_utc="2026-11-03T00:00:00Z",inventory_id="fixture");self.assertIn("license_or_author_incomplete",validate_commons_use(record)["blockers"])
if __name__=="__main__":unittest.main()
