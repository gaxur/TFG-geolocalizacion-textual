#!/usr/bin/env python3
"""Congela por hash un conjunto de rankings F4 antes de evaluar referencias."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f4_evaluation import RANKING_SET_PREFIX, query_inputs_sha256, ranking_set_id
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--partition", choices=("development", "evaluation"), required=True)
    parser.add_argument("--embedding-dataset-id", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--frozen-before-reference-access", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    rankings = []
    for query in dataset["queries"]:
        if query["partition"] != args.partition:
            continue
        path = args.results_dir / f"{query['query_id']}.json"
        if not path.is_file():
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        rankings.append({"query_id": query["query_id"], "logical_path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "effective_k": result["effective_k"]})
    document = {"schema_version": "1.0", "contract_version": "f4-ranking-set-v1", "ranking_set_id": RANKING_SET_PREFIX + "0" * 64, "query_inputs_sha256": query_inputs_sha256(dataset, args.partition), "embedding_dataset_id": args.embedding_dataset_id, "checkpoint_sha256": args.checkpoint_sha256, "partition": args.partition, "frozen_before_reference_access": args.frozen_before_reference_access, "rankings": sorted(rankings, key=lambda item: item["query_id"])}
    document["ranking_set_id"] = ranking_set_id(document)
    validate_document(document, "f4_ranking_set")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output.exists() and args.output.read_text(encoding="utf-8") != raw:
        raise RuntimeError("manifest de rankings existente incompatible")
    args.output.write_text(raw, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
