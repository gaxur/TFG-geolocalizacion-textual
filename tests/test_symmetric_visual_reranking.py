import unittest

from src.tfg_phase0.symmetric_visual_reranking import SymmetricRerankingError, apply_symmetric_reranking, freeze_symmetric_policy, restore_baseline


class SymmetricRerankingTests(unittest.TestCase):
    def baseline(self, equal=False):
        return [{"rank": index, "candidate_id": f"c{index}", "latitude": 40.0, "longitude": -3.0, "cosine_similarity": 1.0 if equal else 1-index/1000} for index in range(1,51)]

    def test_same_evidence_same_modifier_inside_and_outside_top10(self):
        aggregate={"candidates":[{"candidate_id":"c10","positive_evidence":.5,"valid_verdicts":2,"coverage_status":"available"},{"candidate_id":"c11","positive_evidence":.5,"valid_verdicts":2,"coverage_status":"available"}]}
        doc=apply_symmetric_reranking(self.baseline(),aggregate,freeze_symmetric_policy())
        rows={row["candidate_id"]:row for row in doc["candidate_decisions"]}
        self.assertEqual(rows["c10"]["visual_modifier"],rows["c11"]["visual_modifier"])

    def test_missing_and_no_coverage_are_neutral(self):
        aggregate={"candidates":[{"candidate_id":"c11","positive_evidence":1,"valid_verdicts":5,"coverage_status":"no_coverage"}]}
        doc=apply_symmetric_reranking(self.baseline(),aggregate,freeze_symmetric_policy())
        self.assertEqual(doc["full_experimental_order"],[f"c{i}" for i in range(1,51)])

    def test_equal_final_scores_keep_baseline_rank(self):
        doc=apply_symmetric_reranking(self.baseline(equal=True),{"candidates":[]},freeze_symmetric_policy())
        self.assertEqual(doc["full_experimental_order"],[f"c{i}" for i in range(1,51)])

    def test_negative_evidence_never_changes_modifier(self):
        aggregate={"candidates":[{"candidate_id":"c11","positive_evidence":.5,"negative_evidence":1,"valid_verdicts":2,"coverage_status":"available"}]}
        doc=apply_symmetric_reranking(self.baseline(),aggregate,freeze_symmetric_policy())
        row=next(row for row in doc["candidate_decisions"] if row["candidate_id"]=="c11")
        self.assertEqual(row["visual_modifier"],.1);self.assertFalse(row["negative_evidence_used"])

    def test_disabled_and_restore_preserve_baseline(self):
        base=self.baseline();doc=apply_symmetric_reranking(base,{"candidates":[]},freeze_symmetric_policy(enabled=False));self.assertEqual(doc["final_top10_candidate_ids"],[f"c{i}" for i in range(1,11)]);self.assertEqual(restore_baseline(doc),base)

    def test_duplicate_foreign_and_invalid_evidence_rejected(self):
        base=self.baseline()
        with self.assertRaises(SymmetricRerankingError):apply_symmetric_reranking(base,{"candidates":[{"candidate_id":"x","positive_evidence":.5}]},freeze_symmetric_policy())
        with self.assertRaises(SymmetricRerankingError):apply_symmetric_reranking(base,{"candidates":[{"candidate_id":"c1","positive_evidence":2,"valid_verdicts":1,"coverage_status":"available"}]},freeze_symmetric_policy())

    def test_regression_documents_old_asymmetry(self):
        base=self.baseline();aggregate={"candidates":[{"candidate_id":"c10","positive_evidence":1,"valid_verdicts":2,"coverage_status":"available"},{"candidate_id":"c11","positive_evidence":1,"valid_verdicts":2,"coverage_status":"available"}]};doc=apply_symmetric_reranking(base,aggregate,freeze_symmetric_policy());rows={row["candidate_id"]:row for row in doc["candidate_decisions"]};self.assertEqual(rows["c10"]["visual_modifier"],rows["c11"]["visual_modifier"])

    def test_ground_truth_is_rejected(self):
        base=self.baseline();base[0]["ground_truth"]=True
        with self.assertRaises(ValueError):apply_symmetric_reranking(base,{"candidates":[]},freeze_symmetric_policy())


if __name__=="__main__":unittest.main()
