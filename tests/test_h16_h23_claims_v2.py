import hashlib
import json
import unittest
from pathlib import Path

from src.tfg_phase0.visual_reranking import compile_atomic_claims_v2, verdict_only_prompt


ROOT=Path(__file__).resolve().parents[1]


class H16H23ClaimsV2Tests(unittest.TestCase):
    def test_versioned_h16_text_and_ranking_lineage(self):
        plan_path=ROOT/"results/generated/f5/h16-h23-corrected-v2/variant-plan.json";ranking_path=ROOT/"results/generated/f5/h16-h23-corrected-v2/rankings.json"
        if not plan_path.exists() or not ranking_path.exists():self.skipTest("linaje v2 local ausente")
        plan=json.loads(plan_path.read_text());rankings=json.loads(ranking_path.read_text());h16=next(row for row in plan["controls"] if row["query_id"]=="H16")
        self.assertIn("dark altarpiece",h16["text"]);self.assertNotIn("dark choir",h16["text"]);self.assertEqual(h16["text_sha256"],hashlib.sha256(h16["text"].encode()).hexdigest());self.assertEqual(rankings["variant_plan_id"],plan["variant_plan_id"]);self.assertEqual(rankings["checkpoint_sha256"],"d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d")

    def test_v2_claim_is_compatible_with_vlm_prompt(self):
        document=compile_atomic_claims_v2("In front of me is a dark altarpiece.")
        for claim in document["claims"]:
            prompt=verdict_only_prompt(claim)
            self.assertIn("Afirmación:",prompt)
            self.assertIn(claim["kind"],prompt)

    def test_v2_fixture_uses_new_ranking_and_claim_contract(self):
        path=ROOT/"results/generated/mapillary/h16-h23-multicandidate-top50-v2/fixture.json"
        if not path.exists():self.skipTest("fixture v2 ausente")
        fixture=json.loads(path.read_text());self.assertEqual(fixture["contract_version"],"h16-h23-multicandidate-fixture-v2");self.assertTrue(all(row["claims"]["contract_version"]=="visual-atomic-claims-v2" for row in fixture["queries"]));self.assertEqual([len(row["claims"]["claims"]) for row in fixture["queries"]],[19,10])


if __name__=="__main__":unittest.main()
