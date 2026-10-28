import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class H16H23ProtocolTests(unittest.TestCase):
    def test_protocol_freezes_top50_and_blocks_all_gates(self):
        if not (ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json").exists():
            self.skipTest("fixture local Top-50 ausente")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "protocol.json"
            subprocess.run([str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/freeze_h16_h23_protocol.py"), "--output", str(output)], cwd=ROOT, check=True, capture_output=True, text=True)
            document = json.loads(output.read_text())
            self.assertEqual(document["scope"]["candidate_depth_primary"], 50)
            self.assertEqual(document["scope"]["variant"], "en_cartographic")
            self.assertEqual(document["promotion_policy"]["promotion"]["opened_blocks"], [[11, 20], [21, 50]])
            self.assertEqual(document["promotion_policy"]["visual_policy"]["negative_weight"], 0)
            self.assertEqual(document["evidence"]["minimum_positive_evidence"], 0.01)
            self.assertTrue(all(value in {"pending", "blocked"} for value in document["gates"].values()))

    def test_authorization_template_cannot_open_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/acquire_h16_h23_assets.py"), "--plan", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/acquisition-plan.json"), "--authorization", str(ROOT / "config/h16_h23_mapillary_authorization.template.json"), "--output", str(Path(temporary) / "manifest.json")], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(temporary) / "manifest.json").exists())

    def test_preflight_passes_identity_checks_but_blocks_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "preflight.json"
            result = subprocess.run([str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/preflight_h16_h23_experiment.py"), "--protocol", str(ROOT / "config/h16_h23_top50_experiment.json"), "--fixture", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json"), "--plan", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/acquisition-plan.json"), "--authorization", str(ROOT / "config/h16_h23_mapillary_authorization.template.json"), "--output", str(output)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            document = json.loads(output.read_text())
            self.assertTrue(all(document["checks"].values()))
            self.assertFalse(document["ready_for_acquisition"])
            self.assertFalse(document["ready_for_inference"])
            self.assertFalse(document["ready_for_evaluation"])

    def test_pending_canonical_review_does_not_open_claim_gate(self):
        review = ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/reviews/h16-h23-top50-claims-review.json"
        if not review.exists():
            self.skipTest("revisión canónica local ausente")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "preflight.json"
            subprocess.run([str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/preflight_h16_h23_experiment.py"), "--protocol", str(ROOT / "config/h16_h23_top50_experiment.json"), "--fixture", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json"), "--plan", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/acquisition-plan.json"), "--claim-review", str(review), "--authorization", str(ROOT / "config/h16_h23_mapillary_authorization.template.json"), "--output", str(output)], cwd=ROOT, check=True, capture_output=True, text=True)
            document = json.loads(output.read_text())
            self.assertFalse(document["gates"]["claims_review"])


if __name__ == "__main__":
    unittest.main()
