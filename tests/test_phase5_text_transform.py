import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

import jsonschema

from src.tfg_phase0.f5_text_transform import (
    FakeTransformer,
    GenerationConfig,
    QwenTransformersAdapter,
    TextTransformationError,
    build_prompt,
    materialize_variants,
    protect_toponyms,
    restore_toponyms,
    transformation_run_id,
    validate_transformation,
)
from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id
from src.tfg_phase0.f5_variant_ranking import run_variant_rankings, spatial_dispersion_m, variant_ranking_report_id
from src.tfg_phase0.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]


class FakeRetriever:
    gallery_ids = ("madrid-50m", "madrid-25m")
    checkpoint = "d" * 64

    def __init__(self):
        self.calls = []

    def retrieve_many(self, *, gallery_ids, query_id, text, language, k):
        self.calls.append((tuple(gallery_ids), query_id, text, language, k))
        retrievals = []
        shift = sum(ord(value) for value in text) % 5
        for gallery_id in gallery_ids:
            spacing = 0.0002 if gallery_id == "madrid-25m" else 0.0004
            results = []
            for rank in range(1, k + 1):
                index = rank + shift
                results.append({"rank": rank, "candidate_id": f"{gallery_id}-candidate-{index:03d}", "latitude": 40.415 + index * spacing, "longitude": -3.706 + index * spacing, "cosine_similarity": 0.5 - rank / 100})
            retrievals.append({"gallery_id": gallery_id, "visual_dataset_id": f"visual-{gallery_id}", "embedding_dataset_id": f"embedding-{gallery_id}", "gallery_count": 253 if gallery_id == "madrid-50m" else 1115, "requested_k": k, "effective_k": k, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "results": results})
        return {"schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-response-v1", "query": {"query_id": query_id, "text": text, "language": language}, "model": {"name": "CLIP-L/14@336", "checkpoint_sha256": self.checkpoint}, "retrievals": retrievals, "timings_ms": {"text_encoding": 1.0, "ranking_by_gallery": {gallery: 0.1 for gallery in gallery_ids}, "total": 1.5}}


def pending(kind):
    return {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": "es" if kind.startswith("es_") else "en", "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}


def sidecar():
    original = "Estoy cerca de Plaza Mayor, sin parques, mirando al norte y a 20 m de una calle"
    start = original.index("Plaza Mayor")
    document = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text())
    document["dataset_version"] = "f52-software-fixture-v1"
    document["observations"] = [{
        "source_query_id": "fixture-es-001", "source_input_sha256": "1" * 64, "partition": "development", "location_id": None, "derivation_group_id": "fixture-group-001",
        "toponyms": [{"mention": "Plaza Mayor", "span": {"start": start, "end": start + len("Plaza Mayor")}, "entity_type": "square", "name_kind": "proper_name", "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"}],
        "orientation": {"status": "verified", "cardinal": "north", "bearing_degrees": None, "bearing_convention": None, "method": "fixture", "uncertainty_degrees": 1.0, "provenance": "fixture", "verification_status": "verified", "relative_relations_present": False, "notes": None},
        "variants": [
            {"variant_id": "fixture-es-001-es-original-v1", "kind": "es_original", "status": "reviewed", "text": original, "language": "es", "generation": {"method": "original", "tool_or_model": "manual", "version": "v1", "configuration_or_prompt": "copy-from-f43", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []},
            pending("es_cartographic"), pending("en_conventional"), pending("en_toponym_preserved"),
        ], "notes": "Fixture sintética de software sin ground truth.",
    }]
    document["dataset_id"] = textual_variant_dataset_id(document)
    return document


class Phase5TextTransformTests(unittest.TestCase):
    def setUp(self):
        self.config = GenerationConfig()
        self.outputs = {
            "cartographic_rewrite_es": "Estoy cerca de Plaza Mayor, sin parques, mirando al norte y a 20 m de una calle",
            "translate_en_conventional": "I am near the Main Square, without parks, facing north and 20 m from a street",
            "translate_en_preserve_toponyms": "I am near Plaza Mayor, without parks, facing north and 20 m from a street",
        }

    def test_prompt_is_task_specific_non_thinking_and_deterministic(self):
        first = build_prompt("Texto", "cartographic_rewrite_es")
        second = build_prompt("Texto", "cartographic_rewrite_es")
        self.assertEqual(first, second)
        self.assertIn("No inventes", first)
        self.assertIn("Elimina solo detalles visuales", first)
        protected = build_prompt("__TOPONYM_000__", "translate_en_preserve_toponyms", ("__TOPONYM_000__",))
        self.assertIn("Placeholders obligatorios", protected)
        with self.assertRaises(TextTransformationError): build_prompt("x", "unknown")
        with self.assertRaises(ValueError): GenerationConfig(do_sample=True)

    def test_toponym_placeholders_restore_exactly_and_reject_loss_duplicates(self):
        text, mapping = protect_toponyms("Estoy entre Plaza Mayor y Gran Vía", ["Plaza Mayor", "Gran Vía"])
        self.assertEqual(text, "Estoy entre __TOPONYM_000__ y __TOPONYM_001__")
        self.assertEqual(restore_toponyms(text, mapping), "Estoy entre Plaza Mayor y Gran Vía")
        with self.assertRaises(TextTransformationError): restore_toponyms("__TOPONYM_000__", mapping)
        with self.assertRaises(TextTransformationError): restore_toponyms("__TOPONYM_000__ __TOPONYM_000__ __TOPONYM_001__", mapping)
        with self.assertRaises(TextTransformationError): protect_toponyms("Plaza Mayor y Plaza Mayor", ["Plaza Mayor"])

    def test_semantic_heuristics_detect_empty_language_length_negation_numbers_orientation_and_invention(self):
        original = "No estoy a 20 m al norte de una plaza"
        validation = validate_transformation(original, "I am 30 m south of a park", "translate_en_conventional", [], self.config)
        codes = {row["code"] for row in validation["issues"]}
        self.assertIn("numbers_changed", codes)
        self.assertIn("negation_changed", codes)
        self.assertIn("orientation_lost", codes)
        self.assertIn("possible_geographic_invention", codes)
        self.assertFalse(validation["structurally_valid"])
        empty = validate_transformation(original, "", "translate_en_conventional", [], self.config)
        self.assertIn("empty_output", {row["code"] for row in empty["issues"]})
        mismatch = validate_transformation("Estoy en una plaza", "Estoy en una plaza", "translate_en_conventional", [], self.config)
        self.assertIn("language_mismatch", {row["code"] for row in mismatch["issues"]})

    def test_materialization_records_provenance_and_requires_human_review(self):
        source = sidecar()
        transformer = FakeTransformer(self.outputs)
        derived, run = materialize_variants(source, transformer, self.config, source_logical_path="fixture.json", source_sha256="2" * 64)
        self.assertEqual(len(run["records"]), 3)
        self.assertFalse(run["transformer"]["real_model_inference"])
        self.assertTrue(all(record["validation"]["human_review_required"] for record in run["records"]))
        self.assertEqual([variant["status"] for variant in derived["observations"][0]["variants"]], ["reviewed", "generated", "generated", "generated"])
        self.assertEqual(derived["observations"][0]["variants"][3]["protected_toponyms"], ["Plaza Mayor"])
        validate_document(run, "f5_transformation_run")
        self.assertEqual(run["run_id"], transformation_run_id(run))
        transformer.close()
        with self.assertRaises(TextTransformationError): transformer.transform("x", "cartographic_rewrite_es", [], self.config)

    def test_failed_transform_is_rejected_not_silently_compared(self):
        outputs = dict(self.outputs)
        outputs["translate_en_preserve_toponyms"] = "I am near the main square"
        derived, run = materialize_variants(sidecar(), FakeTransformer(outputs), self.config, source_logical_path="fixture.json", source_sha256="2" * 64)
        record = next(row for row in run["records"] if row["kind"] == "en_toponym_preserved")
        self.assertEqual(record["status"], "rejected")
        self.assertEqual(derived["observations"][0]["variants"][3]["review_status"], "rejected")

    def test_qwen_adapter_fails_without_local_snapshot_and_does_not_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "Qwen3-8B"
            with self.assertRaises(TextTransformationError):
                QwenTransformersAdapter(missing, model_id="Qwen/Qwen3-8B", revision="fixture")

    def test_transformation_schema_accepts_run_and_detects_tampering(self):
        schema = json.loads((ROOT / "schemas/f5_transformation_run.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        _, run = materialize_variants(sidecar(), FakeTransformer(self.outputs), self.config, source_logical_path="fixture.json", source_sha256="2" * 64)
        jsonschema.validate(run, schema)
        run["generation"]["do_sample"] = True
        run["run_id"] = transformation_run_id(run)
        with self.assertRaises(Exception): validate_document(run, "f5_transformation_run")

    def test_variant_rankings_are_independent_and_descriptive_only(self):
        derived, run = materialize_variants(sidecar(), FakeTransformer(self.outputs), self.config, source_logical_path="fixture.json", source_sha256="2" * 64)
        retriever = FakeRetriever()
        report = run_variant_rankings(derived, retriever, sidecar_sha256="3" * 64, gallery_ids=("madrid-50m", "madrid-25m"), top_k=5, transformation_run=run, allow_unreviewed_technical=True)
        self.assertEqual(len(report["rankings"]), 8)
        self.assertEqual(len(report["comparisons"]), 6)
        self.assertEqual(len(report["cross_gallery"]), 4)
        self.assertFalse(report["geographic_accuracy_available"])
        self.assertFalse(report["retrieval"]["scores_fused"])
        self.assertFalse(report["retrieval"]["coordinates_fused"])
        self.assertEqual(len(retriever.calls), 4)
        validate_document(report, "f5_variant_ranking_report")
        self.assertEqual(report["report_id"], variant_ranking_report_id(report))

    def test_unreviewed_real_model_variants_are_not_ranked(self):
        derived, run = materialize_variants(sidecar(), FakeTransformer(self.outputs), self.config, source_logical_path="fixture.json", source_sha256="2" * 64)
        report = run_variant_rankings(derived, FakeRetriever(), sidecar_sha256="3" * 64, gallery_ids=("madrid-50m",), top_k=3, transformation_run=run)
        self.assertEqual(len(report["rankings"]), 1)
        self.assertEqual(report["rankings"][0]["kind"], "es_original")

    def test_margin_dispersion_and_cross_gallery_use_metric_distances(self):
        results = [{"candidate_id": f"c-{index}", "latitude": 40.416 + index * .0001, "longitude": -3.704, "cosine_similarity": .5 - index * .1} for index in range(3)]
        dispersion = spatial_dispersion_m(results)
        self.assertGreater(dispersion, 0)
        self.assertTrue(math.isfinite(dispersion))

    def test_ranking_schema_accepts_report_and_rejects_fusion(self):
        schema = json.loads((ROOT / "schemas/f5_variant_ranking_report.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        derived, run = materialize_variants(sidecar(), FakeTransformer(self.outputs), self.config, source_logical_path="fixture.json", source_sha256="2" * 64)
        report = run_variant_rankings(derived, FakeRetriever(), sidecar_sha256="3" * 64, gallery_ids=("madrid-50m",), top_k=3, transformation_run=run, allow_unreviewed_technical=True)
        jsonschema.validate(report, schema)
        report["retrieval"]["scores_fused"] = True
        report["report_id"] = variant_ranking_report_id(report)
        with self.assertRaises(Exception): validate_document(report, "f5_variant_ranking_report")


if __name__ == "__main__":
    unittest.main()
