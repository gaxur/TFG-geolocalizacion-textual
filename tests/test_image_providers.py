import unittest

from src.tfg_phase0.image_providers import MapillaryMetadataProvider,PanoramaxMetadataProvider


class ImageProviderTests(unittest.TestCase):
    def test_mapillary_preserves_provenance_and_sequence(self):
        rows=MapillaryMetadataProvider().normalize_inventory({"images":[{"image_id":"1","latitude":40.0,"longitude":-3.0,"sequence_id":"s","captured_at_epoch_ms":1,"orientation_degrees":90,"camera_type":"perspective","width_px":100,"height_px":50}]})
        self.assertEqual(rows[0].global_record_id,"mapillary:1");self.assertEqual(rows[0].collection_or_sequence_id,"s");self.assertEqual(rows[0].license_identifier,"CC-BY-SA-4.0")

    def test_panoramax_does_not_invent_accuracy_or_heading(self):
        rows=PanoramaxMetadataProvider().normalize_inventory({"items":[{"item_id":"x","collection_id":"c","camera_position":{"latitude":40.0,"longitude":-3.0,"horizontal_accuracy_m":None},"captured_at_utc":None,"license":"CC-BY-SA-4.0","item_url":"https://example.invalid/x"}]})
        self.assertIsNone(rows[0].horizontal_accuracy_m);self.assertIsNone(rows[0].heading_degrees);self.assertEqual(rows[0].provider,"panoramax")
