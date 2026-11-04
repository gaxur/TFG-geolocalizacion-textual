#!/usr/bin/env python3
"""Ejecuta una única sesión multivuelta real con protocolo técnico prefijado."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_interactive_dialogue import load_multiturn_policy
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, load_runtime_config
from src.tfg_phase0.f5_text_transform import QwenTransformersAdapter
from src.tfg_phase0.interactive_dialogue import F3EvidenceIndex, QWEN_MODEL_ID, QWEN_REVISION, QwenDialogueAdapter, ResidentCT2LAdapter
from src.tfg_phase0.interactive_dialogue_multiturn import MultiTurnDialogueOrchestrator, validate_multiturn_session, write_multiturn_session


DESCRIPTION = "Estoy en una calle urbana con varios edificios y comercios"
ANSWERS = ("Sí", "No", "No puedo comprobarlo")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cuda_memory(torch) -> dict:
    if not torch.cuda.is_available():
        return {"allocated_bytes": None, "reserved_bytes": None, "max_allocated_bytes": None, "max_reserved_bytes": None}
    return {
        "allocated_bytes": int(torch.cuda.memory_allocated()),
        "reserved_bytes": int(torch.cuda.memory_reserved()),
        "max_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "max_reserved_bytes": int(torch.cuda.max_memory_reserved()),
    }


def system_memory() -> dict:
    values = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    return {
        "ram_available_bytes": values.get("MemAvailable"),
        "swap_total_bytes": values.get("SwapTotal"),
        "swap_free_bytes": values.get("SwapFree"),
        "swap_used_bytes": values.get("SwapTotal", 0) - values.get("SwapFree", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=ROOT / "config/interactive_dialogue_multiturn.json")
    parser.add_argument("--ct2l-config", type=Path, default=ROOT / "config/madrid_f46_retriever.json")
    parser.add_argument("--f3-bundle", type=Path, required=True)
    parser.add_argument("--cvg-utils-sha256", required=True)
    parser.add_argument("--clip-weights", type=Path, required=True)
    parser.add_argument("--qwen-model-dir", type=Path, required=True)
    args = parser.parse_args()

    import torch

    if (args.output_root / "session").exists() or (args.output_root / "smoke-report.json").exists():
        raise ValueError("el directorio de smoke ya contiene una ejecución")
    gallery_id, config = load_multiturn_policy(args.policy)
    if gallery_id != "madrid-50m" or config.max_questions != 3:
        raise ValueError("configuración del smoke incompatible")

    report = {
        "schema_version": "1.0",
        "contract_version": "interactive-dialogue-multiturn-real-smoke-report-v1",
        "created_at_utc": utc_now(),
        "status": "RUNNING",
        "protocol": {"description": DESCRIPTION, "answers": list(ANSWERS), "answer_rule": "ordinal_valid_question", "ground_truth_used": False, "sealed_sets_used": False, "vlm_used": False, "network_used": False, "model_retries": False},
        "loads_ms": {},
        "resources": {"before_load": {"cuda": cuda_memory(torch), "system": system_memory()}},
        "error": None,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    runtime = qwen_runtime = None
    try:
        model, galleries = load_runtime_config(args.ct2l_config, project_root=ROOT, cvg_utils_sha256=args.cvg_utils_sha256, clip_weights_path=args.clip_weights)
        selected = [value for value in galleries if value.gallery_id == gallery_id]
        if len(selected) != 1:
            raise ValueError("galería madrid-50m no configurada de forma única")

        load_started = time.perf_counter()
        runtime = CrossText2LocRetriever.load(model_config=model, gallery_configs=selected, region_config=ROOT / "config/madrid.yaml")
        report["loads_ms"]["ct2l"] = (time.perf_counter() - load_started) * 1000
        report["resources"]["after_ct2l_load"] = {"cuda": cuda_memory(torch), "system": system_memory()}
        retriever = ResidentCT2LAdapter(runtime, gallery_id)

        load_started = time.perf_counter()
        evidence = F3EvidenceIndex.load_bundle(args.f3_bundle)
        report["loads_ms"]["f3"] = (time.perf_counter() - load_started) * 1000
        runtime_catalog = runtime._galleries[gallery_id].catalog
        if evidence.catalog_manifest_id != runtime_catalog.manifest_id or evidence.catalog_manifest_sha256 != runtime_catalog.sha256:
            raise ValueError("F3 no corresponde al catálogo CT2L")

        load_started = time.perf_counter()
        qwen_runtime = QwenTransformersAdapter(args.qwen_model_dir, model_id=QWEN_MODEL_ID, revision=QWEN_REVISION)
        text_adapter = QwenDialogueAdapter(qwen_runtime)
        report["loads_ms"]["qwen"] = (time.perf_counter() - load_started) * 1000
        report["resources"]["after_qwen_load"] = {"cuda": cuda_memory(torch), "system": system_memory()}

        orchestrator = MultiTurnDialogueOrchestrator(retriever=retriever, evidence=evidence, config=config, text_adapter=text_adapter)
        session_started = time.perf_counter()
        session = orchestrator.start(session_label="multiturn-real-smoke-v1", description=DESCRIPTION)
        answer_index = 0
        while session["status"] == "awaiting_answer":
            if answer_index >= len(ANSWERS):
                raise RuntimeError("la política solicitó más respuestas que el presupuesto")
            session = orchestrator.answer(session, ANSWERS[answer_index])
            answer_index += 1
        validate_multiturn_session(session)
        session_path, events_path = write_multiturn_session(session, args.output_root / "session")
        report.update({
            "status": "PASS",
            "session_duration_ms": (time.perf_counter() - session_started) * 1000,
            "questions_asked": session["questions_asked"],
            "answers_used": list(ANSWERS[:answer_index]),
            "stop_reason": session["stop_reason"],
            "calls": {"ct2l": list(retriever.metadata["calls"]), "qwen": list(text_adapter.metadata["calls"]), "vlm": 0},
            "artifacts": {"session": str(session_path.relative_to(args.output_root)), "session_sha256": sha256_file(session_path), "events": str(events_path.relative_to(args.output_root)), "events_sha256": sha256_file(events_path)},
            "resources_at_completion": {"cuda": cuda_memory(torch), "system": system_memory(), "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
        })
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        report["resources_at_failure"] = {"cuda": cuda_memory(torch), "system": system_memory(), "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
        raise
    finally:
        if qwen_runtime is not None:
            qwen_runtime.close()
        if runtime is not None:
            runtime.close()
        report["resources_after_close"] = {"cuda": cuda_memory(torch), "system": system_memory()}
        report["total_duration_ms"] = (time.perf_counter() - started) * 1000
        (args.output_root / "smoke-report.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"status": report["status"], "questions_asked": report.get("questions_asked"), "stop_reason": report.get("stop_reason"), "call_counts": {key: len(value) if isinstance(value, list) else value for key, value in report.get("calls", {}).items()}}, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
