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

import numpy as np

from scripts.run_f4_crosstext2loc import CONTEXT_LENGTH, EXPECTED_CHECKPOINT_SHA256, build_model, common_inputs
from src.tfg_phase0.f4_retrieval import build_retrieval_result, exhaustive_rank, normalize_l2
from src.tfg_phase0.f4_robustness import linguistic_query_inputs, validate_linguistic_query_set
from src.tfg_phase0.f4_validation import validate_embedding_bundle, validate_retrieval_result


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

    import clip
    import torch

    query_set = json.loads(args.query_set.read_text(encoding="utf-8"))
    validate_linguistic_query_set(query_set)
    catalog, visual, visual_raw = common_inputs(args)
    embedding = json.loads((args.embedding_bundle / "manifest.json").read_text(encoding="utf-8"))
    matrix, candidate_ids = validate_embedding_bundle(embedding, args.embedding_bundle, visual, visual_raw, catalog)
    model, _ = build_model(args.cvg_text_root, args.checkpoint, args.clip_weights, args.device)
    args.output_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    for query in linguistic_query_inputs(query_set):
        start = time.perf_counter()
        tokens = clip.tokenize(query["text"], context_length=CONTEXT_LENGTH, truncate=True).to(args.device)
        with torch.inference_mode():
            text_feature = model.encode_text(tokens).float().cpu().numpy()[0]
        encoded = time.perf_counter()
        ranked = exhaustive_rank(matrix, candidate_ids, text_feature, 10)
        ranked_at = time.perf_counter()
        result = build_retrieval_result(
            query_id=query["query_id"], text=query["text"], language=query["language"],
            embedding_dataset_id=embedding["embedding_dataset_id"], checkpoint_sha256=EXPECTED_CHECKPOINT_SHA256,
            ranked=ranked, catalog=catalog, gallery_count=len(candidate_ids), requested_k=10,
            timings_ms={"text_encoding": (encoded - start) * 1000, "ranking": (ranked_at - encoded) * 1000, "total": (ranked_at - start) * 1000},
        )
        validate_retrieval_result(result, catalog, embedding_manifest=embedding, candidate_ids=candidate_ids, matrix=matrix, text_embedding=normalize_l2(text_feature))
        output = args.output_root / f"{query['query_id']}.json"
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        if output.exists() and output.read_text(encoding="utf-8") != raw:
            existing = json.loads(output.read_text(encoding="utf-8"))
            validate_retrieval_result(existing, catalog, embedding_manifest=embedding, candidate_ids=candidate_ids)
            stable_fields = ("query", "embedding_dataset_id", "checkpoint_sha256", "ranking_method", "tie_break", "gallery_count", "requested_k", "effective_k", "results")
            if any(existing[field] != result[field] for field in stable_fields):
                raise RuntimeError(f"ranking existente no reproducible: {query['query_id']}")
        else:
            output.write_text(raw, encoding="utf-8")
        summaries.append({"query_id": query["query_id"], "top1": result["results"][0]["candidate_id"], "score": result["results"][0]["score"]})
    print(json.dumps({"query_set_id": query_set["query_set_id"], "gallery_count": len(candidate_ids), "rankings": len(summaries), "status": "ok"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
