#!/usr/bin/env python3
"""One-shot local worker which always releases its model before exiting."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.atlas_api.dialogue_sessions import atomic_write


def _die_with_parent() -> None:
    if ctypes.CDLL(None).prctl(1, 9, 0, 0, 0) != 0:
        raise RuntimeError("no se pudo fijar PDEATHSIG")


def _retrieve(arguments, request):
    from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, load_runtime_config

    model, galleries = load_runtime_config(
        arguments.runtime_config,
        project_root=ROOT,
        cvg_utils_sha256=arguments.cvg_utils_sha256,
        clip_weights_path=arguments.clip,
    )
    requested = request.get("gallery_ids")
    if not isinstance(requested, list) or not requested or len(set(requested)) != len(requested):
        raise ValueError("gallery_ids inválido")
    selected = [gallery for gallery in galleries if gallery.gallery_id in requested]
    if [gallery.gallery_id for gallery in selected] != requested:
        by_id = {gallery.gallery_id: gallery for gallery in selected}
        try:
            selected = [by_id[gallery_id] for gallery_id in requested]
        except KeyError as error:
            raise ValueError("galería no configurada") from error
    runtime = CrossText2LocRetriever.load(
        model_config=model,
        gallery_configs=selected,
        region_config=arguments.region_config,
        deep_validate_visual_assets=False,
    )
    try:
        return runtime.retrieve_many(
            gallery_ids=requested,
            query_id=request["query_id"],
            text=request["text"],
            language=request["language"],
            k=request["k"],
        )
    finally:
        runtime.close()


def _transform(arguments, request):
    from src.tfg_phase0.f5_text_transform import GenerationConfig, QwenTransformersAdapter

    generation = GenerationConfig(**request["generation"])
    transformer = QwenTransformersAdapter(arguments.model, model_id=arguments.model_id, revision=arguments.revision)
    try:
        result = transformer.transform(request["original_text"], request["task"], request["protected_toponyms"], generation)
        metadata = asdict(transformer.metadata)
        resource_usage = dict(transformer.resource_usage)
    finally:
        transformer.close()
    return {"result": asdict(result), "metadata": metadata, "resource_usage": resource_usage}


def main() -> int:
    _die_with_parent()
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("retrieve", "transform"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--region-config", type=Path)
    parser.add_argument("--clip", type=Path)
    parser.add_argument("--cvg-utils-sha256")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--model-id")
    parser.add_argument("--revision")
    arguments = parser.parse_args()
    request = json.loads(arguments.request.read_text(encoding="utf-8"))
    document = _retrieve(arguments, request) if arguments.operation == "retrieve" else _transform(arguments, request)
    atomic_write(arguments.output, document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
