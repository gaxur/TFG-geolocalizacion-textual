import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.freeze_h16_h23_selector_manifests import task_fingerprint


ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"results/generated/mapillary/h16-h23-multicandidate-top50-v2"


class SelectorManifestReuseTests(unittest.TestCase):
    def test_task_identity_changes_with_model_image_or_claim(self):
        claim={"claim_id":"c","kind":"object_presence","value":{"object_type":"x"},"evidence":{"text":"x","span":{"start":0,"end":1}},"source_text_sha256":"0"*64,"specificity":"distinctive","requires_ocr":False,"requires_orientation":False}
        left=task_fingerprint("qwen3-vl-2b","1"*64,claim,policy_unverifiable=False)
        self.assertNotEqual(left,task_fingerprint("qwen3-vl-8b","1"*64,claim,policy_unverifiable=False))
        self.assertNotEqual(left,task_fingerprint("qwen3-vl-2b","2"*64,claim,policy_unverifiable=False))
        changed=json.loads(json.dumps(claim));changed["value"]["object_type"]="y"
        self.assertNotEqual(left,task_fingerprint("qwen3-vl-2b","1"*64,changed,policy_unverifiable=False))

    def test_local_manifests_are_deterministic_and_not_authorized(self):
        required=BASE/"metadata-selector-comparison-v1.json"
        if not required.exists():self.skipTest("artefactos locales ausentes")
        with tempfile.TemporaryDirectory() as temporary:
            command=[str(ROOT/".venv-geo/bin/python"),str(ROOT/"scripts/freeze_h16_h23_selector_manifests.py"),"--comparison",str(required),"--fixture",str(BASE/"fixture.json"),"--inventory",str(ROOT/"results/generated/mapillary/d004-buffer100m/inventory.json"),"--adaptive-config",str(ROOT/"config/h16_h23_adaptive_visual_acquisition_v1.json"),"--partial-assets",str(BASE/"partial-existing-assets.json"),"--run-2b",str(BASE/"partial-qwen3-vl-2b-run-v4.json"),"--run-8b",str(BASE/"partial-qwen3-vl-8b-run-v4.json"),"--output-root",temporary]
            subprocess.run(command,cwd=ROOT,check=True,capture_output=True,text=True)
            frozen=ROOT/"results/generated/mapillary/h16-h23-selector-comparison-v1"
            for name in ("coverage_adaptive-manifest.json","geometric_adaptive-manifest.json","paired-reuse-plan.json"):
                self.assertEqual((Path(temporary)/name).read_bytes(),(frozen/name).read_bytes())
            paired=json.loads((Path(temporary)/"paired-reuse-plan.json").read_text())
            self.assertFalse(paired["authorization"]["approved"]);self.assertEqual(paired["asset_sets"]["union"],511);self.assertEqual(paired["download_plan"]["pending_union"],474)

    def test_associations_and_assets_are_unique(self):
        path=ROOT/"results/generated/mapillary/h16-h23-selector-comparison-v1/coverage_adaptive-manifest.json"
        if not path.exists():self.skipTest("manifest local ausente")
        document=json.loads(path.read_text());asset_ids=document["image_ids"];keys=[(row["query_id"],row["candidate_id"],row["image_id"]) for row in document["associations"]]
        self.assertEqual(len(asset_ids),len(set(asset_ids)));self.assertEqual(len(keys),len(set(keys)));self.assertEqual(len(document["candidate_slots"]),100)


if __name__=="__main__":unittest.main()
