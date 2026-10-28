#!/usr/bin/env python3
"""Smoke test de una muestra real de CrossText2Loc en una GPU GB10."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

EXPECTED_CVG_TEXT_COMMIT = "6910d2747a94fbe985309bde60cd4732bcbbf50f"
EXPECTED_CHECKPOINT_NAME = (
    "long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth"
)
EXPECTED_CHECKPOINT_SIZE = 1_712_649_548
EXPECTED_CHECKPOINT_SHA256 = (
    "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d"
)
EXPECTED_CLIP_COMMIT = "dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1"
MODEL_NAME = "ViT-L/14@336px"
CONTEXT_LENGTH = 300


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke test funcional de una muestra real de CrossText2Loc. "
            "No ejecuta el protocolo de evaluación ni calcula R@K."
        )
    )
    parser.add_argument("--cvg-text-root", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--annotation", required=True, type=Path)
    parser.add_argument("--image-root", required=True, type=Path)
    parser.add_argument("--sample-index", required=True, type=int)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Valida en CPU y no carga el modelo ni ejecuta operaciones en CUDA.",
    )
    return parser.parse_args()


def require_path(path: Path, kind: str) -> Path:
    path = path.expanduser().resolve()
    valid = path.is_dir() if kind == "directorio" else path.is_file()
    if not valid:
        raise FileNotFoundError(f"No existe el {kind} requerido: {path}")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(repository: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def load_sample(annotation: Path, image_root: Path, sample_index: int) -> tuple[Path, str]:
    with annotation.open(encoding="utf-8") as file:
        annotations = json.load(file)
    if not isinstance(annotations, dict):
        raise TypeError("La anotacion debe ser un objeto JSON nombre_imagen -> texto.")
    if not 0 <= sample_index < len(annotations):
        raise IndexError(
            f"sample-index={sample_index} fuera del intervalo [0, {len(annotations) - 1}]."
        )
    image_name, text = list(annotations.items())[sample_index]
    if not isinstance(image_name, str) or not isinstance(text, str):
        raise TypeError("La muestra seleccionada no contiene nombre y texto de tipo string.")
    image_path = require_path(image_root / image_name, "archivo")
    return image_path, text


def package_version(distribution: str) -> str:
    from importlib.metadata import version

    return version(distribution)


def clip_commit() -> str | None:
    from importlib.metadata import distribution

    direct_url = distribution("clip").read_text("direct_url.json")
    if direct_url is None:
        return None
    return json.loads(direct_url).get("vcs_info", {}).get("commit_id")


def optional_cuda_telemetry(name: str, operation):
    try:
        return {"status": "ok", "value": operation()}
    except RuntimeError as error:
        return {"status": "unsupported_on_this_platform", "error": str(error)}


def build_model(cvg_text_root: Path, checkpoint: Path):
    import torch
    import clip

    sys.path.insert(0, str(cvg_text_root))
    from utils import interpolate_pos_embedding

    model, preprocess = clip.load(MODEL_NAME, device="cpu")
    model = model.float()
    model.positional_embedding = torch.nn.Parameter(
        interpolate_pos_embedding(model.positional_embedding, CONTEXT_LENGTH)
    )
    mask = torch.empty(CONTEXT_LENGTH, CONTEXT_LENGTH)
    mask.fill_(float("-inf"))
    mask.triu_(1)
    for block in model.transformer.resblocks:
        block.attn_mask = mask

    state_dict = torch.load(checkpoint, map_location="cpu", weights_only=True)
    incompatible = model.load_state_dict(state_dict, strict=False)
    missing_keys = list(incompatible.missing_keys)
    unexpected_keys = list(incompatible.unexpected_keys)
    if missing_keys or unexpected_keys:
        raise RuntimeError(
            "Checkpoint incompatible: "
            f"missing_keys={missing_keys}, unexpected_keys={unexpected_keys}"
        )
    return model, preprocess, missing_keys, unexpected_keys


def main() -> int:
    args = parse_args()
    cvg_text_root = require_path(args.cvg_text_root, "directorio")
    checkpoint = require_path(args.checkpoint, "archivo")
    annotation = require_path(args.annotation, "archivo")
    image_root = require_path(args.image_root, "directorio")

    if git_head(cvg_text_root) != EXPECTED_CVG_TEXT_COMMIT:
        raise RuntimeError("El commit de CVG-Text no coincide con la revision fijada.")
    if checkpoint.name != EXPECTED_CHECKPOINT_NAME:
        raise RuntimeError(f"Nombre de checkpoint inesperado: {checkpoint.name}")
    if checkpoint.stat().st_size != EXPECTED_CHECKPOINT_SIZE:
        raise RuntimeError(f"Tamano de checkpoint inesperado: {checkpoint.stat().st_size}")
    checkpoint_sha256 = sha256(checkpoint)
    if checkpoint_sha256 != EXPECTED_CHECKPOINT_SHA256:
        raise RuntimeError(f"SHA-256 de checkpoint inesperado: {checkpoint_sha256}")

    image_path, text = load_sample(annotation, image_root, args.sample_index)

    import torch
    import torchvision
    import clip
    from PIL import Image

    installed_clip_commit = clip_commit()
    if installed_clip_commit != EXPECTED_CLIP_COMMIT:
        raise RuntimeError(f"Commit de OpenAI CLIP inesperado: {installed_clip_commit}")

    model, preprocess, missing_keys, unexpected_keys = build_model(
        cvg_text_root, checkpoint
    )
    model.eval()

    with Image.open(image_path) as image_file:
        image = preprocess(image_file.convert("RGB")).unsqueeze(0)
    tokens = clip.tokenize(text, context_length=CONTEXT_LENGTH, truncate=True)
    if image.shape != (1, 3, 336, 336):
        raise RuntimeError(f"Forma de imagen inesperada: {tuple(image.shape)}")
    if tokens.shape != (1, CONTEXT_LENGTH):
        raise RuntimeError(f"Forma de tokens inesperada: {tuple(tokens.shape)}")
    if not torch.isfinite(image).all():
        raise RuntimeError("El tensor de imagen contiene valores no finitos.")

    result = {
        "status": "cpu_validation_ok" if args.validate_only else "gpu_smoke_ok",
        "platform_adaptation": {
            "description": (
                "Python 3.12, PyTorch 2.11.0+cu130 y torchvision 0.26.0+cu130 "
                "son una adaptacion para ARM64/NVIDIA GB10, no el entorno "
                "software original publicado por CrossText2Loc."
            ),
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "torch_cuda": torch.version.cuda,
            "clip_commit": installed_clip_commit,
        },
        "cvg_text_commit": EXPECTED_CVG_TEXT_COMMIT,
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": checkpoint_sha256,
        "sample_index": args.sample_index,
        "image": str(image_path),
        "text": text,
        "input_image_shape": list(image.shape),
        "input_token_shape": list(tokens.shape),
        "missing_keys": missing_keys,
        "unexpected_keys": unexpected_keys,
    }

    if args.validate_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no esta disponible en el entorno aislado.")
    if torch.cuda.device_count() != 1:
        raise RuntimeError(
            "El smoke test exige exactamente una GPU visible mediante CUDA_VISIBLE_DEVICES."
        )

    device = torch.device("cuda:0")
    torch.cuda.empty_cache()
    memory_telemetry = {
        "reset_peak_memory_stats": optional_cuda_telemetry(
            "reset_peak_memory_stats",
            lambda: torch.cuda.reset_peak_memory_stats(device),
        )
    }
    move_started = time.perf_counter()
    model = model.to(device)
    image = image.to(device)
    tokens = tokens.to(device)
    torch.cuda.synchronize(device)
    move_seconds = time.perf_counter() - move_started

    inference_started = time.perf_counter()
    with torch.inference_mode():
        image_embedding = model.encode_image(image)
        text_embedding = model.encode_text(tokens)
        torch.cuda.synchronize(device)
        inference_seconds = time.perf_counter() - inference_started

        if not torch.isfinite(image_embedding).all():
            raise RuntimeError("El embedding de imagen contiene valores no finitos.")
        if not torch.isfinite(text_embedding).all():
            raise RuntimeError("El embedding de texto contiene valores no finitos.")
        image_norm = image_embedding.norm(dim=-1, keepdim=True)
        text_norm = text_embedding.norm(dim=-1, keepdim=True)
        if not torch.isfinite(image_norm).all() or torch.any(image_norm <= 0):
            raise RuntimeError("Norma invalida en el embedding de imagen.")
        if not torch.isfinite(text_norm).all() or torch.any(text_norm <= 0):
            raise RuntimeError("Norma invalida en el embedding de texto.")
        normalized_image = image_embedding / image_norm
        normalized_text = text_embedding / text_norm
        normalized_image_norm = normalized_image.norm(dim=-1)
        normalized_text_norm = normalized_text.norm(dim=-1)
        if not torch.allclose(
            normalized_image_norm,
            torch.ones_like(normalized_image_norm),
            rtol=1e-5,
            atol=1e-6,
        ):
            raise RuntimeError("La norma L2 normalizada de imagen no es aproximadamente 1.")
        if not torch.allclose(
            normalized_text_norm,
            torch.ones_like(normalized_text_norm),
            rtol=1e-5,
            atol=1e-6,
        ):
            raise RuntimeError("La norma L2 normalizada de texto no es aproximadamente 1.")
        similarity = normalized_image @ normalized_text.t()
        if not torch.isfinite(similarity).all():
            raise RuntimeError("La similitud contiene valores no finitos.")

    for name, operation in {
        "memory_allocated": lambda: torch.cuda.memory_allocated(device),
        "memory_reserved": lambda: torch.cuda.memory_reserved(device),
        "max_memory_allocated": lambda: torch.cuda.max_memory_allocated(device),
        "max_memory_reserved": lambda: torch.cuda.max_memory_reserved(device),
    }.items():
        memory_telemetry[name] = optional_cuda_telemetry(name, operation)

    result.update(
        {
            "device": str(device),
            "gpu_name": torch.cuda.get_device_name(device),
            "gpu_capability": list(torch.cuda.get_device_capability(device)),
            "image_embedding_shape": list(image_embedding.shape),
            "text_embedding_shape": list(text_embedding.shape),
            "image_embedding_dtype": str(image_embedding.dtype),
            "text_embedding_dtype": str(text_embedding.dtype),
            "image_embedding_device": str(image_embedding.device),
            "text_embedding_device": str(text_embedding.device),
            "image_norm_before_l2": image_norm.detach().cpu().flatten().tolist(),
            "text_norm_before_l2": text_norm.detach().cpu().flatten().tolist(),
            "image_norm_after_l2": normalized_image_norm.detach().cpu().flatten().tolist(),
            "text_norm_after_l2": normalized_text_norm.detach().cpu().flatten().tolist(),
            "similarity_functional_check_not_evaluation_metric": float(
                similarity.detach().cpu().item()
            ),
            "model_move_seconds": move_seconds,
            "inference_seconds": inference_seconds,
            "cuda_memory_telemetry": memory_telemetry,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    del normalized_text_norm, normalized_image_norm
    del similarity, normalized_text, normalized_image, text_norm, image_norm
    del text_embedding, image_embedding, tokens, image, model
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize(device)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
