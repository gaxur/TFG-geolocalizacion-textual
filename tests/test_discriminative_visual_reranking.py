import unittest

from src.tfg_phase0.discriminative_visual_reranking import aggregate_discriminative_evidence, apply_discriminative_reranking, freeze_discriminative_policy


def claim(claim_id="k"):
    return {"claim_id":claim_id,"specificity":"distinctive","requires_orientation":False}


def baseline():
    return [{"rank":index,"candidate_id":f"c{index}","latitude":40.0,"longitude":-3.0,"cosine_similarity":1-index/1000} for index in range(1,51)]


class DiscriminativeVisualRerankingTests(unittest.TestCase):
    def test_exclusive_inside_support_outweighs_shared_ambiguous_support(self):
        associations=[{"candidate_id":"c10","image_id":"shared","sequence_id":"s1","classification":"spatially_ambiguous","competing_candidate_count":4},{"candidate_id":"c11","image_id":"shared","sequence_id":"s1","classification":"spatially_ambiguous","competing_candidate_count":4},{"candidate_id":"c11","image_id":"exclusive","sequence_id":"s2","classification":"camera_inside_candidate","competing_candidate_count":1}]
        verdicts=[{"status":"valid","candidate_id":"c10","image_id":"shared","claim_id":"k","verdict":"supported"},{"status":"valid","candidate_id":"c11","image_id":"shared","claim_id":"k","verdict":"supported"},{"status":"valid","candidate_id":"c11","image_id":"exclusive","claim_id":"k","verdict":"supported"}]
        aggregate=aggregate_discriminative_evidence([claim()],associations,verdicts,candidate_ids=[f"c{i}" for i in range(1,51)])
        rows={row["candidate_id"]:row for row in aggregate["candidates"]}
        self.assertGreater(rows["c11"]["positive_evidence"],rows["c10"]["positive_evidence"])

    def test_redundant_shared_support_does_not_force_promotion(self):
        associations=[];verdicts=[]
        for candidate_id in ("c10","c11"):
            associations.append({"candidate_id":candidate_id,"image_id":"shared","sequence_id":"s","classification":"spatially_ambiguous","competing_candidate_count":8})
            verdicts.append({"status":"valid","candidate_id":candidate_id,"image_id":"shared","claim_id":"k","verdict":"supported"})
        aggregate=aggregate_discriminative_evidence([claim()],associations,verdicts,candidate_ids=[f"c{i}" for i in range(1,51)])
        result=apply_discriminative_reranking(baseline(),aggregate,freeze_discriminative_policy())
        self.assertEqual(result["final_top10_candidate_ids"],[f"c{i}" for i in range(1,11)])

    def test_verified_contradiction_can_penalize_but_unverifiable_is_neutral(self):
        associations=[{"candidate_id":"c1","image_id":"negative","sequence_id":"s1","classification":"camera_inside_candidate"},{"candidate_id":"c2","image_id":"unknown","sequence_id":"s2","classification":"camera_inside_candidate"}]
        verdicts=[{"status":"valid","candidate_id":"c1","image_id":"negative","claim_id":"k","verdict":"contradicted"},{"status":"valid","candidate_id":"c2","image_id":"unknown","claim_id":"k","verdict":"unverifiable"}]
        aggregate=aggregate_discriminative_evidence([claim()],associations,verdicts,candidate_ids=[f"c{i}" for i in range(1,51)])
        result=apply_discriminative_reranking(baseline(),aggregate,freeze_discriminative_policy(positive_weight=0,contradiction_weight=.2))
        decisions={row["candidate_id"]:row for row in result["candidate_decisions"]}
        self.assertLess(decisions["c1"]["visual_spatial_modifier"],0);self.assertEqual(decisions["c2"]["visual_spatial_modifier"],0)

    def test_missing_evidence_exactly_preserves_ct2l(self):
        aggregate=aggregate_discriminative_evidence([claim()],[],[],candidate_ids=[f"c{i}" for i in range(1,51)])
        result=apply_discriminative_reranking(baseline(),aggregate,freeze_discriminative_policy())
        self.assertEqual(result["full_experimental_order"],[f"c{i}" for i in range(1,51)])

    def test_ground_truth_rejected(self):
        base=baseline();base[0]["ground_truth"]=True
        with self.assertRaisesRegex(ValueError,"GT"):
            apply_discriminative_reranking(base,{"candidates":[]},freeze_discriminative_policy())


if __name__=="__main__":unittest.main()
