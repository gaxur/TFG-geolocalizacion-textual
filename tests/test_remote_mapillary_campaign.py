import copy
import unittest

from src.tfg_phase0.remote_mapillary_campaign import (
    D004_BBOX,
    RemoteCampaignError,
    select_remote_campaign,
    validate_pixel_independence,
    validate_selection_plan,
)


class RemoteCampaignTests(unittest.TestCase):
    def test_small_inventory_fails_capacity_without_gallery_input(self):
        inventory = {"inventory_id": "i", "images": []}
        with self.assertRaises(ValueError):
            select_remote_campaign(
                inventory,
                bbox=D004_BBOX,
                historical=[],
                inventory_sha256="0" * 64,
            )

    def test_other_bbox_is_rejected(self):
        with self.assertRaisesRegex(RemoteCampaignError, "D004"):
            select_remote_campaign(
                {"inventory_id": "i", "images": []},
                bbox={"north": 1, "south": 0, "east": 1, "west": 0},
                historical=[],
                inventory_sha256="0" * 64,
            )

    def test_selection_rejects_reference_reused_for_verification(self):
        document = self._selection_fixture()
        document["references"][0]["verification_plan"][0]["image_id"] = document["references"][0]["reference"]["image_id"]
        self._refresh_id(document)
        with self.assertRaisesRegex(RemoteCampaignError, "disjuntos"):
            validate_selection_plan(document)

    def test_pixel_gate_detects_exact_and_near_duplicates(self):
        document = self._selection_fixture()
        assets = []
        for row in document["references"]:
            ids = [row["reference"]["image_id"]] + [asset["image_id"] for asset in row["verification_plan"]]
            for image_id in ids:
                assets.append({"image_id": image_id, "status": "downloaded", "sha256": image_id.zfill(64)[-64:], "perceptual_hash": image_id.zfill(16)[-16:]})
        first = document["references"][0]
        reference_id = first["reference"]["image_id"]
        verification_id = first["verification_plan"][0]["image_id"]
        by_id = {row["image_id"]: row for row in assets}
        by_id[verification_id]["sha256"] = by_id[reference_id]["sha256"]
        report = validate_pixel_independence(document, assets)
        self.assertFalse(report["automatic_gate_passed"])
        self.assertTrue(report["exact_duplicates"])

    @staticmethod
    def _refresh_id(document):
        from src.tfg_phase0.remote_mapillary_campaign import canonical_bytes
        import hashlib

        payload = {key: value for key, value in document.items() if key != "selection_id"}
        document["selection_id"] = "remote-mapillary-selection-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()

    @classmethod
    def _selection_fixture(cls):
        references = []
        for index in range(26, 62):
            image = str(1000 + index)
            verify = str(2000 + index)
            references.append(
                {
                    "query_id": f"H{index:02d}",
                    "partition": "development" if index <= 37 else "test_sealed",
                    "spatial_block_id": f"B150-{index}-{index}",
                    "reference": {"image_id": image, "sequence_id": f"r-{index}"},
                    "verification_plan": [{"image_id": verify, "sequence_id": f"v-{index}"}],
                }
            )
        document = {
            "contract_version": "remote-mapillary-selection-plan-v2",
            "selection_id": "",
            "references": references,
        }
        cls._refresh_id(document)
        return copy.deepcopy(document)


if __name__ == "__main__":
    unittest.main()
