#!/usr/bin/env python3
"""Smoke técnico F5.2 con dobles; no valida Qwen ni precisión geográfica."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f5_text_transform import FakeTransformer, GenerationConfig, materialize_variants
from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id
from src.tfg_phase0.f5_variant_ranking import run_variant_rankings
from src.tfg_phase0.validation import validate_document


class SmokeRetriever:
    gallery_ids = ("madrid-50m", "madrid-25m")

    def retrieve_many(self, *, gallery_ids, query_id, text, language, k):
        retrievals = []
        for gallery in gallery_ids:
            results = [{"rank": rank, "candidate_id": f"{gallery}-technical-{rank}", "latitude": 40.415 + rank * .0001, "longitude": -3.705 + rank * .0001, "cosine_similarity": .5 - rank * .01} for rank in range(1, k + 1)]
            retrievals.append({"gallery_id": gallery, "visual_dataset_id": "technical", "embedding_dataset_id": "technical", "gallery_count": 253 if gallery.endswith("50m") else 1115, "requested_k": k, "effective_k": k, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "results": results})
        return {"schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-response-v1", "query": {"query_id": query_id, "text": text, "language": language}, "model": {"name": "fake", "checkpoint_sha256": "d" * 64}, "retrievals": retrievals, "timings_ms": {"text_encoding": .1, "ranking_by_gallery": {gallery: .1 for gallery in gallery_ids}, "total": .3}}


def main() -> int:
    original = "Estoy cerca de Plaza Mayor, sin parques y mirando al norte"
    start = original.index("Plaza Mayor")
    sidecar = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text())
    sidecar["dataset_version"] = "f52-technical-smoke-v1"
    pending = lambda kind, lang: {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": lang, "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
    sidecar["observations"] = [{"source_query_id": "technical-smoke", "source_input_sha256": "1" * 64, "partition": "development", "location_id": None, "derivation_group_id": "technical-smoke", "toponyms": [{"mention": "Plaza Mayor", "span": {"start": start, "end": start + 12}, "entity_type": "square", "name_kind": "proper_name", "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"}], "orientation": {"status": "verified", "cardinal": "north", "bearing_degrees": None, "bearing_convention": None, "method": "technical_fixture", "uncertainty_degrees": 1.0, "provenance": "technical_fixture", "verification_status": "verified", "relative_relations_present": False, "notes": None}, "variants": [{"variant_id": "technical-smoke-es-original", "kind": "es_original", "status": "reviewed", "text": original, "language": "es", "generation": {"method": "original", "tool_or_model": "manual", "version": "v1", "configuration_or_prompt": "technical", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}, pending("es_cartographic", "es"), pending("en_conventional", "en"), pending("en_toponym_preserved", "en")], "notes": "technical smoke without ground truth"}]
    sidecar["dataset_id"] = textual_variant_dataset_id(sidecar)
    outputs = {"cartographic_rewrite_es": original, "translate_en_conventional": "I am near the Main Square, without parks and facing north", "translate_en_preserve_toponyms": "I am near Plaza Mayor, without parks and facing north"}
    derived, run = materialize_variants(sidecar, FakeTransformer(outputs), GenerationConfig(), source_logical_path="technical.json", source_sha256="2" * 64)
    report = run_variant_rankings(derived, SmokeRetriever(), sidecar_sha256="3" * 64, gallery_ids=("madrid-50m", "madrid-25m"), top_k=3, transformation_run=run, allow_unreviewed_technical=True)
    validate_document(run, "f5_transformation_run")
    validate_document(report, "f5_variant_ranking_report")
    print(json.dumps({"status": "pass", "technical_fake_only": True, "real_qwen_inference": False, "rankings": len(report["rankings"]), "comparisons": len(report["comparisons"]), "geographic_accuracy_available": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
