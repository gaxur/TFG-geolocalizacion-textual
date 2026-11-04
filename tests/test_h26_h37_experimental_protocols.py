import json
import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/"results/generated/mapillary/h26-h37-calibration-v1"
EXP=ROOT/"results/generated/mapillary/h26-h37-exploratory-v2"


class H26H37ExperimentalProtocolTests(unittest.TestCase):
    def test_historical_atlas_policy_remains_frozen(self):
        policy=json.loads((ART/"selected-policy.frozen.json").read_text())
        self.assertEqual(policy["status"],"frozen_before_independent_test")
        self.assertEqual(policy["model"]["model_id"],"Qwen/Qwen3-VL-8B-Instruct")
        self.assertEqual(policy["reranking"]["positive_weight"],.1)
        self.assertFalse(policy["independent_test_opened"])

    def test_exploratory_plans_forbid_gt_and_test(self):
        for path in (EXP/"pairwise-plan.json",EXP/"pairwise-visual-shortlist-plan.json",EXP/"multiview-ocr-plan.proposal.json"):
            document=json.loads(path.read_text())
            serialized=json.dumps(document,sort_keys=True)
            self.assertNotIn("H38",serialized)
            policy=document.get("policy",document.get("scope",{}))
            self.assertFalse(policy.get("selection_uses_gt",policy.get("ground_truth_used",False)))

    def test_multiview_authorization_is_exact_and_excludes_test(self):
        auth=json.loads((ROOT/"config/h26_h37_multiview_ocr_8b_authorization.request.json").read_text())
        self.assertTrue(auth["approved"])
        self.assertEqual(auth["scope"]["model"],"Qwen/Qwen3-VL-8B-Instruct")
        self.assertTrue(auth["scope"]["test_partition_excluded"])
        self.assertEqual(auth["plan_sha256"],"62000f5bbe2ed8c1e0d131f4b56f3febb0ae8c2fd6a212d9cc62cbb268b42e84")


if __name__=="__main__":unittest.main()
