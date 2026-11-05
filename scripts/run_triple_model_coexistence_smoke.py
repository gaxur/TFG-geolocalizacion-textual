#!/usr/bin/env python3
"""Valida coexistencia secuencial de CT2L, Qwen3-8B y Qwen3-VL-8B."""

from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_qwen3_vl_8b_memory_smoke import (
    FIXTURE_SHA256,
    MAX_NEW_TOKENS,
    MODEL_ID as VLM_MODEL_ID,
    PROMPT as VLM_PROMPT,
    REVISION as VLM_REVISION,
    atomic_write_json,
    cuda_memory,
    digest,
    json_value,
    prevalidate_persistence,
    system_memory,
    utc_now,
    verify_model,
)
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, load_runtime_config
from src.tfg_phase0.f5_text_transform import GenerationConfig, QwenTransformersAdapter
from src.tfg_phase0.interactive_dialogue import QWEN_MODEL_ID, QWEN_REVISION


CT2L_TEXT = "Estoy en una calle urbana con varios edificios y comercios"
QWEN_PROMPT = "Responde exactamente con una frase breve: sistema textual operativo."
QWEN_MAX_NEW_TOKENS = 24
MINIMUM_RAM_BEFORE_VLM_BYTES = 40 * 1024**3
MAXIMUM_SWAP_GROWTH_BEFORE_VLM_BYTES = 1024**3


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


def memory_pressure() -> dict:
    path = Path("/proc/pressure/memory")
    if not path.is_file():
        return {"status": "NOT_VERIFIED"}
    return {"status": "VERIFIED", "raw": path.read_text(encoding="ascii").strip()}


def measurement(torch) -> dict:
    torch.cuda.synchronize()
    return {"cuda": cuda_memory(torch), "system": system_memory(), "memory_pressure": memory_pressure(), "compute_processes": compute_processes()}


def phase(name: str, payload: dict) -> dict:
    return {"schema_version": "1.0", "contract_version": "triple-model-coexistence-checkpoint-v1", "phase": name, "recorded_at_utc": utc_now(), **payload}


def own_processes_only(rows: list[dict], own_pid: int | None = None) -> bool:
    own_pid = os.getpid() if own_pid is None else own_pid
    if any("status" in row for row in rows):
        return False
    return all(row.get("pid") == own_pid and row.get("process_name") in {"python", "python3", "/usr/local/bin/python", "/usr/bin/python3"} for row in rows)


def verify_qwen_text(model_path: Path) -> dict:
    metadata = model_path / ".cache/huggingface/download/config.json.metadata"
    config = model_path / "config.json"
    if not model_path.is_dir() or not config.is_file() or not metadata.is_file():
        raise ValueError("snapshot Qwen3-8B ausente")
    raw = json.loads(config.read_text(encoding="utf-8"))
    if raw.get("architectures") != ["Qwen3ForCausalLM"] or raw.get("torch_dtype") != "bfloat16":
        raise ValueError("configuración Qwen3-8B incompatible")
    revision = metadata.read_text(encoding="utf-8").splitlines()[0]
    if revision != QWEN_REVISION:
        raise ValueError("revisión Qwen3-8B incompatible")
    from src.tfg_phase0.f5_text_transform import hash_tree_manifest
    artifact_manifest_sha256 = hash_tree_manifest(model_path)
    if artifact_manifest_sha256 != "d95b2ee5a666c88adcb53094740c1002718f28e0dcabad56a508a9c66dce1570": raise ValueError("manifest Qwen3-8B incompatible")
    return {"model_id": QWEN_MODEL_ID, "revision": revision, "config_sha256": digest(config), "artifact_manifest_sha256": artifact_manifest_sha256, "dtype": "bfloat16", "quantized": False}


def refresh_manifest(output_root: Path, model_identities: dict) -> dict:
    names = ["persistence-prevalidation.json", "protocol.json", "preflight.json", "c0.json", "c1.json", "c2.json", "c3-gate.json", "c3.json", "inference-ct2l.json", "inference-qwen-text.json", "inference-vlm.json", "release.json", "metrics.json", "report.md"]
    if (output_root / "error.json").is_file():
        names.append("error.json")
    artifacts = {name: {"sha256": digest(output_root / name), "size_bytes": (output_root / name).stat().st_size} for name in names if (output_root / name).is_file()}
    required = {"c0.json", "c1.json", "c2.json", "c3.json", "inference-ct2l.json", "inference-qwen-text.json", "inference-vlm.json", "release.json"}
    status = "PASS" if required <= set(artifacts) and not (output_root / "error.json").exists() else "FAILED"
    def load(name):
        path = output_root / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    c0, c1, c2, c3 = (load(name) for name in ("c0.json", "c1.json", "c2.json", "c3.json"))
    ct2l, text, visual, release = (load(name) for name in ("inference-ct2l.json", "inference-qwen-text.json", "inference-vlm.json", "release.json"))
    report_lines = [
        "# Triple model coexistence smoke v1", "", f"- Status: `{status}`", "- Ground truth: no", "- DialogueVPR invoked: no", "",
        "## Loads", "", f"- C1 CT2L allocated: `{c1.get('measurement', {}).get('cuda', {}).get('allocated_bytes', 'NOT VERIFIED')}` B",
        f"- C2 CT2L + Qwen text allocated: `{c2.get('measurement', {}).get('cuda', {}).get('allocated_bytes', 'NOT VERIFIED')}` B",
        f"- C3 triple allocated: `{c3.get('measurement', {}).get('cuda', {}).get('allocated_bytes', 'NOT VERIFIED')}` B",
        f"- C3 swap used: `{c3.get('measurement', {}).get('system', {}).get('swap_used_bytes', 'NOT VERIFIED')}` B", "",
        "## Sequential inference", "", f"- CT2L results: `{ct2l.get('result_count', 'NOT VERIFIED')}`; latency `{ct2l.get('latency_ms', 'NOT VERIFIED')}` ms",
        f"- Qwen text tokens: `{text.get('output_tokens', 'NOT VERIFIED')}`; latency `{text.get('latency_ms', 'NOT VERIFIED')}` ms",
        f"- VLM tokens: `{visual.get('output_tokens', 'NOT VERIFIED')}`; latency `{visual.get('latency_ms', 'NOT VERIFIED')}` ms",
        f"- Joint peak CUDA allocated: `{visual.get('measurement', {}).get('cuda', {}).get('max_allocated_bytes', 'NOT VERIFIED')}` B",
        f"- External compute processes after exit: `{len(release.get('external_host_observation', {}).get('compute_processes', [])) if release.get('external_host_observation') else 'NOT VERIFIED'}`", "",
    ]
    (output_root / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
    artifacts["report.md"] = {"sha256": digest(output_root / "report.md"), "size_bytes": (output_root / "report.md").stat().st_size}
    manifest = {"schema_version": "1.0", "contract_version": "triple-model-coexistence-manifest-v1", "status": status, "models": model_identities, "artifacts": artifacts, "limitations": ["single_process_sequential_inference", "synthetic_visual_fixture", "no_ground_truth", "no_dialogue_integration"]}
    atomic_write_json(output_root / "manifest.json", manifest)
    return manifest


def finalize_external(output_root: Path) -> int:
    release_path = output_root / "release.json"
    if not release_path.is_file():
        raise ValueError("checkpoint de liberación ausente")
    release = json.loads(release_path.read_text(encoding="utf-8"))
    release["external_host_observation"] = {"recorded_at_utc": utc_now(), "compute_processes": compute_processes(), "system": system_memory(), "memory_pressure": memory_pressure(), "provenance": "host_after_inference_container_exit"}
    atomic_write_json(release_path, release)
    protocol = json.loads((output_root / "protocol.json").read_text(encoding="utf-8"))
    manifest = refresh_manifest(output_root, protocol["models"])
    print(json.dumps({"status": manifest["status"], "compute_processes": release["external_host_observation"]["compute_processes"]}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--ct2l-config", type=Path, default=ROOT / "config/madrid_f46_retriever.json")
    parser.add_argument("--clip-weights", type=Path)
    parser.add_argument("--cvg-utils-sha256")
    parser.add_argument("--qwen-model-dir", type=Path)
    parser.add_argument("--vlm-model-dir", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--host-compute-process-count", type=int, default=-1)
    parser.add_argument("--host-ollama-status", default="NOT_VERIFIED")
    parser.add_argument("--prevalidate-only", action="store_true")
    parser.add_argument("--finalize-external", action="store_true")
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
    if None in (args.clip_weights, args.cvg_utils_sha256, args.qwen_model_dir, args.vlm_model_dir, args.fixture):
        raise ValueError("faltan recursos obligatorios")
    if digest(args.fixture) != FIXTURE_SHA256:
        raise ValueError("fixture visual incompatible")

    vlm_identity = verify_model(args.vlm_model_dir)
    text_identity = verify_qwen_text(args.qwen_model_dir)
    model_config, galleries = load_runtime_config(args.ct2l_config, project_root=ROOT, cvg_utils_sha256=args.cvg_utils_sha256, clip_weights_path=args.clip_weights)
    selected = [value for value in galleries if value.gallery_id == "madrid-50m"]
    if len(selected) != 1:
        raise ValueError("galería madrid-50m no configurada de forma única")
    ct2l_identity = {"checkpoint_sha256": "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d", "gallery_id": "madrid-50m", "candidate_count": 253, "dtype": "float32"}
    models = {"ct2l": ct2l_identity, "qwen_text": text_identity, "qwen_vl": vlm_identity}
    protocol = {"schema_version": "1.0", "contract_version": "triple-model-coexistence-protocol-v1", "models": models, "loads": ["ct2l", "qwen_text", "qwen_vl"], "inferences": ["ct2l", "qwen_text", "qwen_vl"], "sequential": True, "same_process": True, "ground_truth_used": False, "reserved_sets_used": False, "network_used": False, "downloads": False, "training": False, "quantization": False, "offloading": False, "intermediate_gate": {"minimum_ram_available_bytes": MINIMUM_RAM_BEFORE_VLM_BYTES, "maximum_swap_growth_bytes": MAXIMUM_SWAP_GROWTH_BEFORE_VLM_BYTES, "foreign_compute_processes_allowed": 0}, "inputs": {"ct2l_text": CT2L_TEXT, "qwen_prompt": QWEN_PROMPT, "qwen_max_new_tokens": QWEN_MAX_NEW_TOKENS, "vlm_prompt": VLM_PROMPT, "vlm_max_new_tokens": MAX_NEW_TOKENS, "fixture_sha256": FIXTURE_SHA256}}
    atomic_write_json(args.output_root / "protocol.json", protocol)

    import torch
    import transformers
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    if not torch.cuda.is_available() or args.host_compute_process_count != 0:
        raise RuntimeError("preflight host incompatible")
    preflight = {"schema_version": "1.0", "contract_version": "triple-model-coexistence-preflight-v1", "recorded_at_utc": utc_now(), "status": "PASS_WITH_UNIFIED_MEMORY_NOT_VERIFIED", "gpu": {"name": torch.cuda.get_device_name(0), "cuda_runtime": torch.version.cuda, "memory_total": "NOT_VERIFIED", "memory_free": "NOT_VERIFIED"}, "host_compute_process_count": args.host_compute_process_count, "ollama": args.host_ollama_status, "system": system_memory(), "memory_pressure": memory_pressure()}
    atomic_write_json(args.output_root / "preflight.json", preflight)
    total_started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    c0_memory = measurement(torch)
    atomic_write_json(args.output_root / "c0.json", phase("C0", {"status": "PASS", "configuration": protocol, "measurement": c0_memory}))

    runtime = text_runtime = vlm = processor = ct2l_result = text_result = vlm_inputs = vlm_generated = trimmed = image = None
    completed = "C0"
    error_document = None
    latencies = {}
    try:
        started = time.perf_counter()
        runtime = CrossText2LocRetriever.load(model_config=model_config, gallery_configs=selected, region_config=ROOT / "config/madrid.yaml")
        torch.cuda.synchronize(); latencies["ct2l_load_ms"] = (time.perf_counter() - started) * 1000
        if runtime.gallery_count("madrid-50m") != 253:
            raise RuntimeError("cardinalidad CT2L incompatible")
        atomic_write_json(args.output_root / "c1.json", phase("C1", {"status": "PASS", "model": ct2l_identity, "load_ms": latencies["ct2l_load_ms"], "models_resident": ["ct2l"], "measurement": measurement(torch)})); completed = "C1"

        started = time.perf_counter()
        text_runtime = QwenTransformersAdapter(args.qwen_model_dir, model_id=QWEN_MODEL_ID, revision=QWEN_REVISION)
        torch.cuda.synchronize(); latencies["qwen_text_load_ms"] = (time.perf_counter() - started) * 1000
        c2_memory = measurement(torch)
        atomic_write_json(args.output_root / "c2.json", phase("C2", {"status": "PASS", "model": text_identity, "load_ms": latencies["qwen_text_load_ms"], "models_resident": ["ct2l", "qwen_text"], "measurement": c2_memory})); completed = "C2"

        swap_growth = max(0, c2_memory["system"]["swap_used_bytes"] - c0_memory["system"]["swap_used_bytes"])
        gate_processes = compute_processes()
        gate = {"ram_available_bytes": c2_memory["system"]["ram_available_bytes"], "swap_growth_bytes": swap_growth, "compute_processes": gate_processes, "own_processes_only": own_processes_only(gate_processes, os.getpid()), "minimum_ram_available_bytes": MINIMUM_RAM_BEFORE_VLM_BYTES, "maximum_swap_growth_bytes": MAXIMUM_SWAP_GROWTH_BEFORE_VLM_BYTES}
        gate["passed"] = gate["ram_available_bytes"] >= MINIMUM_RAM_BEFORE_VLM_BYTES and swap_growth <= MAXIMUM_SWAP_GROWTH_BEFORE_VLM_BYTES and gate["own_processes_only"]
        atomic_write_json(args.output_root / "c3-gate.json", phase("C3_GATE", {"status": "PASS" if gate["passed"] else "BLOCKED", "gate": gate}))
        if not gate["passed"]:
            raise RuntimeError("gate intermedio bloqueó carga VLM")

        started = time.perf_counter()
        processor = AutoProcessor.from_pretrained(args.vlm_model_dir, local_files_only=True)
        vlm = Qwen3VLForConditionalGeneration.from_pretrained(args.vlm_model_dir, local_files_only=True, dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa")
        vlm.eval(); torch.cuda.synchronize(); latencies["vlm_load_ms"] = (time.perf_counter() - started) * 1000
        resident_checks = {"ct2l_encoder_present": runtime._encoder._model is not None, "qwen_text_model_present": text_runtime._model is not None, "qwen_vl_model_present": vlm is not None}
        if not all(resident_checks.values()):
            raise RuntimeError("algún modelo no permanece residente en C3")
        atomic_write_json(args.output_root / "c3.json", phase("C3", {"status": "PASS", "model": vlm_identity, "load_ms": latencies["vlm_load_ms"], "models_resident": ["ct2l", "qwen_text", "qwen_vl"], "resident_checks": resident_checks, "measurement": measurement(torch)})); completed = "C3"

        started = time.perf_counter()
        ct2l_result = runtime.retrieve(gallery_id="madrid-50m", query_id="triple-coexistence-ct2l", text=CT2L_TEXT, language="es", k=253)
        torch.cuda.synchronize(); latencies["ct2l_inference_ms"] = (time.perf_counter() - started) * 1000
        atomic_write_json(args.output_root / "inference-ct2l.json", {"schema_version": "1.0", "contract_version": "triple-coexistence-ct2l-inference-v1", "input": CT2L_TEXT, "gallery_count": ct2l_result["gallery_count"], "result_count": len(ct2l_result["results"]), "top1": ct2l_result["results"][0], "latency_ms": latencies["ct2l_inference_ms"], "measurement": measurement(torch), "ground_truth_used": False})

        started = time.perf_counter()
        text_messages = [{"role": "user", "content": QWEN_PROMPT}]
        try:
            text_rendered = text_runtime._tokenizer.apply_chat_template(text_messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            text_rendered = text_runtime._tokenizer.apply_chat_template(text_messages, tokenize=False, add_generation_prompt=True)
        text_input_tokens = len(text_runtime._tokenizer(text_rendered)["input_ids"])
        text_result = text_runtime.generate_prompt(QWEN_PROMPT, GenerationConfig(max_new_tokens=QWEN_MAX_NEW_TOKENS))
        torch.cuda.synchronize(); latencies["qwen_text_inference_ms"] = (time.perf_counter() - started) * 1000
        text_output_tokens = len(text_runtime._tokenizer(text_result.raw_output)["input_ids"])
        atomic_write_json(args.output_root / "inference-qwen-text.json", {"schema_version": "1.0", "contract_version": "triple-coexistence-qwen-text-inference-v1", "prompt": QWEN_PROMPT, "raw_output": text_result.raw_output, "processed_output": text_result.text, "input_tokens": text_input_tokens, "output_tokens": text_output_tokens, "latency_ms": latencies["qwen_text_inference_ms"], "measurement": measurement(torch), "do_sample": False, "max_new_tokens": QWEN_MAX_NEW_TOKENS})

        image = Image.open(args.fixture).convert("RGB")
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": VLM_PROMPT}]}]
        vlm_inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt").to(vlm.device)
        started = time.perf_counter()
        with torch.inference_mode():
            vlm_generated = vlm.generate(**vlm_inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
        torch.cuda.synchronize(); latencies["vlm_inference_ms"] = (time.perf_counter() - started) * 1000
        trimmed = vlm_generated[:, vlm_inputs.input_ids.shape[1]:]
        raw = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        atomic_write_json(args.output_root / "inference-vlm.json", {"schema_version": "1.0", "contract_version": "triple-coexistence-vlm-inference-v1", "prompt": VLM_PROMPT, "image_sha256": FIXTURE_SHA256, "raw_output": raw, "output_tokens": int(trimmed.shape[1]), "input_tokens": int(vlm_inputs.input_ids.shape[1]), "latency_ms": latencies["vlm_inference_ms"], "measurement": measurement(torch), "do_sample": False, "max_new_tokens": MAX_NEW_TOKENS})
    except Exception as error:
        error_document = {"schema_version": "1.0", "contract_version": "triple-model-coexistence-error-v1", "completed_phase": completed, "type": type(error).__name__, "message": str(error), "automatic_retry": False}
        atomic_write_json(args.output_root / "error.json", error_document)
    finally:
        release_started = time.perf_counter()
        del image, trimmed, vlm_generated, vlm_inputs, vlm, processor, text_result, ct2l_result
        if text_runtime is not None:
            text_runtime.close()
        if runtime is not None:
            runtime.close()
        del text_runtime, runtime
        gc.collect(); torch.cuda.empty_cache(); torch.cuda.synchronize()
        latencies["release_ms"] = (time.perf_counter() - release_started) * 1000
        atomic_write_json(args.output_root / "release.json", {"schema_version": "1.0", "contract_version": "triple-model-coexistence-release-v1", "recorded_at_utc": utc_now(), "release_order": ["qwen_vl", "qwen_text", "ct2l"], "references_deleted": True, "measurement_inside_container": measurement(torch)})

    status = "PASS" if completed == "C3" and error_document is None and all((args.output_root / name).is_file() for name in ("inference-ct2l.json", "inference-qwen-text.json", "inference-vlm.json")) else "FAILED"
    metrics = {"schema_version": "1.0", "contract_version": "triple-model-coexistence-metrics-v1", "status": status, "completed_phase": completed, "latencies_ms": {**latencies, "total_runtime_ms": (time.perf_counter() - total_started) * 1000}, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, "disk_free_bytes_after": shutil.disk_usage(args.output_root).free}
    atomic_write_json(args.output_root / "metrics.json", metrics)
    refresh_manifest(args.output_root, models)
    print(json.dumps({"status": status, "completed_phase": completed}, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
