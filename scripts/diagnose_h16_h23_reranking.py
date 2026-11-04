#!/usr/bin/env python3
"""Diagnóstico development H16/H23 sin GT ni nuevas inferencias."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.discriminative_visual_reranking import aggregate_discriminative_evidence, apply_discriminative_reranking, canonical_bytes, freeze_discriminative_policy
from src.tfg_phase0.selector_e2e import project_results
from src.tfg_phase0.symmetric_visual_reranking import apply_symmetric_reranking, freeze_symmetric_policy

ART = ROOT / "results/generated/mapillary/h16-h23-selector-comparison-v1"
FIXTURE = ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v2/fixture.json"
OUTPUT = ROOT / "results/generated/mapillary/h16-h23-reranking-diagnostics-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    fixture = json.loads(FIXTURE.read_text())
    plan = json.loads((ART / "physical-task-plan.json").read_text())
    arms = {arm: json.loads((ART / f"{arm}-manifest.json").read_text()) for arm in ("coverage_adaptive", "geometric_adaptive")}
    claims = {query["query_id"]: query["claims"]["claims"] for query in fixture["queries"]}
    baselines = {query["query_id"]: query["baseline_results"] for query in fixture["queries"]}
    weights = (0.0, 0.1, 0.2, 0.5, 1.0, 2.0)
    models = {}
    for model in ("qwen3-vl-2b", "qwen3-vl-8b"):
        physical_document = json.loads((ART / f"{model}-physical-results.json").read_text())
        physical = {row["physical_task_id"]: row for row in physical_document["records"]}
        models[model] = {}
        for arm, manifest in arms.items():
            projected = project_results(plan, physical, arm=arm, model_key=model)
            query_outputs = {}
            for query_id, baseline in baselines.items():
                associations = [row for row in manifest["associations"] if row["query_id"] == query_id]
                verdicts = [row for row in projected if row["query_id"] == query_id]
                from src.tfg_phase0.visual_reranking import aggregate_candidate_evidence
                original_aggregate = aggregate_candidate_evidence(claims[query_id], associations, verdicts, candidate_ids=[row["candidate_id"] for row in baseline])
                sensitivity = []
                for weight in weights:
                    artifact = apply_symmetric_reranking(baseline, original_aggregate, freeze_symmetric_policy(positive_weight=weight))
                    decisions = {row["candidate_id"]: row for row in artifact["candidate_decisions"]}
                    inside = [decisions[row["candidate_id"]] for row in baseline[:10]]
                    outside = [decisions[row["candidate_id"]] for row in baseline[10:]]
                    sensitivity.append({"positive_weight": weight, "changed_candidates": len(artifact["rank_changes"]), "top10_entries": sum(row["type"] == "enter_top10" for row in artifact["operations"]), "top1_changed": artifact["full_experimental_order"][0] != baseline[0]["candidate_id"], "rank10_rank11_margin": min(row["experimental_score"] for row in inside) - max(row["experimental_score"] for row in outside)})
                discriminative_aggregate = aggregate_discriminative_evidence(claims[query_id], associations, verdicts, candidate_ids=[row["candidate_id"] for row in baseline])
                discriminative = apply_discriminative_reranking(baseline, discriminative_aggregate, freeze_discriminative_policy())
                original_by = {row["candidate_id"]: row for row in original_aggregate["candidates"]}
                discriminative_by = {row["candidate_id"]: row for row in discriminative_aggregate["candidates"]}
                query_outputs[query_id] = {"sensitivity": sensitivity, "discriminative": discriminative, "candidate_diagnostics": [{"candidate_id": row["candidate_id"], "baseline_rank": row["rank"], "cosine_similarity": row["cosine_similarity"], "original_positive_evidence": original_by[row["candidate_id"]]["positive_evidence"], "original_negative_evidence": original_by[row["candidate_id"]]["negative_evidence"], "discriminative_positive_evidence": discriminative_by[row["candidate_id"]]["positive_evidence"], "discriminative_negative_evidence": discriminative_by[row["candidate_id"]]["negative_evidence"]} for row in baseline]}
            models[model][arm] = query_outputs
    document = {"schema_version": "1.0", "contract_version": "h16-h23-reranking-diagnostics-v1", "status": "development_diagnostic_not_policy_selection", "inputs": {"fixture_sha256": digest(FIXTURE), "physical_task_plan_sha256": digest(ART / "physical-task-plan.json"), "qwen3_vl_2b_sha256": digest(ART / "qwen3-vl-2b-physical-results.json"), "qwen3_vl_8b_sha256": digest(ART / "qwen3-vl-8b-physical-results.json")}, "protocol": {"ground_truth_used": False, "new_inference": False, "weights_predefined_not_optimized": list(weights), "h16_h23_development_only": True}, "models": models, "conclusions": ["weight_0_2_is_smaller_than_observed_ct2l_boundary_gaps", "shared_support_has_no_discount_in_original_policy", "sequence_count_is_diagnostic_only_in_original_policy", "original_negative_weight_is_zero", "sensitivity_is_not_calibration"]}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "diagnostic.json"
    path.write_bytes(canonical_bytes(document) + b"\n")
    summary = {model: {arm: {query: {"sensitivity": data["sensitivity"], "discriminative_top10_entries": sum(row["type"] == "enter_top10" for row in data["discriminative"]["operations"]), "discriminative_top1_changed": data["discriminative"]["full_experimental_order"][0] != baselines[query][0]["candidate_id"]} for query, data in queries.items()} for arm, queries in arms.items()} for model, arms in models.items()}
    print(json.dumps({"summary": summary, "sha256": digest(path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
