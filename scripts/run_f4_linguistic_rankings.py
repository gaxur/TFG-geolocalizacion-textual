#!/usr/bin/env python3
"""Genera Top-10 F4.5 cargando una vez el modelo y una galería validada."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, GalleryConfig, ModelConfig
from src.tfg_phase0.f4_robustness import linguistic_query_inputs, validate_linguistic_query_set


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-set", required=True, type=Path)
    parser.add_argument("--visual-bundle", required=True, type=Path)
    parser.add_argument("--catalog-manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--region-config", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--clip-weights", required=True, type=Path)
    parser.add_argument("--cvg-text-root", required=True, type=Path)
    parser.add_argument("--cvg-utils-sha256", required=True)
    parser.add_argument("--container-image-id", required=True)
    parser.add_argument("--embedding-bundle", required=True, type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()

    query_set = json.loads(args.query_set.read_text(encoding="utf-8"))
    validate_linguistic_query_set(query_set)
    gallery = GalleryConfig("batch", args.catalog_manifest, args.selection, args.visual_bundle, args.embedding_bundle)
    model = ModelConfig(args.checkpoint, args.clip_weights, args.cvg_text_root, args.cvg_utils_sha256, args.device)
    runtime = CrossText2LocRetriever.load(model_config=model, gallery_configs=[gallery], region_config=args.region_config, deep_validate_visual_assets=True)
    args.output_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    try:
        for query in linguistic_query_inputs(query_set):
            response = runtime.retrieve_many(gallery_ids=["batch"], query_id=query["query_id"], text=query["text"], language=query["language"], k=10)
            resident = response["retrievals"][0]
            timing = response["timings_ms"]
            result = {"schema_version": "2.0", "contract_version": "f4-exhaustive-retrieval-v2", "query": response["query"], "embedding_dataset_id": resident["embedding_dataset_id"], "checkpoint_sha256": response["model"]["checkpoint_sha256"], "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "gallery_count": resident["gallery_count"], "requested_k": 10, "effective_k": 10, "results": [{"rank": row["rank"], "candidate_id": row["candidate_id"], "latitude": row["latitude"], "longitude": row["longitude"], "score": row["cosine_similarity"]} for row in resident["results"]], "timings_ms": {"text_encoding": timing["text_encoding"], "ranking": timing["ranking_by_gallery"]["batch"], "total": timing["total"]}}
            output = args.output_root / f"{query['query_id']}.json"
            raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            if output.exists() and output.read_text(encoding="utf-8") != raw:
                existing = json.loads(output.read_text(encoding="utf-8"))
                stable_fields = ("query", "embedding_dataset_id", "checkpoint_sha256", "ranking_method", "tie_break", "gallery_count", "requested_k", "effective_k", "results")
                if any(existing[field] != result[field] for field in stable_fields):
                    raise RuntimeError(f"ranking existente no reproducible: {query['query_id']}")
            else:
                output.write_text(raw, encoding="utf-8")
            summaries.append({"query_id": query["query_id"], "top1": result["results"][0]["candidate_id"], "score": result["results"][0]["score"]})
    finally:
        runtime.close()
    print(json.dumps({"query_set_id": query_set["query_set_id"], "gallery_count": resident["gallery_count"], "rankings": len(summaries), "status": "ok"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
