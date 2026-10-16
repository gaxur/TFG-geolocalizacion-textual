import copy
import json
from pathlib import Path
import unittest

from src.tfg_phase0.f4_robustness import aggregate_comparisons, compare_rankings, linguistic_query_set_id, robustness_result_id, validate_linguistic_query_set, validate_robustness_result
from src.tfg_phase0.f4_validation import F4ValidationError


ROOT = Path(__file__).resolve().parents[1]


def ranking(ids, scores=None):
    scores = scores or [1 - index / 100 for index in range(10)]
    return {"results": [{"candidate_id": candidate_id, "rank": index, "score": scores[index - 1], "latitude": 40.4 + index / 10000, "longitude": -3.7} for index, candidate_id in enumerate(ids, 1)]}


class Phase4RobustnessTests(unittest.TestCase):
    def test_real_query_set_contract(self):
        document = json.loads((ROOT / "config/madrid_f45_linguistic_robustness.json").read_text())
        validate_linguistic_query_set(document)
        self.assertEqual(document["query_set_id"], linguistic_query_set_id(document))
        self.assertEqual(sum(len(group["variants"]) for group in document["groups"]), 27)

    def test_query_set_rejects_tampering_and_semantic_mislabel(self):
        document = json.loads((ROOT / "config/madrid_f45_linguistic_robustness.json").read_text())
        invalid = copy.deepcopy(document)
        invalid["groups"][0]["variants"][1]["word_count"] += 1
        invalid["query_set_id"] = linguistic_query_set_id(invalid)
        with self.assertRaises(F4ValidationError): validate_linguistic_query_set(invalid)
        invalid = copy.deepcopy(document)
        contradiction = next(v for v in invalid["groups"][0]["variants"] if v["transformation"] == "contradiction")
        contradiction["semantic_relation"] = "approximately_equivalent"
        invalid["query_set_id"] = linguistic_query_set_id(invalid)
        with self.assertRaises(F4ValidationError): validate_linguistic_query_set(invalid)
        invalid = copy.deepcopy(document)
        invalid["groups"][0]["variants"][1]["removed_units"] = ["narrow"]
        invalid["query_set_id"] = linguistic_query_set_id(invalid)
        with self.assertRaises(F4ValidationError): validate_linguistic_query_set(invalid)

    def test_identical_and_disjoint_rankings(self):
        ids = [f"c{index}" for index in range(10)]
        same = compare_rankings(ranking(ids), ranking(ids))
        self.assertTrue(same["top1_agreement"])
        self.assertEqual(same["jaccard_at_5"], 1.0)
        self.assertEqual(same["top1_geographic_distance_m"], 0.0)
        disjoint = compare_rankings(ranking(ids), ranking([f"x{index}" for index in range(10)]))
        self.assertFalse(disjoint["top1_agreement"])
        self.assertEqual(disjoint["jaccard_at_10"], 0.0)
        self.assertIsNone(disjoint["mean_absolute_rank_shift_shared"])

    def test_overlap_rank_shift_and_incomplete_rejection(self):
        anchor_ids = [f"c{index}" for index in range(10)]
        variant_ids = ["c1", "c0", *anchor_ids[2:]]
        metrics = compare_rankings(ranking(anchor_ids), ranking(variant_ids))
        self.assertFalse(metrics["top1_agreement"])
        self.assertEqual(metrics["top10_overlap_count"], 10)
        self.assertAlmostEqual(metrics["mean_absolute_rank_shift_shared"], 0.2)
        with self.assertRaises(F4ValidationError): compare_rankings(ranking(anchor_ids), {"results": ranking(variant_ids)["results"][:5]})

    def test_nonfinite_score_rejected(self):
        ids = [f"c{index}" for index in range(10)]
        invalid = ranking(ids)
        invalid["results"][0]["score"] = float("nan")
        with self.assertRaises(F4ValidationError): compare_rankings(ranking(ids), invalid)

    def test_nonconsecutive_ranks_rejected(self):
        ids = [f"c{index}" for index in range(10)]
        invalid = ranking(ids)
        invalid["results"][4]["rank"] = 9
        with self.assertRaises(F4ValidationError): compare_rankings(ranking(ids), invalid)

    def test_result_tampering_rejected(self):
        metrics = compare_rankings(ranking([f"c{index}" for index in range(10)]), ranking([f"c{index}" for index in range(10)]))
        comparison = {"group_id": "g", "anchor_query_id": "a", "variant_query_id": "v", "language": "en", "transformation": "paraphrase", "semantic_relation": "approximately_equivalent", "word_count": 5, "attribute_count": 2, "length_bucket": "short_1_5", "metrics": metrics}
        document = {"schema_version": "1.0", "contract_version": "f4-linguistic-robustness-result-v1", "robustness_result_id": "f4-madrid-linguistic-robustness-sha256-" + "0" * 64, "query_set_id": "queries", "query_set_sha256": "1" * 64, "gallery": {"label": "50m"}, "checkpoint_sha256": "2" * 64, "ranking_set_id": "rankings", "ranking_set_sha256": "3" * 64, "top_k": 10, "comparisons": [comparison], "aggregates": aggregate_comparisons([comparison]), "geographic_accuracy_available": False, "limitations": ["fixture"]}
        document["robustness_result_id"] = robustness_result_id(document)
        validate_robustness_result(document)
        document["aggregates"][0]["mean_jaccard_at_10"] = 0.0
        document["robustness_result_id"] = robustness_result_id(document)
        with self.assertRaises(F4ValidationError): validate_robustness_result(document)

    def test_impossible_rank_and_negative_absolute_metrics_rejected(self):
        metrics = compare_rankings(ranking([f"c{index}" for index in range(10)]), ranking([f"c{index}" for index in range(10)]))
        comparison = {"group_id": "g", "anchor_query_id": "a", "variant_query_id": "v", "language": "en", "transformation": "paraphrase", "semantic_relation": "approximately_equivalent", "word_count": 5, "attribute_count": 2, "length_bucket": "short_1_5", "metrics": metrics}
        base = {"schema_version": "1.0", "contract_version": "f4-linguistic-robustness-result-v1", "robustness_result_id": "f4-madrid-linguistic-robustness-sha256-" + "0" * 64, "query_set_id": "queries", "query_set_sha256": "1" * 64, "gallery": {"label": "50m"}, "checkpoint_sha256": "2" * 64, "ranking_set_id": "rankings", "ranking_set_sha256": "3" * 64, "top_k": 10, "comparisons": [comparison], "aggregates": aggregate_comparisons([comparison]), "geographic_accuracy_available": False, "limitations": ["fixture"]}
        for field, value in (("anchor_top1_rank_in_variant_top10", 11), ("mean_absolute_rank_shift_shared", -1.0), ("mean_absolute_score_delta_shared", -0.1)):
            document = copy.deepcopy(base)
            document["comparisons"][0]["metrics"][field] = value
            document["robustness_result_id"] = robustness_result_id(document)
            with self.subTest(field=field), self.assertRaises(F4ValidationError):
                validate_robustness_result(document)


if __name__ == "__main__":
    unittest.main()
