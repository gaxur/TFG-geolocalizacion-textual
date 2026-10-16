#!/usr/bin/env python3
"""Runner JSON/JSONL del recuperador residente F4.6; no abre sockets HTTP."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, GalleryConfig, ModelConfig, validate_retrieval_request


def load_config(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != {"schema_version", "contract_version", "model", "galleries"} or raw["schema_version"] != "1.0" or raw["contract_version"] != "crosstext2loc-runtime-config-v1" or not isinstance(raw["galleries"], dict) or not raw["galleries"]:
        raise ValueError("configuración runtime incompatible")
    expected_gallery_fields = {"catalog_manifest", "selection", "visual_bundle", "embedding_bundle"}
    if any(set(value) != expected_gallery_fields for value in raw["galleries"].values()):
        raise ValueError("configuración de galería incompatible")
    galleries = [GalleryConfig(gallery_id, ROOT / value["catalog_manifest"], ROOT / value["selection"], ROOT / value["visual_bundle"], ROOT / value["embedding_bundle"]) for gallery_id, value in raw["galleries"].items()]
    model = raw["model"]
    if set(model) != {"checkpoint", "clip_weights", "cvg_text_root", "device"}:
        raise ValueError("configuración de modelo incompatible")
    clip_path = model["clip_weights"]
    if clip_path == "${CLIP_WEIGHTS_PATH}":
        try:
            clip_path = os.environ["CLIP_WEIGHTS_PATH"]
        except KeyError as error:
            raise ValueError("CLIP_WEIGHTS_PATH es obligatorio para el runtime") from error
    return ModelConfig(ROOT / model["checkpoint"], Path(clip_path), ROOT / model["cvg_text_root"], "", model["device"]), galleries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid_f46_retriever.json")
    parser.add_argument("--cvg-utils-sha256", required=True)
    parser.add_argument("--request", type=Path, help="Procesa un JSON y termina; sin este argumento usa JSONL por stdin.")
    parser.add_argument("--deep-validate-visual-assets", action="store_true")
    args = parser.parse_args()
    model, galleries = load_config(args.config)
    model = ModelConfig(model.checkpoint, model.clip_weights, model.cvg_text_root, args.cvg_utils_sha256, model.device)
    runtime = CrossText2LocRetriever.load(model_config=model, gallery_configs=galleries, region_config=ROOT / "config/madrid.yaml", deep_validate_visual_assets=args.deep_validate_visual_assets)
    try:
        lines = [args.request.read_text(encoding="utf-8")] if args.request else sys.stdin
        for line in lines:
            if not line.strip(): continue
            try:
                request = json.loads(line)
                validate_retrieval_request(request, runtime.gallery_ids)
                query = request["query"]
                response = runtime.retrieve_many(gallery_ids=request["gallery_ids"], query_id=query["query_id"], text=query["text"], language=query["language"], k=request["top_k"])
                print(json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)
            except Exception as error:
                if args.request:
                    raise
                print(json.dumps({"schema_version": "1.0", "error": {"type": type(error).__name__, "message": str(error)}}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
