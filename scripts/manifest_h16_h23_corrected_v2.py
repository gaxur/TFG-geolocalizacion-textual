#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--old-rankings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rankings = json.loads((args.root / "rankings.json").read_text(encoding="utf-8"))
    old = json.loads(args.old_rankings.read_text(encoding="utf-8"))
    old_index = {(row["query_id"], row["kind"], row["gallery_id"]): row for row in old["rows"]}
    comparison = []
    for row in rankings["rows"]:
        previous = old_index[(row["query_id"], "en_cartographic", "madrid-50m")]
        comparison.append({"query_id": row["query_id"], "top10_identical": [item["candidate_id"] for item in row["results"][:10]] == [item["candidate_id"] for item in previous["results"][:10]], "top50_set_identical": {item["candidate_id"] for item in row["results"][:50]} == {item["candidate_id"] for item in previous["results"][:50]}, "top100_order_identical": [item["candidate_id"] for item in row["results"]] == [item["candidate_id"] for item in previous["results"]]})
    files = ["variant-plan.json", "requests/H16.json", "requests/H23.json", "h16-response.json", "h23-response.json", "rankings.json"]
    document = {"schema_version": "1.0", "contract_version": "h16-h23-corrected-v2-manifest", "ranking_id": rankings["ranking_id"], "checkpoint_sha256": rankings["checkpoint_sha256"], "artifacts": {name: {"sha256": digest(args.root / name), "size_bytes": (args.root / name).stat().st_size} for name in files}, "runtime": {"config": "config/madrid_f46_retriever.json", "cvg_text_commit": "6910d2747a94fbe985309bde60cd4732bcbbf50f", "cvg_utils_sha256": "18dad4696c205dba5f934f9382ff5bd7d380c502680e462612bbdc49229ba597", "clip_sha256": "3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02", "ranking_method": "exhaustive_cosine", "ground_truth_used": False, "training": False}, "comparison_to_v1": comparison, "limitations": ["H16_text_changed_so_ranking_is_new", "H23_unchanged_text_is_reproducibility_control", "no_ground_truth_used_for_retrieval"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ranking_id": rankings["ranking_id"], "comparison": comparison}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
