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
    compare_human,
    parse_verification,
    verification_prompt,
)

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
REVISION = "89644892e4d85e24eaac8bacfd4f463576704203"
WEIGHT_SHA256 = "7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0"
WEIGHT_SIZE_BYTES = 4_255_140_312
SAMPLE_IMAGE_IDS = ("1210433070142949", "1539904880777289", "483221386454901")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke aislado Qwen3-VL-2B sin GT ni reranking")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=ROOT / "results/generated/mapillary/visual-pilot-v1/selection.json")
    parser.add_argument("--photos", type=Path, default=ROOT / "results/generated/mapillary/visual-pilot-v1/photo-manifest.json")
    parser.add_argument("--annotations", type=Path, default=ROOT / "results/generated/mapillary/visual-pilot-v1/annotations.json")
    parser.add_argument("--source-spec", type=Path, default=ROOT / "config/madrid_h11_h25_independent.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()
    if not args.model_path.is_dir() or not 32 <= args.max_new_tokens <= 512:
        raise VLMSmokeError("modelo local ausente o límite de tokens inválido")
    weight_path = args.model_path / "model.safetensors"
    if not weight_path.is_file() or weight_path.stat().st_size != WEIGHT_SIZE_BYTES or digest(weight_path) != WEIGHT_SHA256:
        raise VLMSmokeError("pesos Qwen3-VL no corresponden a la revisión autorizada")

    import psutil
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    photos_doc = json.loads(args.photos.read_text(encoding="utf-8"))
    annotations_doc = json.loads(args.annotations.read_text(encoding="utf-8"))
    source = json.loads(args.source_spec.read_text(encoding="utf-8"))
    candidates = {row["candidate_id"]: row for row in selection["candidates"]}
    photos = {row["image_id"]: row for row in photos_doc["photos"]}
    annotations = {row["image_id"]: row for row in annotations_doc["records"] if row["image_id"]}
    descriptions = {row["query_id"]: row["text"] for row in source["observations"]}
    samples = []
    for image_id in SAMPLE_IMAGE_IDS:
        photo, human = photos[image_id], annotations[image_id]
        candidate = candidates[photo["candidate_id"]]
        path = args.photos.parent / photo["logical_path"]
        if photo["status"] != "downloaded" or digest(path) != photo["sha256"] or human["review_status"] != "reviewed":
            raise VLMSmokeError(f"muestra no trazable: {image_id}")
        samples.append((candidate, photo, human, path, descriptions[candidate["query_id"]]))

    process = psutil.Process()
    started_at = utc_now()
    wall_start = time.perf_counter()
    rss_before = process.memory_info().rss
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_start = time.perf_counter()
    processor = AutoProcessor.from_pretrained(args.model_path, local_files_only=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        args.model_path,
        local_files_only=True,
        dtype=torch.bfloat16,
        device_map="cuda",
        attn_implementation="sdpa",
    )
    model.eval()
    load_seconds = time.perf_counter() - load_start
    records = []
    try:
        for candidate, photo, human, path, description in samples:
            prompt = verification_prompt(description, candidate["candidate_id"])
            messages = [{"role": "user", "content": [{"type": "image", "image": Image.open(path).convert("RGB")}, {"type": "text", "text": prompt}]}]
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
                parsed = parse_verification(raw)
                error = None
            except VLMSmokeError as parse_error:
                parsed = None
                error = str(parse_error)
            records.append({
                "candidate_id": candidate["candidate_id"],
                "image_id": photo["image_id"],
                "image_sha256": photo["sha256"],
                "input": {"description": description, "candidate_id": candidate["candidate_id"]},
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "raw_output": raw,
                "parsed_output": parsed,
                "contract_error": error,
                "inference_seconds": infer_seconds,
                "input_tokens": int(inputs.input_ids.shape[1]),
                "output_tokens": int(trimmed.shape[1]),
                "human_comparison": compare_human(parsed, human) if parsed else {"human_utility": human["utility"], "level_agreement": False},
            })
    finally:
        del model
        torch.cuda.empty_cache()

    result = {
        "schema_version": "1.0",
        "contract_version": "mapillary-qwen3-vl-isolated-smoke-v1",
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "model": {"model_id": MODEL_ID, "revision": REVISION, "local_directory_name": args.model_path.name, "weight_file": "model.safetensors", "weight_size_bytes": WEIGHT_SIZE_BYTES, "weight_sha256": WEIGHT_SHA256, "dtype": "bfloat16", "attention": "sdpa"},
        "protocol": {"isolated": True, "ground_truth_used": False, "reranking_performed": False, "cross_text2loc_modified": False, "sample_policy": "one useful, one partially_useful, one not_useful; fixed before inference", "do_sample": False, "max_new_tokens": args.max_new_tokens},
        "inputs": {"selection_sha256": digest(args.selection), "photo_manifest_sha256": digest(args.photos), "annotations_sha256": digest(args.annotations), "source_spec_sha256": digest(args.source_spec), "image_ids": list(SAMPLE_IMAGE_IDS)},
        "environment": {"python": sys.version.split()[0], "torch": torch.__version__, "transformers": __import__("transformers").__version__, "cuda": torch.version.cuda, "device": torch.cuda.get_device_name(0)},
        "resources": {"model_load_seconds": load_seconds, "total_seconds": time.perf_counter() - wall_start, "rss_before_bytes": rss_before, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(), "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(), "disk_free_bytes_after": shutil.disk_usage(args.model_path).free},
        "summary": {"samples": len(records), "contract_valid": sum(row["contract_error"] is None for row in records), "level_agreements": sum(row["human_comparison"]["level_agreement"] for row in records)},
        "records": records,
        "limitations": ["three_image_development_smoke", "human_utility_is_not_ground_truth", "semantic_lists_compared_descriptively", "no_reranking", "no_cross_text2loc_execution"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result) + b"\n")
    print(json.dumps({"output": str(args.output), **result["summary"], **result["resources"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
