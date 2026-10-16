#!/usr/bin/env python3
"""Congela todos los rankings Top-10 de un query set lingüístico F4.5."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f4_evaluation import RANKING_SET_PREFIX, ranking_set_id
from src.tfg_phase0.f4_robustness import linguistic_query_inputs, linguistic_query_inputs_sha256, validate_linguistic_query_set
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-set", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--embedding-dataset-id", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    query_set = json.loads(args.query_set.read_text(encoding="utf-8"))
    validate_linguistic_query_set(query_set)
    queries = linguistic_query_inputs(query_set)
    rankings = []
    for query in queries:
        path = args.results_dir / f"{query['query_id']}.json"
        if not path.is_file():
            raise RuntimeError(f"ranking ausente: {query['query_id']}")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["query"] != {"query_id": query["query_id"], "text": query["text"], "language": query["language"]} or result["effective_k"] != 10 or result["checkpoint_sha256"] != args.checkpoint_sha256 or result["embedding_dataset_id"] != args.embedding_dataset_id:
            raise RuntimeError(f"ranking incompatible: {query['query_id']}")
        rankings.append({"query_id": query["query_id"], "logical_path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "effective_k": 10})
    document = {"schema_version": "1.0", "contract_version": "f4-ranking-set-v1", "ranking_set_id": RANKING_SET_PREFIX + "0" * 64, "query_inputs_sha256": linguistic_query_inputs_sha256(query_set), "embedding_dataset_id": args.embedding_dataset_id, "checkpoint_sha256": args.checkpoint_sha256, "partition": "development", "frozen_before_reference_access": False, "rankings": sorted(rankings, key=lambda row: row["query_id"])}
    document["ranking_set_id"] = ranking_set_id(document)
    validate_document(document, "f4_ranking_set")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(document["ranking_set_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
