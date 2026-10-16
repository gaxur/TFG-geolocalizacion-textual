import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.crs import epsg25830_to_wgs84
from src.tfg_phase0.f4_evaluation import (
    assign_reference,
    evaluate_rankings,
    haversine_m,
    evaluation_id,
    query_dataset_id,
    token_jaccard,
    validate_evaluation_result,
    validate_query_dataset,
)
from src.tfg_phase0.f4_validation import F4ValidationError, load_verified_f1_catalog, load_verified_f1_50m
from src.tfg_phase0.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]


class Phase4EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_region_config(ROOT / "config/madrid.yaml")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.manifest_path = Path(cls.temporary.name) / "manifest-50m.json"
        write_manifest(build_catalog(cls.config, spacing_m=50), cls.manifest_path)
        cls.catalog = load_verified_f1_50m(cls.manifest_path, cls.config)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def query(self, query_id="q-001", partition="development", candidate_index=0):
        candidate = self.catalog.candidates[candidate_index]
        query = {
            "query_id": query_id, "location_id": f"loc-{candidate_index}", "derivation_group_id": f"group-{query_id}", "partition": partition,
            "description": {"text": f"Synthetic description {query_id}", "language": "en", "contains_coordinates": False},
            "provenance": {"source_type": "synthetic", "description": "Synthetic software fixture", "independent_environment_observation": False, "instructions_version": "fixture-v1", "collected_at_utc": None},
            "reference": {"status": "validated", "latitude": candidate.latitude, "longitude": candidate.longitude, "crs": "EPSG:4326", "capture_method": "synthetic_candidate_center", "reported_accuracy_m": 0.0, "validation_method": "fixture", "catalog_assignment": None},
            "ambiguity": {"status": "not_ambiguous", "notes": None}, "validation_status": "validated",
        }
        query["reference"]["catalog_assignment"] = assign_reference(
            candidate.latitude, candidate.longitude, self.catalog, reported_accuracy_m=0.0
        )
        return query

    def dataset(self, queries):
        document = {
            "schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "f4-madrid-queries-sha256-" + "0" * 64, "dataset_version": "fixture-v1",
            "region": {"region_id": "madrid_pilot", "bbox_wgs84": dict(self.config["region"]["bbox"])},
            "catalog": {"manifest_id": self.catalog.manifest_id, "manifest_sha256": self.catalog.sha256, "candidate_count": 253, "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"},
            "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": 0.8},
            "queries": queries,
        }
        document["dataset_id"] = query_dataset_id(document)
        return document

    def ranking(self, query, correct_rank):
        candidates = list(self.catalog.candidates[:11])
        correct = next(candidate for candidate in self.catalog.candidates if candidate.latitude == query["reference"]["latitude"] and candidate.longitude == query["reference"]["longitude"])
        candidates = [candidate for candidate in candidates if candidate.candidate_id != correct.candidate_id]
        if correct_rank is not None:
            candidates.insert(correct_rank - 1, correct)
        candidates = candidates[:10]
        return {
            "query": {"query_id": query["query_id"], "text": query["description"]["text"], "language": query["description"]["language"]},
            "effective_k": 10,
            "results": [{"rank": index, "candidate_id": candidate.candidate_id, "latitude": candidate.latitude, "longitude": candidate.longitude, "score": 1 - index / 100} for index, candidate in enumerate(candidates, 1)],
        }

    def evaluate(self, dataset, results):
        raw = json.dumps(dataset, sort_keys=True).encode()
        return evaluate_rankings(
            dataset, results, self.catalog, partition="development", dataset_sha256=hashlib.sha256(raw).hexdigest(),
            visual_dataset_id="f4-madrid-visual-sha256-" + "1" * 64, visual_manifest_sha256="2" * 64,
            embedding_dataset_id="f4-madrid-embeddings-sha256-" + "3" * 64, embedding_manifest_sha256="4" * 64,
            checkpoint_sha256="5" * 64,
            ranking_artifacts=[{"query_id": query_id, "logical_path": f"{query_id}.json", "sha256": hashlib.sha256(query_id.encode()).hexdigest()} for query_id in results],
            ranking_set_id_value="f4-madrid-rankings-sha256-" + "6" * 64,
            ranking_set_sha256="7" * 64,
            rankings_frozen_before_reference_access=False,
        )

    def test_draft_dataset_has_no_validated_references(self):
        document = json.loads((ROOT / "config/madrid_f43_query_dataset_draft.json").read_text())
        validate_document(document, "f4_query_dataset")
        audit = validate_query_dataset(document, self.catalog)
        self.assertEqual(len(document["queries"]), 3)
        self.assertEqual(sum(query["reference"]["status"] == "validated" for query in document["queries"]), 0)
        self.assertEqual(audit["cross_partition_near_duplicates"], [])

    def test_assignment_center_outside_gap_and_boundary(self):
        candidate = self.catalog.candidates[0]
        assigned = assign_reference(candidate.latitude, candidate.longitude, self.catalog)
        self.assertEqual(assigned["candidate_id"], candidate.candidate_id)
        self.assertLess(assigned["center_distance_m"], 0.001)
        outside = assign_reference(self.config["region"]["bbox"]["south"] - 0.001, candidate.longitude, self.catalog)
        self.assertEqual(outside["status"], "outside_region")
        gap = assign_reference(self.config["region"]["bbox"]["south"] + 0.000001, self.config["region"]["bbox"]["west"] + 0.000001, self.catalog)
        self.assertEqual(gap["status"], "outside_catalog_coverage")
        latitude, longitude = epsg25830_to_wgs84(candidate.center_easting_m + 25, candidate.center_northing_m)
        boundary = assign_reference(latitude, longitude, self.catalog)
        self.assertEqual(boundary["status"], "boundary_ambiguous")

    def test_haversine_is_metric_in_meters(self):
        self.assertEqual(haversine_m(40.0, -3.0, 40.0, -3.0), 0.0)
        distance = haversine_m(40.0, -3.0, 40.0, -2.999)
        self.assertGreater(distance, 80)
        self.assertLess(distance, 90)
        self.assertAlmostEqual(distance, haversine_m(40.0, -2.999, 40.0, -3.0), places=9)
        with self.assertRaises(F4ValidationError):
            haversine_m(95, 0, 0, 0)

    def test_exact_recall_at_1_5_10_and_outside(self):
        queries = [self.query(f"q-{rank}", candidate_index=index + 20) for index, rank in enumerate((1, 5, 10, 0))]
        dataset = self.dataset(queries)
        validate_query_dataset(dataset, self.catalog)
        results = {query["query_id"]: self.ranking(query, rank or None) for query, rank in zip(queries, (1, 5, 10, 0))}
        evaluation = self.evaluate(dataset, results)
        self.assertEqual(evaluation["metrics"]["exact_recall_at_k"], {"1": 0.25, "5": 0.5, "10": 0.75})
        self.assertTrue(evaluation["metrics"]["exact_available"])
        self.assertEqual(evaluation["coverage"]["exact_denominator"], 4)
        validate_document(evaluation, "f4_evaluation_result")

    def test_pending_reference_produces_no_metrics(self):
        query = self.query()
        query["reference"] = {"status": "pending", "latitude": None, "longitude": None, "crs": None, "capture_method": None, "reported_accuracy_m": None, "validation_method": None, "catalog_assignment": None}
        query["validation_status"] = "pending"
        dataset = self.dataset([query])
        evaluation = self.evaluate(dataset, {})
        self.assertFalse(evaluation["metrics"]["exact_available"])
        self.assertIsNone(evaluation["metrics"]["exact_recall_at_k"]["1"])

    def test_evaluation_partition_requires_freeze_and_location(self):
        query = self.query("q-eval", "evaluation", 50)
        dataset = self.dataset([query])
        with self.assertRaises(F4ValidationError):
            evaluate_rankings(
                dataset, {}, self.catalog, partition="evaluation", dataset_sha256="1" * 64,
                visual_dataset_id="visual", visual_manifest_sha256="2" * 64,
                embedding_dataset_id="embedding", embedding_manifest_sha256="3" * 64,
                checkpoint_sha256="4" * 64, ranking_artifacts=[],
                ranking_set_id_value="f4-madrid-rankings-sha256-" + "6" * 64,
                ranking_set_sha256="7" * 64,
                rankings_frozen_before_reference_access=False,
            )
        query["location_id"] = None
        dataset = self.dataset([query])
        with self.assertRaises(F4ValidationError):
            validate_query_dataset(dataset, self.catalog)

    def test_reference_accuracy_crossing_boundary_is_not_exactly_assignable(self):
        candidate = self.catalog.candidates[60]
        assignment = assign_reference(candidate.latitude, candidate.longitude, self.catalog, reported_accuracy_m=30.0)
        self.assertEqual(assignment["status"], "accuracy_insufficient")

    def test_validated_reference_requires_stored_assignment(self):
        query = self.query(candidate_index=65)
        query["reference"]["catalog_assignment"] = None
        dataset = self.dataset([query])
        with self.assertRaises(F4ValidationError):
            validate_query_dataset(dataset, self.catalog)

    def test_pending_reference_rejects_contradictory_state_and_metadata(self):
        query = self.query(candidate_index=66)
        query["reference"] = {"status": "pending", "latitude": None, "longitude": None, "crs": None, "capture_method": "gps", "reported_accuracy_m": None, "validation_method": None, "catalog_assignment": None}
        query["validation_status"] = "pending"
        with self.assertRaises(F4ValidationError):
            validate_query_dataset(self.dataset([query]), self.catalog)
        query["reference"]["capture_method"] = None
        query["validation_status"] = "validated"
        with self.assertRaises(F4ValidationError):
            validate_query_dataset(self.dataset([query]), self.catalog)

    def test_missing_ranking_remains_in_denominators(self):
        query = self.query(candidate_index=70)
        evaluation = self.evaluate(self.dataset([query]), {})
        self.assertEqual(evaluation["coverage"]["exact_denominator"], 1)
        self.assertEqual(evaluation["coverage"]["geographic_denominator"], 1)
        self.assertEqual(evaluation["metrics"]["exact_recall_at_k"]["1"], 0.0)
        self.assertEqual(evaluation["metrics"]["top1_error_m_conditional_on_ranking"]["missing_count"], 1)

    def test_catalog_gap_is_exact_failure_but_geographically_evaluable(self):
        query = self.query(candidate_index=70)
        latitude = self.config["region"]["bbox"]["south"] + 0.000001
        longitude = self.config["region"]["bbox"]["west"] + 0.000001
        assignment = assign_reference(latitude, longitude, self.catalog, reported_accuracy_m=0.0)
        self.assertEqual(assignment["status"], "outside_catalog_coverage")
        query["reference"].update(latitude=latitude, longitude=longitude, catalog_assignment=assignment)
        dataset = self.dataset([query])
        validate_query_dataset(dataset, self.catalog)
        ranking = {
            "query": {"query_id": query["query_id"], "text": query["description"]["text"], "language": "en"},
            "effective_k": 10,
            "results": [{"rank": index, "candidate_id": candidate.candidate_id, "latitude": candidate.latitude, "longitude": candidate.longitude, "score": 1 - index / 100} for index, candidate in enumerate(self.catalog.candidates[:10], 1)],
        }
        evaluation = self.evaluate(dataset, {query["query_id"]: ranking})
        self.assertEqual(evaluation["coverage"]["exact_denominator"], 1)
        self.assertEqual(evaluation["coverage"]["geographic_denominator"], 1)
        self.assertEqual(evaluation["metrics"]["exact_recall_at_k"]["10"], 0.0)

    def test_evaluation_identity_detects_tampering(self):
        query = self.query(candidate_index=75)
        evaluation = self.evaluate(self.dataset([query]), {query["query_id"]: self.ranking(query, 1)})
        validate_document(evaluation, "f4_evaluation_result")
        evaluation["metrics"]["exact_recall_at_k"]["1"] = 0.0
        evaluation["evaluation_id"] = evaluation_id(evaluation)
        with self.assertRaises(F4ValidationError):
            validate_evaluation_result(evaluation)

    def test_partition_leakage_and_near_duplicates_are_rejected(self):
        left = self.query("q-left", "development", 30)
        right = self.query("q-right", "evaluation", 31)
        right["location_id"] = left["location_id"]
        dataset = self.dataset([left, right])
        with self.assertRaises(F4ValidationError):
            validate_query_dataset(dataset, self.catalog)
        right["location_id"] = "other-location"
        right["description"]["text"] = left["description"]["text"] + "!"
        dataset = self.dataset([left, right])
        with self.assertRaises(F4ValidationError):
            validate_query_dataset(dataset, self.catalog)
        self.assertGreaterEqual(token_jaccard("A broad green park", "A broad, green park!"), 0.8)

    def test_ranking_query_mismatch_and_short_topk_are_rejected(self):
        query = self.query(candidate_index=40)
        dataset = self.dataset([query])
        result = self.ranking(query, 1)
        result["query"]["text"] = "different text"
        with self.assertRaises(F4ValidationError):
            self.evaluate(dataset, {query["query_id"]: result})
        result = self.ranking(query, 1)
        result["effective_k"] = 5
        result["results"] = result["results"][:5]
        with self.assertRaises(F4ValidationError):
            self.evaluate(dataset, {query["query_id"]: result})

    def test_25m_catalog_has_independent_assignment(self):
        catalog_25_path = Path(self.temporary.name) / "manifest-25m.json"
        write_manifest(build_catalog(self.config, spacing_m=25), catalog_25_path)
        catalog_25 = load_verified_f1_catalog(catalog_25_path, self.config)
        candidate_50 = self.catalog.candidates[100]
        assignment_50 = assign_reference(candidate_50.latitude, candidate_50.longitude, self.catalog, reported_accuracy_m=0.0)
        assignment_25 = assign_reference(candidate_50.latitude, candidate_50.longitude, catalog_25, reported_accuracy_m=0.0)
        self.assertEqual(assignment_50["status"], "assigned")
        self.assertNotEqual(assignment_50.get("candidate_id"), assignment_25.get("candidate_id"))
        draft = json.loads((ROOT / "config/madrid_f44_query_dataset_25m_draft.json").read_text())
        validate_query_dataset(draft, catalog_25)


if __name__ == "__main__":
    unittest.main()
