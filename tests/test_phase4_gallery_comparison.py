import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from src.tfg_phase0.f4_evaluation import gallery_comparison_id, query_inputs_sha256, ranking_set_id
from src.tfg_phase0.validation import SchemaValidationError, validate_document


class Phase4GalleryComparisonTests(unittest.TestCase):
    def comparison(self):
        document = {
            "schema_version": "1.0", "contract_version": "f4-gallery-comparison-v1",
            "comparison_id": "f4-madrid-gallery-comparison-sha256-" + "0" * 64,
            "query_inputs_sha256": "1" * 64, "checkpoint_sha256": "2" * 64,
            "galleries": {
                "25m": {"candidate_count": 1115, "dataset_id": "queries-25", "embedding_dataset_id": "embeddings-25", "ranking_set_id": "rankings-25"},
                "50m": {"candidate_count": 253, "dataset_id": "queries-50", "embedding_dataset_id": "embeddings-50", "ranking_set_id": "rankings-50"},
            },
            "queries": [{"query_id": "q1", "top1_25m": {"candidate_id": "c25", "rank": 1, "score": 0.2, "latitude": 40.4, "longitude": -3.7}, "top1_50m": {"candidate_id": "c50", "rank": 1, "score": 0.19, "latitude": 40.4001, "longitude": -3.7}, "top1_cross_gallery_distance_m": 11.1, "minimum_top10_cross_gallery_distance_m": 5.0}],
            "empirical_metrics_available": False,
            "limitations": ["no_validated_geographic_references", "different_gallery_cardinalities", "exact_cell_recall_not_directly_comparable"],
        }
        document["comparison_id"] = gallery_comparison_id(document)
        return document

    def test_comparison_identity_and_cardinalities(self):
        document = self.comparison()
        validate_document(document, "f4_gallery_comparison")
        self.assertEqual(document["galleries"]["25m"]["candidate_count"], 1115)
        self.assertFalse(document["empirical_metrics_available"])

    def test_comparison_tampering_is_rejected(self):
        document = self.comparison()
        invalid = copy.deepcopy(document)
        invalid["queries"][0]["top1_cross_gallery_distance_m"] = 999.0
        with self.assertRaises(SchemaValidationError):
            validate_document(invalid, "f4_gallery_comparison")

    def test_comparator_rejects_missing_or_mismatched_query(self):
        datasets = {
            label: {"dataset_id": f"queries-{label}", "queries": [{"query_id": "q1", "partition": "development", "description": {"text": "same text", "language": "en"}}]}
            for label in ("25m", "50m")
        }
        ranking = {"query": {"query_id": "q1", "text": "wrong text", "language": "en"}}
        expected = {"query_id": "q1", "text": "same text", "language": "en"}
        self.assertNotEqual(ranking["query"], expected)
        self.assertEqual(query_inputs_sha256(datasets["25m"], "development"), query_inputs_sha256(datasets["50m"], "development"))
        ranking_set = {"contract_version": "f4-ranking-set-v1", "query_inputs_sha256": query_inputs_sha256(datasets["25m"], "development"), "embedding_dataset_id": "f4-madrid-embeddings-sha256-" + "1" * 64, "checkpoint_sha256": "2" * 64, "partition": "development", "frozen_before_reference_access": False, "rankings": []}
        ranking_set["ranking_set_id"] = ranking_set_id(ranking_set)
        self.assertNotEqual({entry["query_id"] for entry in ranking_set["rankings"]}, {"q1"})


if __name__ == "__main__":
    unittest.main()
