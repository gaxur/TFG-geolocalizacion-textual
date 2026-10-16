#!/usr/bin/env python3
"""Integración real F4.6 con una carga de modelo y ambas galerías."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_f46_retriever import load_config
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, ModelConfig, RuntimeClosedError


def stable_rows(response):
    return {row["gallery_id"]: normalized_rows(row["results"]) for row in response["retrievals"]}


def normalized_rows(rows):
    return [
        (row["rank"], row["candidate_id"], row["latitude"], row["longitude"], row.get("cosine_similarity", row.get("score")))
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid_f46_retriever.json")
    parser.add_argument("--cvg-utils-sha256", required=True)
    parser.add_argument("--expected-25m", required=True, type=Path)
    parser.add_argument("--expected-50m", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    import torch
    torch.cuda.reset_peak_memory_stats()
    model, galleries = load_config(args.config)
    model = ModelConfig(model.checkpoint, model.clip_weights, model.cvg_text_root, args.cvg_utils_sha256, model.device)
    started = time.perf_counter()
    runtime = CrossText2LocRetriever.load(model_config=model, gallery_configs=galleries, region_config=ROOT / "config/madrid.yaml", deep_validate_visual_assets=False)
    initialized = time.perf_counter()
    memory_after_load = runtime.cuda_memory()
    torch.cuda.reset_peak_memory_stats()
    query = {"query_id": "madrid-f42-final-en-001", "text": "A large urban square surrounded by buildings and narrow streets", "language": "en"}
    first = runtime.retrieve_many(gallery_ids=["madrid-25m", "madrid-50m"], k=10, **query)
    queried = time.perf_counter()
    memory_after_query = runtime.cuda_memory()
    repeated = runtime.retrieve_many(gallery_ids=["madrid-25m", "madrid-50m"], k=10, **query)
    spanish = runtime.retrieve_many(gallery_ids=["madrid-25m", "madrid-50m"], query_id="f46-es", text="Una gran plaza urbana rodeada de edificios y calles estrechas", language="es", k=10)
    expected = {"madrid-25m": normalized_rows(json.loads(args.expected_25m.read_text())["results"]), "madrid-50m": normalized_rows(json.loads(args.expected_50m.read_text())["results"])}
    if stable_rows(first) != expected or stable_rows(repeated) != stable_rows(first):
        raise RuntimeError("el runtime no coincide con rankings F4.4 o no es determinista")
    encode_count = runtime._encoder.encode_count
    runtime.close()
    closed_rejected = False
    try:
        runtime.retrieve_many(gallery_ids=["madrid-50m"], k=1, **query)
    except RuntimeClosedError:
        closed_rejected = True
    report = {
        "status": "pass", "loaded_gallery_ids": list(runtime.gallery_ids),
        "text_encode_count": encode_count, "multigallery_single_encode_verified": encode_count == 3,
        "rankings_match_f44": True, "repeated_ranking_identical": True, "closed_runtime_rejected": closed_rejected,
        "initialization_ms": (initialized - started) * 1000, "first_multigallery_query_ms": (queried - initialized) * 1000,
        "cuda_memory_after_load": memory_after_load, "cuda_memory_after_query": memory_after_query,
        "gallery_counts": {row["gallery_id"]: row["gallery_count"] for row in first["retrievals"]},
        "spanish_top1": {row["gallery_id"]: row["results"][0] for row in spanish["retrievals"]},
    }
    if not report["multigallery_single_encode_verified"] or not closed_rejected or len(report["loaded_gallery_ids"]) != 2:
        raise RuntimeError("no se verificó residencia o cierre")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
