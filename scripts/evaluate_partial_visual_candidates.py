#!/usr/bin/env python3
"""Evalúa honestamente fixtures con un único candidato visual por consulta."""

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


def positive_evidence(run: dict, fixture: dict) -> dict[tuple[str, str], dict]:
    query_by_pair = {(row["candidate_id"], row["image_id"]): row["query_id"] for row in fixture["associations"]}
    claims_by_query = {row["query_id"]: len(row["claims"]) for row in fixture["claim_sets"]}
    states = {}
    for row in run["records"]:
        query_id = query_by_pair[(row["candidate_id"], row["image_id"])]
        key = (query_id, row["candidate_id"], row["claim_id"])
        verdict = row.get("verdict") or (row.get("parsed_verdict") or {}).get("verdict")
        states.setdefault(key, set()).add(verdict or "unverifiable")
    result = {}
    for query_id, candidate_id in {(query, candidate) for query, candidate, _ in states}:
        claim_states = [values for (query, candidate, _), values in states.items() if query == query_id and candidate == candidate_id]
        supported = sum("supported" in values and "contradicted" not in values for values in claim_states)
        result[(query_id, candidate_id)] = {"positive_evidence": supported / claims_by_query[query_id], "claims_supported_by_any_view": supported, "claim_count": claims_by_query[query_id]}
    return result


def metrics(rows: list[dict], reference: dict) -> dict:
    distances = [haversine_m(reference["latitude"], reference["longitude"], row["latitude"], row["longitude"]) for row in rows]
    return {"top1_distance_m": distances[0], "geo_recall_50m": {str(k): min(distances[:k]) <= 50 for k in (1, 5, 10)}, "minimum_distance_m": {str(k): min(distances[:k]) for k in (1, 5, 10)}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--fixture-run", nargs=3, action="append", metavar=("FIXTURE", "MODEL", "RUN"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lambda-pos", type=float, default=0.2)
    args = parser.parse_args()
    rankings = json.loads(args.rankings.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    references = {row["query_id"]: row["reference"] for row in dataset["observations"]}
    baseline = {(row["query_id"], row["kind"], row["gallery_id"]): row["results"] for row in rankings["rows"]}
    rows = []
    for fixture_path, model, run_path in args.fixture_run:
        fixture_file, run_file = Path(fixture_path), Path(run_path)
        fixture = json.loads(fixture_file.read_text(encoding="utf-8"))
        run = json.loads(run_file.read_text(encoding="utf-8"))
        evidence = positive_evidence(run, fixture)
        for (query_id, candidate_id), visual in sorted(evidence.items()):
            base = baseline[(query_id, "es_original", "madrid-50m")]
            if candidate_id not in {candidate["candidate_id"] for candidate in base}:
                rows.append({"query_id": query_id, "model": model, "candidate_id": candidate_id, **visual, "status": "photographed_candidate_not_in_selected_baseline_top10"})
                continue
            scores = [candidate["cosine_similarity"] for candidate in base]
            low, high = min(scores), max(scores)
            ordered = sorted(base, key=lambda candidate: (-((0.5 if high == low else (candidate["cosine_similarity"] - low) / (high - low)) + (args.lambda_pos * visual["positive_evidence"] if candidate["candidate_id"] == candidate_id else 0)), candidate["rank"], candidate["candidate_id"]))
            reranked = [{**candidate, "rank": index} for index, candidate in enumerate(ordered, 1)]
            base_metrics = metrics(base, references[query_id])
            experimental_metrics = metrics(reranked, references[query_id])
            rows.append({"query_id": query_id, "model": model, "candidate_id": candidate_id, **visual, "status": "partial_single_candidate_visual_evidence", "baseline": base_metrics, "experimental": experimental_metrics, "top1_distance_delta_m": experimental_metrics["top1_distance_m"] - base_metrics["top1_distance_m"], "baseline_rank": next(candidate["rank"] for candidate in base if candidate["candidate_id"] == candidate_id), "experimental_rank": next(candidate["rank"] for candidate in reranked if candidate["candidate_id"] == candidate_id)})
    evaluable = [row for row in rows if row["status"] == "partial_single_candidate_visual_evidence"]
    aggregates = {}
    for model in sorted({row["model"] for row in evaluable}):
        selected = [row for row in evaluable if row["model"] == model]
        deltas = [row["top1_distance_delta_m"] for row in selected]
        aggregates[model] = {"queries": len(selected), "improved": sum(value < 0 for value in deltas), "regressed": sum(value > 0 for value in deltas), "tied": sum(value == 0 for value in deltas), "mean_top1_distance_m": {"baseline": statistics.fmean(row["baseline"]["top1_distance_m"] for row in selected), "experimental": statistics.fmean(row["experimental"]["top1_distance_m"] for row in selected)}, "median_top1_distance_m": {"baseline": statistics.median(row["baseline"]["top1_distance_m"] for row in selected), "experimental": statistics.median(row["experimental"]["top1_distance_m"] for row in selected)}, "geo_recall_50m": {str(k): {"baseline_hits": sum(row["baseline"]["geo_recall_50m"][str(k)] for row in selected), "experimental_hits": sum(row["experimental"]["geo_recall_50m"][str(k)] for row in selected), "total": len(selected)} for k in (1, 5, 10)}}
    document = {"schema_version": "1.0", "contract_version": "partial-single-candidate-visual-geography-v1", "inputs": {"rankings_sha256": hashlib.sha256(args.rankings.read_bytes()).hexdigest(), "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest()}, "policy": {"lambda_pos": args.lambda_pos, "lambda_neg": 0, "unphotographed_candidates_neutral": True, "ground_truth_used_for_reranking": False, "same_fixtures_per_model": True}, "aggregates": aggregates, "rows": rows, "limitations": ["development_queries", "only_one_candidate_has_visual_evidence_per_query", "not_a_complete_visual_reranking", "reference_coordinates_have_unknown_uncertainty", "promotion_not_evaluable"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps(aggregates, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
