#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f4_evaluation import haversine_m
from src.tfg_phase0.topn_reserve import canonical_bytes


REQUESTED_KS = (1, 5, 10, 20, 50, 100, 200, 500)
THRESHOLDS = (50, 100)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa techo geográfico después del freeze.")
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rankings = json.loads(args.rankings.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    references = {row["query_id"]: row["reference"] for row in dataset["observations"]}
    available_k = int(rankings["top_k"])
    ks = tuple(value for value in REQUESTED_KS if value <= available_k)
    rows = []
    for ranking in rankings["rows"]:
        reference = references[ranking["query_id"]]
        assignment = reference["assignments"][ranking["gallery_id"]]
        candidates = [
            {**candidate, "distance_m": haversine_m(reference["latitude"], reference["longitude"], candidate["latitude"], candidate["longitude"])}
            for candidate in ranking["results"]
        ]
        exact_rank = next((candidate["rank"] for candidate in candidates if assignment.get("status") == "assigned" and candidate["candidate_id"] == assignment.get("candidate_id")), None)
        metrics = {}
        for value in ks:
            subset = candidates[:value]
            minimum = min(candidate["distance_m"] for candidate in subset)
            metrics[str(value)] = {
                "minimum_distance_m": minimum,
                "exact_recall": exact_rank is not None and exact_rank <= value if assignment.get("status") == "assigned" else None,
                **{f"geo_{threshold}": minimum <= threshold for threshold in THRESHOLDS},
            }
        rows.append({"query_id": ranking["query_id"], "kind": ranking["kind"], "gallery_id": ranking["gallery_id"], "assignment_status": assignment.get("status"), "exact_rank": exact_rank, "metrics": metrics, "top1_distance_m": candidates[0]["distance_m"], "nearest_available_rank": min(candidates, key=lambda candidate: candidate["distance_m"])["rank"]})
    aggregates = []
    for gallery in ("madrid-25m", "madrid-50m"):
        for kind in ("es_original", "en_cartographic"):
            selected = [row for row in rows if row["gallery_id"] == gallery and row["kind"] == kind]
            exact = [row for row in selected if row["assignment_status"] == "assigned"]
            aggregates.append({
                "gallery_id": gallery,
                "kind": kind,
                "count": len(selected),
                "exact_count": len(exact),
                "exact_recall": {str(value): {"hits": sum(row["metrics"][str(value)]["exact_recall"] for row in exact), "total": len(exact), "value": sum(row["metrics"][str(value)]["exact_recall"] for row in exact) / len(exact) if exact else None} for value in ks},
                "geo_recall": {str(value): {str(threshold): {"hits": sum(row["metrics"][str(value)][f"geo_{threshold}"] for row in selected), "total": len(selected), "value": sum(row["metrics"][str(value)][f"geo_{threshold}"] for row in selected) / len(selected)} for threshold in THRESHOLDS} for value in ks},
            })
    document = {
        "schema_version": "1.1",
        "contract_version": "h11-h25-topn-geographic-ceiling-v1",
        "inputs": {"rankings_sha256": sha256_file(args.rankings), "dataset_sha256": sha256_file(args.dataset)},
        "protocol": {"reference_kind": "google_link_coordinate_unknown_uncertainty", "official_f54_evaluation": False, "reference_loaded_only_by_evaluator": True, "rankings_frozen_before_reference": True, "available_top_k": available_k, "ks": list(ks), "unavailable_requested_ks": [value for value in REQUESTED_KS if value > available_k], "thresholds_m": list(THRESHOLDS)},
        "aggregates": aggregates,
        "rows": rows,
        "limitations": ["development_queries", "unknown_reference_uncertainty", "not_official_ground_truth", "ceiling_not_reranking_result", "cannot_infer_metrics_beyond_frozen_ranking_depth"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"rows": len(rows), "available_ks": ks, "aggregates": aggregates}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
