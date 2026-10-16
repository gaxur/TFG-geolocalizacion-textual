#!/usr/bin/env python3
"""Genera embeddings F4 o ejecuta retrieval exhaustivo CrossText2Loc."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.crosstext2loc_runtime import (
    EXPECTED_CHECKPOINT_NAME as EXPECTED_CHECKPOINT,
    EXPECTED_CHECKPOINT_SHA256,
    EXPECTED_CHECKPOINT_SIZE,
    EXPECTED_CLIP_WEIGHTS_NAME as EXPECTED_CLIP_WEIGHTS,
    EXPECTED_CLIP_WEIGHTS_SHA256,
    EXPECTED_CLIP_WEIGHTS_SIZE,
    EXPECTED_CLIP_COMMIT,
    EXPECTED_CVG_TEXT_COMMIT,
    CLIP_ARCHITECTURE as MODEL_NAME,
    CONTEXT_LENGTH,
    CrossText2LocRetriever,
    GalleryConfig,
    ModelConfig,
    load_model_components,
    load_visual_inputs,
)
from src.tfg_phase0.f4_contracts import F4_EMBEDDING_CONTRACT_VERSION, F4_EMBEDDING_GENERATOR_VERSION
from src.tfg_phase0.f4_retrieval import normalize_l2
from src.tfg_phase0.f4_validation import (
    embedding_dataset_id,
    sha256_bytes,
    validate_embedding_bundle,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_file(path: Path, *, name: str, size: int, digest: str) -> None:
    if not path.is_file() or path.is_symlink() or path.name != name:
        raise RuntimeError(f"archivo inesperado: {path}")
    if path.stat().st_size != size or sha256(path) != digest:
        raise RuntimeError(f"tamaño o SHA-256 inesperado: {path}")


def common_inputs(args):
    gallery = GalleryConfig("cli", args.catalog_manifest, args.selection, args.visual_bundle, getattr(args, "embedding_bundle", args.visual_bundle))
    return load_visual_inputs(gallery, region_config=args.region_config, deep_validate_visual_assets=True)


def model_config(args) -> ModelConfig:
    return ModelConfig(args.checkpoint, args.clip_weights, args.cvg_text_root, args.cvg_utils_sha256, args.device)


def canonical_jsonl(candidate_ids: list[str]) -> bytes:
    return b"".join((json.dumps({"candidate_id": candidate_id}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode() for candidate_id in candidate_ids)


def publish_embedding_bundle(args, catalog, visual, visual_raw, matrix, environment):
    import numpy as np
    matrix = np.ascontiguousarray(matrix, dtype="<f4")
    candidate_ids = [row["candidate_id"] for row in visual["images"]]
    args.output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".f4-embeddings-", dir=args.output_root) as temporary:
        temp = Path(temporary)
        embedding_dir = temp / "embeddings"
        embedding_dir.mkdir()
        matrix_path = embedding_dir / "image_embeddings.npy"
        np.save(matrix_path, matrix, allow_pickle=False)
        ids_path = embedding_dir / "candidate_ids.jsonl"
        ids_path.write_bytes(canonical_jsonl(candidate_ids))
        document = {
            "schema_version": "2.0",
            "embedding_dataset_id": "f4-madrid-embeddings-sha256-" + "0" * 64,
            "contract_version": F4_EMBEDDING_CONTRACT_VERSION,
            "generator_version": F4_EMBEDDING_GENERATOR_VERSION,
            "generator_source_sha256": sha256(Path(__file__)),
            "visual_dataset": {"visual_dataset_id": visual["visual_dataset_id"], "manifest_sha256": sha256_bytes(visual_raw)},
            "model": {"name": "CLIP-L/14@336", "architecture": MODEL_NAME, "cvg_text_commit": EXPECTED_CVG_TEXT_COMMIT, "cvg_utils_sha256": args.cvg_utils_sha256, "openai_clip_commit": EXPECTED_CLIP_COMMIT, "openai_clip_weights_filename": EXPECTED_CLIP_WEIGHTS, "openai_clip_weights_sha256": EXPECTED_CLIP_WEIGHTS_SHA256, "text_context_length": CONTEXT_LENGTH},
            "checkpoint": {"filename": EXPECTED_CHECKPOINT, "size_bytes": EXPECTED_CHECKPOINT_SIZE, "sha256": EXPECTED_CHECKPOINT_SHA256, "selection_status": "provisional_d013"},
            "preprocessing": {"policy": "official_openai_clip_preprocess", "input_width_px": 336, "input_height_px": 336, "image_color_mode": "RGB", "text_tokenizer": "clip.tokenize_context_300", "text_truncation": True},
            "environment": environment,
            "embedding": {"matrix_path": "embeddings/image_embeddings.npy", "matrix_sha256": sha256(matrix_path), "candidate_ids_path": "embeddings/candidate_ids.jsonl", "candidate_ids_sha256": sha256(ids_path), "candidate_ids_format": "jsonl_object_candidate_id_v1", "count": len(candidate_ids), "dimension": 768, "dtype": "float32", "byte_order": "little", "normalization": "l2", "row_order": "visual_manifest_order"},
        }
        document["embedding_dataset_id"] = embedding_dataset_id(document)
        (temp / "manifest.json").write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        validate_embedding_bundle(document, temp, visual, visual_raw, catalog)
        final = args.output_root / document["embedding_dataset_id"]
        if final.exists():
            if {p.relative_to(temp): sha256(p) for p in temp.rglob("*") if p.is_file()} != {p.relative_to(final): sha256(p) for p in final.rglob("*") if p.is_file()}:
                raise RuntimeError("bundle de embeddings existente incompatible")
        else:
            Path(temp).rename(final)
        print(final)


def command_embed(args) -> int:
    import numpy as np
    import torch
    import torchvision
    from PIL import Image
    catalog, visual, visual_raw = common_inputs(args)
    generated = [row for row in visual["images"] if row["generation_status"] == "generated"]
    if len(generated) != len(visual["images"]):
        raise RuntimeError("el bundle visual debe estar completo antes de generar embeddings")
    model, preprocess, _ = load_model_components(model_config(args))
    rows = []
    with torch.inference_mode():
        for image_row in generated:
            with Image.open(args.visual_bundle / image_row["image_path"]) as image:
                tensor = preprocess(image.convert("RGB")).unsqueeze(0).to(args.device)
            if tuple(tensor.shape) != (1, 3, 336, 336):
                raise RuntimeError(f"forma preprocesada inesperada: {tensor.shape}")
            feature = model.encode_image(tensor.float()).float().cpu().numpy()[0]
            rows.append(normalize_l2(feature, label=image_row["candidate_id"]))
    matrix = np.ascontiguousarray(np.stack(rows), dtype="<f4")
    environment = {"container_image_id": args.container_image_id, "python_version": sys.version.split()[0], "torch_version": torch.__version__, "torchvision_version": torchvision.__version__, "cuda_version": str(torch.version.cuda), "device_type": args.device.split(":")[0], "inference_dtype": "float32"}
    publish_embedding_bundle(args, catalog, visual, visual_raw, matrix, environment)
    return 0


def command_rank(args) -> int:
    gallery = GalleryConfig("cli", args.catalog_manifest, args.selection, args.visual_bundle, args.embedding_bundle)
    runtime = CrossText2LocRetriever.load(model_config=model_config(args), gallery_configs=[gallery], region_config=args.region_config, deep_validate_visual_assets=True)
    try:
        resident_count = runtime.gallery_count("cli")
        effective_request_k = min(args.k, resident_count)
        source = runtime.retrieve_many(gallery_ids=["cli"], query_id=args.query_id, text=args.text, language=args.language, k=effective_request_k)
        resident = source["retrievals"][0]
        timing = source["timings_ms"]
        result = {
            "schema_version": "2.0", "contract_version": "f4-exhaustive-retrieval-v2",
            "query": source["query"], "embedding_dataset_id": resident["embedding_dataset_id"],
            "checkpoint_sha256": source["model"]["checkpoint_sha256"], "ranking_method": "exhaustive_cosine",
            "tie_break": "candidate_id_ascending", "gallery_count": resident["gallery_count"], "requested_k": args.k,
            "effective_k": len(resident["results"]),
            "results": [{"rank": row["rank"], "candidate_id": row["candidate_id"], "latitude": row["latitude"], "longitude": row["longitude"], "score": row["cosine_similarity"]} for row in resident["results"]],
            "timings_ms": {"text_encoding": timing["text_encoding"], "ranking": timing["ranking_by_gallery"]["cli"], "total": timing["total"]},
        }
    finally:
        runtime.close()
    output = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.is_symlink():
            raise RuntimeError("la salida no puede ser un symlink")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.output.parent, prefix=f".{args.output.name}.", delete=False) as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        if args.output.exists():
            if args.output.read_text(encoding="utf-8") != output:
                temporary.unlink()
                raise RuntimeError(f"resultado existente incompatible: {args.output}")
            temporary.unlink()
        else:
            os.replace(temporary, args.output)
    print(output, end="")
    return 0


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--visual-bundle", required=True, type=Path)
    common.add_argument("--catalog-manifest", required=True, type=Path)
    common.add_argument("--selection", required=True, type=Path)
    common.add_argument("--region-config", required=True, type=Path)
    common.add_argument("--checkpoint", required=True, type=Path)
    common.add_argument("--clip-weights", required=True, type=Path)
    common.add_argument("--cvg-text-root", required=True, type=Path)
    common.add_argument("--cvg-utils-sha256", required=True)
    common.add_argument("--container-image-id", required=True)
    common.add_argument("--device", default="cuda")
    root = argparse.ArgumentParser(description=__doc__)
    subcommands = root.add_subparsers(required=True)
    embed = subcommands.add_parser("embed", parents=[common])
    embed.add_argument("--output-root", required=True, type=Path)
    embed.set_defaults(function=command_embed)
    rank = subcommands.add_parser("rank", parents=[common])
    rank.add_argument("--embedding-bundle", required=True, type=Path)
    rank.add_argument("--query-id", required=True)
    rank.add_argument("--text", required=True)
    rank.add_argument("--language", required=True)
    rank.add_argument("--k", required=True, type=int)
    rank.add_argument("--output", type=Path)
    rank.set_defaults(function=command_rank)
    return root


def main() -> int:
    args = parser().parse_args()
    if not args.container_image_id.startswith("sha256:") or len(args.cvg_utils_sha256) != 64:
        raise RuntimeError("container_image_id no válido")
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
