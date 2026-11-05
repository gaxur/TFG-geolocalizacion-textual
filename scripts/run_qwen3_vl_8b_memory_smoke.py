#!/usr/bin/env python3
"""Smoke aislado Qwen3-VL-8B con checkpoints incrementales y atómicos."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time


MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
FIXTURE_SHA256 = "b9468994d5ce0a1ae6a6c7ecd37430926064d6088dfc123b2e2388fb22a033fb"
PROMPT = "Describe brevemente los elementos visuales que aparecen en la imagen. No inventes información que no puedas observar."
MAX_NEW_TOKENS = 64
WEIGHTS = {
    "model-00001-of-00004.safetensors": (4_902_275_944, "d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa"),
    "model-00002-of-00004.safetensors": (4_915_962_496, "8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5"),
    "model-00003-of-00004.safetensors": (4_999_831_048, "83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192"),
    "model-00004-of-00004.safetensors": (2_716_270_024, "0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def json_value(value):
    """Convierte tipos conocidos a JSON; rechaza tipos desconocidos."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    module = type(value).__module__
    if module.startswith("numpy"):
        if hasattr(value, "tolist"):
            return json_value(value.tolist())
        if hasattr(value, "item"):
            return json_value(value.item())
    if module.startswith("torch") and hasattr(value, "numel"):
        if value.numel() == 1:
            return json_value(value.item())
        return json_value(value.detach().cpu().tolist())
    if hasattr(value, "to_dict"):
        return json_value(value.to_dict())
    try:
        return {str(key): json_value(item) for key, item in dict(value).items()}
    except (TypeError, ValueError) as error:
        raise TypeError(f"tipo no serializable explícitamente: {type(value).__module__}.{type(value).__name__}") from error


def atomic_write_json(path: Path, document) -> dict:
    normalized = json_value(document)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if loaded != normalized:
        raise ValueError(f"relectura divergente: {path.name}")
    return loaded


def prevalidate_persistence(path: Path) -> dict:
    import numpy as np
    import torch
    try:
        from transformers.image_processing_utils import SizeDict
        size = SizeDict(shortest_edge=65536, longest_edge=16777216)
    except (ImportError, TypeError):
        size = {"shortest_edge": 65536, "longest_edge": 16777216}
    fixture = {
        "size_dict": size,
        "numpy_scalar": np.int64(7),
        "numpy_float": np.float32(1.5),
        "numpy_array": np.array([[1, 2], [3, 4]], dtype=np.int32),
        "torch_scalar": torch.tensor(9),
        "torch_vector": torch.tensor([1.0, 2.0]),
        "tuple": ("a", 2),
        "list": [True, None],
        "nested": {"optional": None, "processor": {"patch_size": 16}, "tokenizer": {"class": "Qwen2Tokenizer"}},
    }
    loaded = atomic_write_json(path, {"schema_version": "1.0", "contract_version": "persistence-prevalidation-v1", "fixture": fixture})
    expected = {"shortest_edge": 65536, "longest_edge": 16777216}
    if loaded["fixture"]["size_dict"] != expected or loaded["fixture"]["numpy_scalar"] != 7 or loaded["fixture"]["torch_scalar"] != 9:
        raise ValueError("prevalidación de persistencia incompleta")
    return {"status": "PASS", "logical_path": path.name, "sha256": digest(path)}


def system_memory() -> dict:
    values = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    return {"ram_available_bytes": values.get("MemAvailable"), "swap_total_bytes": values.get("SwapTotal"), "swap_free_bytes": values.get("SwapFree"), "swap_used_bytes": values.get("SwapTotal", 0) - values.get("SwapFree", 0)}


def cuda_memory(torch) -> dict:
    return {"allocated_bytes": int(torch.cuda.memory_allocated()), "reserved_bytes": int(torch.cuda.memory_reserved()), "max_allocated_bytes": int(torch.cuda.max_memory_allocated()), "max_reserved_bytes": int(torch.cuda.max_memory_reserved())}


def compute_processes() -> list[dict]:
    command = ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory,gpu_uuid", "--format=csv,noheader,nounits"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return [{"status": "NOT_VERIFIED", "error": completed.stderr.strip()}]
    rows = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 4:
            rows.append({"pid": int(parts[0]), "process_name": parts[1], "used_memory_mib": None if parts[2] in {"N/A", "[N/A]"} else int(parts[2]), "gpu_uuid": parts[3]})
    return rows


def verify_model(model_path: Path) -> dict:
    required = {"config.json", "model.safetensors.index.json", "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json", "chat_template.json", *WEIGHTS}
    if not model_path.is_dir() or not required <= {item.name for item in model_path.iterdir() if item.is_file()}:
        raise ValueError("snapshot Qwen3-VL-8B incompleto")
    metadata = model_path / ".cache/huggingface/download/config.json.metadata"
    if not metadata.is_file() or metadata.read_text(encoding="utf-8").splitlines()[0] != REVISION:
        raise ValueError("revisión local Qwen3-VL-8B incompatible")
    config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
    index = json.loads((model_path / "model.safetensors.index.json").read_text(encoding="utf-8"))
    if config.get("architectures") != ["Qwen3VLForConditionalGeneration"] or config.get("text_config", {}).get("dtype") != "bfloat16":
        raise ValueError("configuración Qwen3-VL-8B incompatible")
    files = {}
    for name, (size, sha256) in WEIGHTS.items():
        path = model_path / name
        if path.stat().st_size != size or digest(path) != sha256:
            raise ValueError(f"integridad incorrecta: {name}")
        files[name] = {"size_bytes": size, "sha256": sha256}
    return {"model_id": MODEL_ID, "revision": REVISION, "directory_name": model_path.name, "architecture": config["architectures"][0], "dtype": "bfloat16", "attention": "sdpa", "quantized": False, "indexed_weight_bytes": index["metadata"]["total_size"], "files": files, "config_sha256": digest(model_path / "config.json"), "processor_sha256": digest(model_path / "preprocessor_config.json"), "tokenizer_sha256": digest(model_path / "tokenizer.json")}


def phase_document(phase: str, payload: dict) -> dict:
    return {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-memory-checkpoint-v2", "phase": phase, "recorded_at_utc": utc_now(), **payload}


def refresh_final_artifacts(output_root: Path) -> dict:
    phase_names = ["m0.json", "m1.json", "m2.json", "m3.json", "m4.json"]
    phases = {name[:-5].upper(): json.loads((output_root / name).read_text(encoding="utf-8")) for name in phase_names if (output_root / name).is_file()}
    status = "PASS" if set(phases) == {"M0", "M1", "M2", "M3", "M4"} and phases["M3"]["status"] == "PASS" else "FAILED"
    metrics = json.loads((output_root / "metrics.json").read_text(encoding="utf-8")) if (output_root / "metrics.json").is_file() else {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-memory-metrics-v2", "latencies_ms": {}}
    metrics.update({"status": status, "completed_phase": max(phases, default="NONE"), "measurements": phases})
    atomic_write_json(output_root / "metrics.json", metrics)
    m1, m2, m3, m4 = (phases.get(name, {}) for name in ("M1", "M2", "M3", "M4"))
    report_lines = [
        "# Smoke aislado Qwen3-VL-8B v2", "", f"- Estado: `{status}`", f"- Última fase: `{metrics['completed_phase']}`",
        f"- Modelo: `{MODEL_ID}` @ `{REVISION}`", f"- Imagen: `{FIXTURE_SHA256}`", "- GT: no", "- Modelos adicionales: no", "",
        "## Recursos", "", f"- CUDA M1 asignada: `{m1.get('cuda', {}).get('allocated_bytes', 'NOT VERIFIED')}` B",
        f"- CUDA pico M3: `{m3.get('cuda', {}).get('max_allocated_bytes', 'NOT VERIFIED')}` B",
        f"- Tokens de entrada: `{m2.get('input', {}).get('input_tokens', 'NOT VERIFIED')}`",
        f"- Tokens visuales: `{m2.get('input', {}).get('visual_tokens', 'NOT VERIFIED')}`",
        f"- Tokens de salida: `{m3.get('output', {}).get('output_tokens', 'NOT VERIFIED')}`",
        f"- Procesos compute externos tras terminar: `{len(m4.get('external_host_observation', {}).get('compute_processes', [])) if m4.get('external_host_observation') else 'NOT VERIFIED'}`", "",
    ]
    (output_root / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
    artifact_names = ["persistence-prevalidation.json", "protocol.json", "preflight.json", "synthetic-visual-fixture.png", *phase_names, "inference-output.json", "metrics.json", "report.md"]
    if (output_root / "error.json").is_file():
        artifact_names.append("error.json")
    artifacts = {name: {"sha256": digest(output_root / name), "size_bytes": (output_root / name).stat().st_size} for name in artifact_names if (output_root / name).is_file()}
    protocol = json.loads((output_root / "protocol.json").read_text(encoding="utf-8"))
    manifest = {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-memory-manifest-v2", "status": status, "completed_phase": metrics["completed_phase"], "artifacts": artifacts, "model": protocol["model"], "image": protocol["image"], "limitations": ["isolated_synthetic_image_smoke", "no_geographic_accuracy", "no_model_coexistence_measured"]}
    atomic_write_json(output_root / "manifest.json", manifest)
    return manifest


def finalize_external(output_root: Path) -> int:
    m4_path = output_root / "m4.json"
    if not m4_path.is_file():
        raise ValueError("M4 interno ausente")
    m4 = json.loads(m4_path.read_text(encoding="utf-8"))
    m4["external_host_observation"] = {"recorded_at_utc": utc_now(), "provenance": "external_process_after_inference_container_exit", "compute_processes": compute_processes(), "system": system_memory()}
    atomic_write_json(m4_path, m4)
    manifest = refresh_final_artifacts(output_root)
    print(json.dumps({"status": manifest["status"], "external_m4": "PASS", "compute_processes": m4["external_host_observation"]["compute_processes"]}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--prevalidate-only", action="store_true")
    parser.add_argument("--finalize-external", action="store_true")
    parser.add_argument("--host-ollama-status", default="NOT_VERIFIED")
    parser.add_argument("--host-compute-process-count", type=int, default=-1)
    args = parser.parse_args()
    if args.finalize_external:
        return finalize_external(args.output_root)
    if args.output_root.exists():
        raise ValueError("output-root ya existe")
    args.output_root.mkdir(parents=True)
    prevalidation = prevalidate_persistence(args.output_root / "persistence-prevalidation.json")
    if args.prevalidate_only:
        print(json.dumps(prevalidation, sort_keys=True))
        return 0
    if args.model_path is None or args.fixture is None:
        raise ValueError("model-path y fixture son obligatorios")
    if digest(args.fixture) != FIXTURE_SHA256:
        raise ValueError("fixture sintético no coincide con v1")
    image_path = args.output_root / "synthetic-visual-fixture.png"
    shutil.copyfile(args.fixture, image_path)
    if digest(image_path) != FIXTURE_SHA256:
        raise ValueError("copia del fixture divergente")
    identity = verify_model(args.model_path)
    protocol = {"prompt": PROMPT, "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(), "max_new_tokens": MAX_NEW_TOKENS, "do_sample": False, "dtype": "bfloat16", "attention": "sdpa", "single_load": True, "single_inference": True, "ground_truth_used": False, "reserved_sets_used": False, "ct2l_loaded": False, "text_qwen_loaded": False, "dialogue_loaded": False, "network_used": False, "downloads": False}
    image_identity = {"kind": "synthetic_generated_locally_v1_reused_byte_exact", "width": 384, "height": 384, "mode": "RGB", "logical_path": image_path.name, "sha256": FIXTURE_SHA256, "size_bytes": image_path.stat().st_size, "contains_personal_data": False, "contains_geographic_ground_truth": False}
    atomic_write_json(args.output_root / "protocol.json", {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-memory-smoke-protocol-v2", "model": identity, "image": image_identity, "generation": protocol, "persistence_prevalidation": prevalidation})

    import torch
    import transformers
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no disponible")
    preflight = {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-memory-preflight-v2", "recorded_at_utc": utc_now(), "status": "PASS_WITH_UNIFIED_MEMORY_NOT_VERIFIED", "gpu": {"name": torch.cuda.get_device_name(0), "cuda_runtime": torch.version.cuda, "memory_total_bytes": "NOT_VERIFIED", "memory_free_bytes": "NOT_VERIFIED", "reason": "NVML memory fields are unsupported on GB10 unified memory"}, "host_compute_process_count_before_container": args.host_compute_process_count, "container_compute_processes_after_cuda_init": compute_processes(), "ollama": {"status": args.host_ollama_status, "action_taken": "none"}, "system": system_memory(), "model_identity_verified": True, "fixture_sha256": FIXTURE_SHA256}
    if args.host_compute_process_count != 0:
        raise RuntimeError("preflight host no acredita cero procesos compute")
    atomic_write_json(args.output_root / "preflight.json", preflight)
    total_started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    environment = {"python": sys.version.split()[0], "torch": torch.__version__, "transformers": transformers.__version__, "cuda_runtime": torch.version.cuda, "device": torch.cuda.get_device_name(0)}
    m0 = phase_document("M0", {"status": "PASS", "environment": environment, "configuration": protocol, "cuda": cuda_memory(torch), "system": system_memory(), "compute_processes": compute_processes()})
    atomic_write_json(args.output_root / "m0.json", m0)
    processor = model = inputs = generated = trimmed = None
    latencies = {}
    completed_phase = "M0"
    error_document = None
    try:
        processor_started = time.perf_counter()
        processor = AutoProcessor.from_pretrained(args.model_path, local_files_only=True)
        latencies["processor_load_ms"] = (time.perf_counter() - processor_started) * 1000
        processor_identity = {"class": type(processor).__name__, "tokenizer_class": type(processor.tokenizer).__name__, "image_processor_class": type(processor.image_processor).__name__, "patch_size": getattr(processor.image_processor, "patch_size", None), "temporal_patch_size": getattr(processor.image_processor, "temporal_patch_size", None), "merge_size": getattr(processor.image_processor, "merge_size", None), "size": json_value(getattr(processor.image_processor, "size", None)), "tokenizer_vocab_size": getattr(processor.tokenizer, "vocab_size", None)}
        load_started = time.perf_counter()
        model = Qwen3VLForConditionalGeneration.from_pretrained(args.model_path, local_files_only=True, dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa")
        model.eval()
        torch.cuda.synchronize()
        latencies["weights_load_and_cuda_transfer_ms"] = (time.perf_counter() - load_started) * 1000
        tensor_count = len(model.state_dict())
        m1 = phase_document("M1", {"status": "PASS", "model": identity, "processor": processor_identity, "dtype": str(next(model.parameters()).dtype), "device": str(next(model.parameters()).device), "tensor_count": tensor_count, "latencies_ms": {"processor_load": latencies["processor_load_ms"], "weights_load_and_cuda_transfer": latencies["weights_load_and_cuda_transfer_ms"]}, "cuda": cuda_memory(torch), "system": system_memory()})
        atomic_write_json(args.output_root / "m1.json", m1); completed_phase = "M1"

        image = Image.open(image_path).convert("RGB")
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": PROMPT}]}]
        preprocessing_started = time.perf_counter()
        inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt").to(model.device)
        torch.cuda.synchronize()
        latencies["preprocessing_and_transfer_ms"] = (time.perf_counter() - preprocessing_started) * 1000
        visual_grid = inputs.get("image_grid_thw")
        visual_tokens = int(visual_grid.prod(dim=1).sum().item() // (processor.image_processor.merge_size ** 2)) if visual_grid is not None else None
        input_identity = {"original_dimensions": [384, 384], "input_tokens": int(inputs.input_ids.shape[1]), "pixel_values_shape": list(inputs.pixel_values.shape) if "pixel_values" in inputs else None, "image_grid_thw": visual_grid.tolist() if visual_grid is not None else None, "visual_tokens": visual_tokens}
        m2 = phase_document("M2", {"status": "PASS", "image": image_identity, "processor": processor_identity, "input": input_identity, "latencies_ms": {"preprocessing_and_transfer": latencies["preprocessing_and_transfer_ms"]}, "cuda": cuda_memory(torch), "system": system_memory()})
        atomic_write_json(args.output_root / "m2.json", m2); completed_phase = "M2"

        generation_started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
        torch.cuda.synchronize()
        latencies["generation_ms"] = (time.perf_counter() - generation_started) * 1000
        trimmed = generated[:, inputs.input_ids.shape[1]:]
        decoding_started = time.perf_counter()
        raw = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        latencies["decoding_ms"] = (time.perf_counter() - decoding_started) * 1000
        output = {"raw": raw, "decoded": raw.strip(), "output_tokens": int(trimmed.shape[1]), "validation": {"nonempty": bool(raw.strip()), "geographic_claim_evaluated": False}}
        atomic_write_json(args.output_root / "inference-output.json", {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-inference-output-v1", "prompt": PROMPT, "image_sha256": FIXTURE_SHA256, "output": output})
        m3 = phase_document("M3", {"status": "PASS" if raw.strip() else "FAILED_EMPTY_OUTPUT", "output": output, "latencies_ms": {"generation": latencies["generation_ms"], "decoding": latencies["decoding_ms"]}, "cuda": cuda_memory(torch), "system": system_memory()})
        atomic_write_json(args.output_root / "m3.json", m3); completed_phase = "M3"
        if not raw.strip():
            raise RuntimeError("salida VLM vacía")
    except Exception as error:
        error_document = {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-memory-error-v1", "completed_phase": completed_phase, "type": type(error).__name__, "message": str(error), "pending_phases": [phase for phase in ("M1", "M2", "M3") if int(phase[1]) > int(completed_phase[1])], "automatic_retry": False}
        atomic_write_json(args.output_root / "error.json", error_document)
    finally:
        release_started = time.perf_counter()
        del trimmed, generated, inputs, model, processor
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        latencies["release_ms"] = (time.perf_counter() - release_started) * 1000
        latencies["total_runtime_ms"] = (time.perf_counter() - total_started) * 1000
        m4 = phase_document("M4", {"status": "PASS", "own_references_deleted": True, "empty_cache_called_after_reference_deletion": True, "latencies_ms": {"release": latencies["release_ms"]}, "cuda": cuda_memory(torch), "system": system_memory(), "compute_processes_inside_container": compute_processes()})
        atomic_write_json(args.output_root / "m4.json", m4)

    status = "PASS" if completed_phase == "M3" and error_document is None else "FAILED"
    metrics = {"schema_version": "1.0", "contract_version": "qwen3-vl-8b-memory-metrics-v2", "status": status, "completed_phase": completed_phase, "latencies_ms": latencies, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, "disk_free_bytes_after": shutil.disk_usage(args.output_root).free, "measurements": {name: json.loads((args.output_root / f"{name.lower()}.json").read_text()) for name in ("M0", "M1", "M2", "M3", "M4") if (args.output_root / f"{name.lower()}.json").is_file()}}
    atomic_write_json(args.output_root / "metrics.json", metrics)
    refresh_final_artifacts(args.output_root)
    print(json.dumps({"status": status, "completed_phase": completed_phase, "output_root": str(args.output_root)}, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
