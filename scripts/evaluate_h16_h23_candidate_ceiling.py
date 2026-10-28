#!/usr/bin/env python3
"""Evaluación posterior del ranking/plan ya congelados; nunca selecciona candidatos."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f4_evaluation import haversine_m
from src.tfg_phase0.visual_reranking import canonical_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/dataset.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    references = {row["query_id"]: row["reference"] for row in dataset["observations"]}
    rows = []
    for query in fixture["queries"]:
        reference = references[query["query_id"]]
        candidates = [{**candidate, "distance_m": haversine_m(reference["latitude"], reference["longitude"], candidate["latitude"], candidate["longitude"])} for candidate in query["baseline_results"]]
        assignment = reference["assignments"]["madrid-50m"]
        exact_rank = next((candidate["rank"] for candidate in candidates if candidate["candidate_id"] == assignment.get("candidate_id")), None) if assignment.get("status") == "assigned" else None
        metrics = {}
        for k in (1, 5, 10, 20, 50):
            if k > len(candidates):
                continue
            distances = [candidate["distance_m"] for candidate in candidates[:k]]
            metrics[str(k)] = {"minimum_distance_m": min(distances), "geo_recall_50m": min(distances) <= 50, "exact_recall": exact_rank is not None and exact_rank <= k}
        rows.append({"query_id": query["query_id"], "candidate_depth": len(candidates), "top1_candidate_id": candidates[0]["candidate_id"], "top1_distance_m": candidates[0]["distance_m"], "first_geo50_rank": next((candidate["rank"] for candidate in candidates if candidate["distance_m"] <= 50), None), "exact_rank_within_fixture": exact_rank, "metrics": metrics})
    top1 = [row["top1_distance_m"] for row in rows]
    document = {"schema_version": "1.0", "contract_version": "h16-h23-postfreeze-candidate-ceiling-v1", "inputs": {"fixture_id": fixture["fixture_id"], "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(), "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest()}, "protocol": {"ground_truth_loaded_only_by_evaluator": True, "candidate_plan_frozen_before_reference": True, "not_a_reranking_or_promotion_result": True}, "rows": rows, "aggregate": {"queries": len(rows), "mean_top1_distance_m": statistics.fmean(top1), "median_top1_distance_m": statistics.median(top1), "geo_recall_50m": {str(k): {"hits": sum(row["metrics"].get(str(k), {}).get("geo_recall_50m", False) for row in rows), "total": sum(str(k) in row["metrics"] for row in rows)} for k in (1, 5, 10, 20, 50)}}, "limitations": ["historical_development_queries", "reference_uncertainty_unknown", "ceiling_uses_gt_after_selection", "does_not_show_vlm_can_identify_candidate"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"rows": rows, "aggregate": document["aggregate"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
