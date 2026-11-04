#!/usr/bin/env python3
"""Ejecuta hasta tres sesiones técnicas reutilizando una sola carga de modelos."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_interactive_dialogue import build_real_components, load_policy
from src.tfg_phase0.interactive_dialogue import OneTurnDialogueOrchestrator, write_session


SESSIONS = (
    ("session-02", "Estoy cerca de una plaza y observo varios edificios alrededor", "No"),
    ("session-03", "Estoy en una zona con calles que se cruzan y edificios a ambos lados", "No puedo comprobarlo"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def cuda_memory() -> dict:
    import torch

    return {
        "allocated_bytes": int(torch.cuda.memory_allocated()),
        "reserved_bytes": int(torch.cuda.memory_reserved()),
        "max_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "max_reserved_bytes": int(torch.cuda.max_memory_reserved()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=ROOT / "config/interactive_dialogue_mvp.json")
    parser.add_argument("--ct2l-config", type=Path, default=ROOT / "config/madrid_f46_retriever.json")
    parser.add_argument("--f3-bundle", type=Path, required=True)
    parser.add_argument("--cvg-utils-sha256", required=True)
    parser.add_argument("--clip-weights", type=Path, required=True)
    parser.add_argument("--qwen-model-dir", type=Path, required=True)
    args = parser.parse_args()

    gallery_id, config = load_policy(args.policy)
    before = cuda_memory()
    started = time.perf_counter()
    retriever, evidence, text_adapter, resources = build_real_components(args, gallery_id)
    loaded = time.perf_counter()
    after_load = cuda_memory()
    records = []
    try:
        for label, description, answer in SESSIONS:
            session_started = time.perf_counter()
            orchestrator = OneTurnDialogueOrchestrator(retriever=retriever, evidence=evidence, config=config, text_adapter=text_adapter)
            session = orchestrator.start(session_label=f"real-smoke-{label}", description=description)
            if session["status"] == "awaiting_answer":
                session = orchestrator.answer(session, answer)
            session_dir = args.output_root / label
            session_path, events_path = write_session(session, session_dir)
            records.append({
                "label": label,
                "session_id": session["session_id"],
                "description": description,
                "technical_answer": answer,
                "question": session["selected_question"]["question"] if session["selected_question"] else None,
                "question_source": session["selected_question"]["source"] if session["selected_question"] else None,
                "question_fallback": session["selected_question"]["fallback_reason"] if session["selected_question"] else None,
                "stop_reason": session["stop_reason"],
                "updated_variants": [row["variant"] for row in session["updated_rankings"]],
                "duration_ms": (time.perf_counter() - session_started) * 1000,
                "session_path": str(session_path),
                "events_path": str(events_path),
            })
    finally:
        for value in reversed(resources):
            if value is not None:
                value.close()
    finished = time.perf_counter()
    report = {
        "schema_version": "1.0",
        "contract_version": "interactive-dialogue-real-smoke-report-v1",
        "created_at_utc": utc_now(),
        "protocol": {
            "technical_smoke_only": True,
            "ground_truth_used": False,
            "sealed_sets_used": False,
            "vlm_used": False,
            "network_used": False,
            "model_retries": False,
            "shared_model_load": True,
        },
        "resources": {
            "cuda_before": before,
            "cuda_after_load": after_load,
            "cuda_after_close": cuda_memory(),
            "load_duration_ms": (loaded - started) * 1000,
            "sessions_duration_ms": (finished - loaded) * 1000,
            "total_duration_ms": (finished - started) * 1000,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        },
        "calls": {
            "ct2l": list(retriever.metadata["calls"]),
            "qwen": list(text_adapter.metadata["calls"]),
        },
        "sessions": records,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "smoke-report.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sessions": records, "resources": report["resources"], "call_counts": {key: len(value) for key, value in report["calls"].items()}}, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
