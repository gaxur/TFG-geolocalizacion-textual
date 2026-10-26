#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import canonical_bytes  # noqa: E402
from src.tfg_phase0.mapillary_vlm_smoke import (  # noqa: E402
    VLMSmokeError,
    conservative_verification_prompt,
    parse_verification,
)

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
REVISION = "89644892e4d85e24eaac8bacfd4f463576704203"
WEIGHT_SHA256 = "7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0"
WEIGHT_SIZE_BYTES = 4_255_140_312
PROMPT_VERSION = "mapillary-visual-verification-conservative-v2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluación conservadora Qwen3-VL-2B sobre 24 fotografías, sin GT ni reranking")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=ROOT / "results/generated/mapillary/visual-pilot-v1/selection.json")
    parser.add_argument("--photos", type=Path, default=ROOT / "results/generated/mapillary/visual-pilot-v1/photo-manifest.json")
    parser.add_argument("--source-spec", type=Path, default=ROOT / "config/madrid_h11_h25_independent.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    weight_path = args.model_path / "model.safetensors"
    if not weight_path.is_file() or weight_path.stat().st_size != WEIGHT_SIZE_BYTES or digest(weight_path) != WEIGHT_SHA256:
        raise VLMSmokeError("pesos Qwen3-VL no corresponden a la revisión autorizada")
    if shutil.disk_usage(args.model_path).free < 1_000_000_000:
        raise VLMSmokeError("margen de disco inferior a 1 GB")

    # Este proceso no abre anotaciones humanas. Solo une texto, candidato opaco e imagen.
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    photos_doc = json.loads(args.photos.read_text(encoding="utf-8"))
    source = json.loads(args.source_spec.read_text(encoding="utf-8"))
    candidates = {row["candidate_id"]: row for row in selection["candidates"]}
    descriptions = {row["query_id"]: row["text"] for row in source["observations"]}
    samples = []
    seen = set()
    for photo in photos_doc["photos"]:
        if photo["status"] != "downloaded" or photo["image_id"] in seen:
            raise VLMSmokeError("manifest fotográfico incompleto o duplicado")
        seen.add(photo["image_id"])
        candidate = candidates.get(photo["candidate_id"])
        if candidate is None:
            raise VLMSmokeError("fotografía sin candidato congelado")
        path = args.photos.parent / photo["logical_path"]
        if not path.is_file() or digest(path) != photo["sha256"]:
            raise VLMSmokeError(f"hash de fotografía inválido: {photo['image_id']}")
        samples.append((candidate["candidate_id"], photo, path, descriptions[candidate["query_id"]]))
    if len(samples) != 24:
        raise VLMSmokeError("la evaluación v2 exige exactamente 24 fotografías")

    import psutil
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    process = psutil.Process()
    started = utc_now()
    wall_start = time.perf_counter()
    rss_before = process.memory_info().rss
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_start = time.perf_counter()
    processor = AutoProcessor.from_pretrained(args.model_path, local_files_only=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        args.model_path, local_files_only=True, dtype=torch.bfloat16,
        device_map="cuda", attn_implementation="sdpa",
    )
    model.eval()
    load_seconds = time.perf_counter() - load_start
    records = []
    try:
        for candidate_id, photo, path, description in samples:
            prompt = conservative_verification_prompt(description, candidate_id)
            with Image.open(path) as opened:
                image = opened.convert("RGB")
            messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
            inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt").to(model.device)
            torch.cuda.synchronize()
            infer_start = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            torch.cuda.synchronize()
            infer_seconds = time.perf_counter() - infer_start
            trimmed = generated[:, inputs.input_ids.shape[1]:]
            raw = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
            try:
                parsed, error = parse_verification(raw), None
            except VLMSmokeError as parse_error:
                parsed, error = None, str(parse_error)
            records.append({
                "candidate_id": candidate_id, "image_id": photo["image_id"],
                "image_sha256": photo["sha256"],
                "input": {"description": description, "candidate_id": candidate_id},
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "raw_output": raw, "parsed_output": parsed, "contract_error": error,
                "inference_seconds": infer_seconds, "input_tokens": int(inputs.input_ids.shape[1]),
                "output_tokens": int(trimmed.shape[1]),
            })
    finally:
        del model
        torch.cuda.empty_cache()

    result = {
        "schema_version": "1.0",
        "contract_version": "mapillary-qwen3-vl-conservative-evaluation-v2",
        "started_at_utc": started, "finished_at_utc": utc_now(),
        "model": {"model_id": MODEL_ID, "revision": REVISION, "weight_sha256": WEIGHT_SHA256, "weight_size_bytes": WEIGHT_SIZE_BYTES, "dtype": "bfloat16", "attention": "sdpa"},
        "protocol": {"prompt_version": PROMPT_VERSION, "isolated": True, "annotations_loaded_during_inference": False, "ground_truth_used": False, "reranking_performed": False, "cross_text2loc_modified": False, "candidates_or_rankings_modified": False, "do_sample": False, "max_new_tokens": args.max_new_tokens, "development_pilot_overlap_image_ids": ["1210433070142949", "1539904880777289", "483221386454901"]},
        "inputs": {"selection_sha256": digest(args.selection), "photo_manifest_sha256": digest(args.photos), "source_spec_sha256": digest(args.source_spec), "image_count": len(samples)},
        "environment": {"python": sys.version.split()[0], "torch": torch.__version__, "transformers": __import__("transformers").__version__, "cuda": torch.version.cuda, "device": torch.cuda.get_device_name(0)},
        "resources": {"model_load_seconds": load_seconds, "total_seconds": time.perf_counter() - wall_start, "rss_before_bytes": rss_before, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(), "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(), "disk_free_bytes_after": shutil.disk_usage(args.model_path).free},
        "summary": {"images": len(records), "contract_valid": sum(row["contract_error"] is None for row in records)},
        "records": records,
        "limitations": ["development_set_includes_three_prompt_design_images", "no_independent_test", "no_reranking", "no_ground_truth", "outputs_require_post_inference_human_adjudication"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result) + b"\n")
    print(json.dumps({"output": str(args.output), **result["summary"], **result["resources"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
