#!/usr/bin/env python3
"""Congela el protocolo corregido v2 sin referencias geográficas."""

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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--variant-plan", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--acquisition-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rankings = json.loads(args.rankings.read_text(encoding="utf-8"))
    variant = json.loads(args.variant_plan.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    acquisition = json.loads(args.acquisition_plan.read_text(encoding="utf-8"))
    for name, document in (("rankings", rankings), ("variant", variant), ("fixture", fixture)):
        reject_ground_truth(document, path=name)
    if fixture.get("contract_version") != "h16-h23-multicandidate-fixture-v2" or fixture["inputs"]["rankings_sha256"] != digest(args.rankings) or fixture["inputs"]["plan_sha256"] != digest(args.variant_plan):
        raise ValueError("fixture v2 incompatible con ranking/variante")
    if acquisition["fixture_id"] != fixture["fixture_id"] or acquisition["authorization"]["downloads_permitted"] is not False:
        raise ValueError("plan de adquisición v2 incompatible")
    promotion = freeze_policy(enabled=True, input_top_n=50, output_top_k=10, positive_weight=0.2, minimum_positive_evidence=0.01, minimum_valid_verdicts=1, max_promotions=10, opened_blocks=((11, 20), (21, 50)))
    prompt_example = verdict_only_prompt({"kind": "object_presence", "value": {"object_type": "example"}, "evidence": {"text": "example"}})
    hashes = {query["query_id"]: query["text_sha256"] for query in fixture["queries"]}
    document = {"schema_version": "2.0", "contract_version": "h16-h23-top50-experiment-protocol-v2", "protocol_id": "", "status": "frozen_blocked_pending_gates", "scope": {"query_ids": ["H16", "H23"], "development_only": True, "variant": "corrected_v2", "query_variants": {query["query_id"]: query["kind"] for query in fixture["queries"]}, "gallery_id": "madrid-50m", "candidate_depth_primary": 50, "candidate_depth_secondary": 20, "output_top_k": 10}, "inputs": {"ranking_id": rankings["ranking_id"], "rankings_sha256": digest(args.rankings), "variant_plan_id": variant["variant_plan_id"], "variant_plan_sha256": digest(args.variant_plan), "fixture_id": fixture["fixture_id"], "fixture_sha256": digest(args.fixture), "acquisition_plan_id": acquisition["plan_id"], "acquisition_plan_sha256": digest(args.acquisition_plan)}, "image_policy": fixture["policy"], "claims": {"contract_version": "visual-atomic-claims-v2", "extractor_version": "visual-atomic-rules-v2", "required_source_hashes": hashes, "human_review_required": True, "orientation_claims_without_comparable_heading": "policy_unverifiable"}, "models": {key: value for key, value in SUPPORTED_LOCAL_MODELS.items() if key in {"qwen3-vl-2b", "qwen3-vl-8b"}}, "inference": {"prompt_version": "visual-verdict-only-v4", "prompt_template_sha256": hashlib.sha256(prompt_example.encode()).hexdigest(), "output_schema": verdict_only_schema(), "output_schema_sha256": hashlib.sha256(canonical_bytes(verdict_only_schema())).hexdigest(), "do_sample": False, "max_new_tokens": 24, "dtype": "bfloat16", "attention": "sdpa", "same_assets_claims_and_policy_for_models": True}, "evidence": {"sequence_deduplication": True, "generic_weight": 0.5, "distinctive_weight": 1.0, "conflict_is_neutral": True, "unverifiable_is_neutral": True, "missing_or_failed_is_neutral": True, "negative_evidence_enabled": False, "minimum_positive_evidence": 0.01}, "promotion_policy": promotion, "metrics": {"distance_top1_m": True, "geo_recall_thresholds_m": [50, 100], "geo_recall_ks": [1, 5, 10], "rank_changes": True, "correct_and_incorrect_promotions": True, "regressions": True, "visual_coverage": True, "neutral_candidates": True, "paired_model_difference": True}, "gates": {"claims_review": "pending", "mapillary_authorization": "pending", "asset_manifest_complete": "pending", "paired_inference_2b_8b": "blocked", "promotion_evaluation": "blocked"}, "biases": ["retrospective_query_selection", "optional_stopping_prevented_by_primary_top50_freeze", "unequal_photo_coverage", "shared_images_and_sequences", "h16_interior_exterior_domain_mismatch", "reference_coordinate_uncertainty_unknown", "no_generalization_from_two_queries"], "supersedes_protocol_for_corrected_variant": "h16-h23-protocol-sha256-dca92d1771695b792a617583138d7fa9c70d016c17a3a17b6dcfa0e97e0d1a96"}
    document["protocol_id"] = "h16-h23-protocol-v2-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in document.items() if key != "protocol_id"})).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"protocol_id": document["protocol_id"], "ranking_id": rankings["ranking_id"], "fixture_id": fixture["fixture_id"], "plan_id": acquisition["plan_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
