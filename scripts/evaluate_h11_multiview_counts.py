#!/usr/bin/env python3
"""Ablación anidada H11 con los mismos assets ya inferidos por 2B y 8B."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.visual_reranking import aggregate_candidate_evidence, canonical_bytes, evaluate_topk_transition, rerank_experimental


def nested_associations(fixture: dict, count: int) -> list[dict]:
    grouped = {}
    for row in fixture["associations"]:
        grouped.setdefault(row["candidate_id"], []).append(row)
    selected = []
    for candidate_id, rows in grouped.items():
        rows.sort(key=lambda row: (row["orientation_band"], row["distance_to_candidate_m"], -(row.get("quality_score") or -1), row["image_id"]))
        selected.extend(rows[:count])
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--run-2b", type=Path, required=True)
    parser.add_argument("--run-8b", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lambda-pos", type=float, default=0.2)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    reference = next(row["reference"] for row in dataset["observations"] if row["query_id"] == "H11")
    baseline = fixture["baseline"]["results"]
    baseline_ids = [row["candidate_id"] for row in baseline]
    experiments = []
    for model, path in (("2b", args.run_2b), ("8b", args.run_8b)):
        run = json.loads(path.read_text(encoding="utf-8"))
        records = {(row["candidate_id"], row["image_id"], row["claim_id"]): row for row in run["records"]}
        for count in (1, 3, 5):
            associations = nested_associations(fixture, count)
            keys = {(row["candidate_id"], row["image_id"]) for row in associations}
            verdicts = []
            for key, row in records.items():
                if key[:2] not in keys or row["status"] not in {"valid", "policy_unverifiable"}:
                    continue
                verdict = row.get("verdict") or (row.get("parsed_verdict") or {}).get("verdict")
                if verdict:
                    verdicts.append({"status": "valid", "candidate_id": key[0], "image_id": key[1], "claim_id": key[2], "verdict": verdict})
            aggregate = aggregate_candidate_evidence(run["approved_claims"], associations, verdicts, candidate_ids=baseline_ids)
            reranking = rerank_experimental({"results": baseline}, aggregate, enabled=True, lambda_pos=args.lambda_pos, lambda_neg=0)
            by_id = {row["candidate_id"]: row for row in baseline}
            experimental = [{**by_id[row["candidate_id"]], "rank": index} for index, row in enumerate(reranking["results"], 1)]
            geography = evaluate_topk_transition(baseline, experimental, reference_latitude=reference["latitude"], reference_longitude=reference["longitude"])
            experiments.append({"model": model, "requested_images_per_candidate": count, "actual_associations": len(associations), "candidate_image_counts": {candidate_id: sum(row["candidate_id"] == candidate_id for row in associations) for candidate_id in baseline_ids}, "valid_verdicts": len(verdicts), "reranked_candidate_ids": [row["candidate_id"] for row in reranking["results"]], "geography": geography})
    document = {"schema_version": "1.0", "contract_version": "h11-multiview-count-ablation-v1", "inputs": {"fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(), "run_2b_sha256": hashlib.sha256(args.run_2b.read_bytes()).hexdigest(), "run_8b_sha256": hashlib.sha256(args.run_8b.read_bytes()).hexdigest(), "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest()}, "policy": {"nested_counts": [1, 3, 5], "requested_primary_count": 8, "eight_image_result_available": False, "selection_without_gt": True, "lambda_pos": args.lambda_pos, "lambda_neg": 0, "missing_is_neutral": True}, "experiments": experiments, "limitations": ["single_development_query", "reference_coordinate_unknown_uncertainty", "no_human_labels_for_h11_claim_image_pairs", "maximum_existing_run_depth_is_five_not_eight", "no_promotion_beyond_top10"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"experiments": len(experiments), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
