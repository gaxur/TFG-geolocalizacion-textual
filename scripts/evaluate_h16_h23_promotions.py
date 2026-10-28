#!/usr/bin/env python3
"""Abre referencias solo después de materializar las promociones sin GT."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.crs import wgs84_to_epsg25830
from src.tfg_phase0.topn_promotion import restore_baseline
from src.tfg_phase0.visual_reranking import canonical_bytes


def candidate_metrics(ids: list[str], by_id: dict, reference: dict) -> dict:
    reference_xy=wgs84_to_epsg25830(reference["latitude"],reference["longitude"])
    distances = [((wgs84_to_epsg25830(by_id[candidate_id]["latitude"],by_id[candidate_id]["longitude"])[0]-reference_xy[0])**2+(wgs84_to_epsg25830(by_id[candidate_id]["latitude"],by_id[candidate_id]["longitude"])[1]-reference_xy[1])**2)**.5 for candidate_id in ids]
    return {"top1_distance_m": distances[0], "geo_recall": {str(threshold): {str(k): min(distances[:k]) <= threshold for k in (1, 5, 10)} for threshold in (50, 100)}, "minimum_distance_m": {str(k): min(distances[:k]) for k in (1, 5, 10)}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promotions", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    promotions = json.loads(args.promotions.read_text(encoding="utf-8"))
    allowed = {"h16-h23-paired-promotion-artifacts-v1", "h16-h23-v2-partial-availability-conditioned-promotion-v1"}
    if promotions.get("contract_version") not in allowed:
        raise ValueError("artefacto de promoción incompatible")
    partial = promotions.get("protocol", {}).get("availability_conditioned_counterfactual", False)
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    references = {row["query_id"]: row["reference"] for row in dataset["observations"]}
    models = {}
    for model_key, model in promotions["models"].items():
        rows = []
        for query in model["queries"]:
            artifact = query["promotion"]
            baseline = restore_baseline(artifact)
            by_id = {row["candidate_id"]: row for row in baseline}
            baseline_ids = [row["candidate_id"] for row in baseline[:10]]
            final_ids = artifact["final_top10_candidate_ids"]
            reference = references[query["query_id"]]
            baseline_metrics = candidate_metrics(baseline_ids, by_id, reference)
            experimental_metrics = candidate_metrics(final_ids, by_id, reference)
            operations = []
            for operation in artifact["operations"]:
                reference_xy=wgs84_to_epsg25830(reference["latitude"],reference["longitude"])
                promoted_xy=wgs84_to_epsg25830(by_id[operation["promoted_candidate_id"]]["latitude"],by_id[operation["promoted_candidate_id"]]["longitude"]);displaced_xy=wgs84_to_epsg25830(by_id[operation["displaced_candidate_id"]]["latitude"],by_id[operation["displaced_candidate_id"]]["longitude"])
                promoted_distance=((promoted_xy[0]-reference_xy[0])**2+(promoted_xy[1]-reference_xy[1])**2)**.5;displaced_distance=((displaced_xy[0]-reference_xy[0])**2+(displaced_xy[1]-reference_xy[1])**2)**.5
                distance_delta = promoted_distance - displaced_distance
                operations.append({**operation, "promoted_distance_m": promoted_distance, "displaced_distance_m": displaced_distance, "promoted_minus_displaced_distance_m": distance_delta, "replacement_geography": "closer" if distance_delta < 0 else "farther" if distance_delta > 0 else "tied", "correct_geo50_promotion": promoted_distance <= 50 and displaced_distance > 50, "incorrect_geo50_promotion": promoted_distance > 50 and displaced_distance <= 50})
            delta = experimental_metrics["top1_distance_m"] - baseline_metrics["top1_distance_m"]
            lost_hits = [{"threshold_m": threshold, "k": k} for threshold in (50, 100) for k in (1, 5, 10) if baseline_metrics["geo_recall"][str(threshold)][str(k)] and not experimental_metrics["geo_recall"][str(threshold)][str(k)]]
            gained_hits = [{"threshold_m": threshold, "k": k} for threshold in (50, 100) for k in (1, 5, 10) if not baseline_metrics["geo_recall"][str(threshold)][str(k)] and experimental_metrics["geo_recall"][str(threshold)][str(k)]]
            coverage = {row["candidate_id"]: {"status": row["evidence_status"], "valid_verdicts": row["valid_verdicts"], "positive_evidence": row["positive_evidence"]} for row in artifact["candidate_decisions"]}
            rows.append({"query_id": query["query_id"], "baseline": baseline_metrics, "experimental": experimental_metrics, "transition": {"top1_distance_delta_m": delta, "improved": delta < 0 or bool(gained_hits), "regressed": delta > 0 or bool(lost_hits), "gained_geo_hits": gained_hits, "lost_geo_hits": lost_hits}, "operations": operations, "coverage": {"available_candidates": sum(value["status"] == "available" for value in coverage.values()), "neutral_candidates": sum(value["status"] != "available" or value["valid_verdicts"] == 0 for value in coverage.values()), "candidate_evidence": coverage}})
        top1_baseline = [row["baseline"]["top1_distance_m"] for row in rows]
        top1_experimental = [row["experimental"]["top1_distance_m"] for row in rows]
        models[model_key] = {"rows": rows, "aggregate": {"queries": len(rows), "mean_top1_distance_m": {"baseline": statistics.fmean(top1_baseline), "experimental": statistics.fmean(top1_experimental)}, "median_top1_distance_m": {"baseline": statistics.median(top1_baseline), "experimental": statistics.median(top1_experimental)}, "improved_queries": sum(row["transition"]["improved"] for row in rows), "regressed_queries": sum(row["transition"]["regressed"] for row in rows), "correct_geo50_promotions": sum(operation["correct_geo50_promotion"] for row in rows for operation in row["operations"]), "incorrect_geo50_promotions": sum(operation["incorrect_geo50_promotion"] for row in rows for operation in row["operations"]), "geo_recall": {str(threshold): {str(k): {"baseline_hits": sum(row["baseline"]["geo_recall"][str(threshold)][str(k)] for row in rows), "experimental_hits": sum(row["experimental"]["geo_recall"][str(threshold)][str(k)] for row in rows), "total": len(rows)} for k in (1, 5, 10)} for threshold in (50, 100)}}}
    document = {"schema_version": "1.1", "contract_version": "h16-h23-partial-promotion-geography-v1" if partial else "h16-h23-paired-promotion-evaluation-v1", "inputs": {"promotions_sha256": hashlib.sha256(args.promotions.read_bytes()).hexdigest(), "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest()}, "protocol": {"references_loaded_only_by_evaluator": True, "promotions_frozen_before_reference": True, "historical_development_only": True, "distance_crs":"EPSG:25830", "official_frozen_experiment_result": not partial, "availability_conditioned_counterfactual": partial}, "models": models, "limitations": ["two_retrospectively_selected_queries", "reference_coordinate_uncertainty_unknown", "h16_interior_exterior_mismatch", "not_statistical_generalization"] + (["incomplete_historical_asset_subset", "availability_bias"] if partial else [])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({model: value["aggregate"] for model, value in models.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
