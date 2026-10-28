#!/usr/bin/env python3
"""Congela el protocolo Top-50 H16/H23 sin cargar referencias geográficas."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
from src.tfg_phase0.topn_promotion import freeze_policy
from src.tfg_phase0.visual_reranking import canonical_bytes, verdict_only_prompt, verdict_only_schema
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS


EXPECTED_RESERVE_ID = "h11-h25-topn-sha256-92c2ecc639f4e4d650e55be0b7376f73f06279a23c4f59e210a812a14ad43c14"
EXPECTED_RANKINGS_SHA256 = "29bcea393be3048104d3920c1d6ff399aa6f247e49a38bbe34466af579355ed4"
EXPECTED_PLAN_ID = "h16-h23-acquisition-sha256-c5fabcc68d2066024c8058837d01e7401e473c957173caa53c206c713a331a4d"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rankings", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/top100/rankings.json")
    parser.add_argument("--fixture", type=Path, default=ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json")
    parser.add_argument("--acquisition-plan", type=Path, default=ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/acquisition-plan.json")
    parser.add_argument("--output", type=Path, default=ROOT / "config/h16_h23_top50_experiment.json")
    args = parser.parse_args()
    rankings = json.loads(args.rankings.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    acquisition = json.loads(args.acquisition_plan.read_text(encoding="utf-8"))
    reject_ground_truth(rankings, path="rankings")
    reject_ground_truth(fixture, path="fixture")
    if rankings.get("reserve_id") != EXPECTED_RESERVE_ID or digest(args.rankings) != EXPECTED_RANKINGS_SHA256:
        raise ValueError("Top-100 no corresponde a la reserva congelada")
    if acquisition.get("plan_id") != EXPECTED_PLAN_ID or acquisition.get("fixture_id") != fixture.get("fixture_id"):
        raise ValueError("plan Top-50 o fixture incompatible")
    if acquisition["authorization"]["downloads_permitted"] is not False:
        raise ValueError("el plan base debe permanecer no autorizado")
    if fixture["policy"] != {"query_ids": ["H16", "H23"], "kind": "en_cartographic", "gallery_id": "madrid-50m", "complete_symmetric_rank_block": [1, 50], "maximum_distance_m": 100, "maximum_images_per_candidate": 8, "ground_truth_used": False, "coverage_used_for_candidate_selection": False, "no_coverage_is_neutral": True, "failed_download_is_neutral": True, "unverifiable_is_neutral": True, "negative_evidence_enabled": False}:
        raise ValueError("política de fixture Top-50 no coincide con el protocolo")
    promotion = freeze_policy(enabled=True, input_top_n=50, output_top_k=10, positive_weight=0.2, minimum_positive_evidence=0.01, minimum_valid_verdicts=1, max_promotions=10, opened_blocks=((11, 20), (21, 50)))
    prompt_example = verdict_only_prompt({"kind": "object_presence", "value": {"object_type": "example"}, "evidence": {"text": "example"}})
    document = {
        "schema_version": "1.0",
        "contract_version": "h16-h23-top50-experiment-protocol-v1",
        "protocol_id": "",
        "status": "frozen_blocked_pending_gates",
        "scope": {"query_ids": ["H16", "H23"], "development_only": True, "variant": "en_cartographic", "gallery_id": "madrid-50m", "candidate_depth_primary": 50, "candidate_depth_secondary": 20, "output_top_k": 10},
        "inputs": {"reserve_id": EXPECTED_RESERVE_ID, "rankings_sha256": EXPECTED_RANKINGS_SHA256, "fixture_id": fixture["fixture_id"], "fixture_sha256": digest(args.fixture), "acquisition_plan_id": EXPECTED_PLAN_ID, "acquisition_plan_sha256": digest(args.acquisition_plan)},
        "image_policy": fixture["policy"],
        "claims": {"source_variant": "en_cartographic", "required_source_hashes": {row["query_id"]: row["text_sha256"] for row in fixture["queries"]}, "human_review_required": True, "orientation_claims_without_comparable_heading": "policy_unverifiable"},
        "models": {key: value for key, value in SUPPORTED_LOCAL_MODELS.items() if key in {"qwen3-vl-2b", "qwen3-vl-8b"}},
        "inference": {"prompt_version": "visual-verdict-only-v4", "prompt_template_sha256": hashlib.sha256(prompt_example.encode()).hexdigest(), "output_schema": verdict_only_schema(), "output_schema_sha256": hashlib.sha256(canonical_bytes(verdict_only_schema())).hexdigest(), "do_sample": False, "max_new_tokens": 24, "dtype": "bfloat16", "attention": "sdpa", "same_assets_claims_and_policy_for_models": True},
        "evidence": {"sequence_deduplication": True, "generic_weight": 0.5, "distinctive_weight": 1.0, "conflict_is_neutral": True, "unverifiable_is_neutral": True, "missing_or_failed_is_neutral": True, "negative_evidence_enabled": False, "minimum_positive_evidence": 0.01, "threshold_role": "technical_nonzero_guard_not_fitted_on_h16_h23"},
        "promotion_policy": promotion,
        "metrics": {"distance_top1_m": True, "geo_recall_thresholds_m": [50, 100], "geo_recall_ks": [1, 5, 10], "rank_changes": True, "correct_and_incorrect_promotions": True, "regressions": True, "visual_coverage": True, "neutral_candidates": True, "paired_model_difference": True},
        "outcome_rules": {"geographic_improvement": "at least one lower Top-1 distance or gained GeoRecall@K without hiding any losses", "no_observed_improvement": "no requested geographic metric improves", "regression": "Top-1 distance increases or any baseline GeoRecall@K hit is lost", "model_superiority": "descriptive only for two retrospective development queries; no global claim"},
        "gates": {"claims_review": "pending", "mapillary_authorization": "pending", "asset_manifest_complete": "pending", "paired_inference_2b_8b": "blocked", "promotion_evaluation": "blocked"},
        "biases": ["retrospective_query_selection", "optional_stopping_prevented_by_primary_top50_freeze", "unequal_photo_coverage", "shared_images_and_sequences", "h16_interior_exterior_domain_mismatch", "reference_coordinate_uncertainty_unknown", "no_generalization_from_two_queries"],
    }
    payload = {key: value for key, value in document.items() if key != "protocol_id"}
    document["protocol_id"] = "h16-h23-protocol-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"protocol_id": document["protocol_id"], "promotion_policy_id": promotion["policy_id"], "gates": document["gates"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
