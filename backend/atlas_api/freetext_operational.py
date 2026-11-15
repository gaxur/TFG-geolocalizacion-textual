"""Sesiones de producto FreeText-v1 para descripciones españolas arbitrarias."""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .dialogue_sessions import canonical
from .freetext_sessions import FreeTextConflict, FreeTextUnavailable, atomic, digest
from src.tfg_phase0.dialogue_freetext_v1 import validate_full_ranking


POLICY_ID = "dialogue-vpr-freetext-v1-operational"
TERMINAL = {"completed", "failed", "unknown"}
EVENT_STATUSES = {"pending", "running", "waiting_user", "completed", "failed", "unknown"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class OperationalFreeTextExpired(FreeTextConflict):
    pass


class OperationalFreeTextSessionService:
    def __init__(self, *, session_root: Path, executor=None, enabled: bool = False, ttl_seconds: int = 86400):
        self.session_root = session_root
        self.executor = executor
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.reconcile()

    def policy(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "contract_version": "atlas-dialogue-freetext-policy-public-v1",
            "policy_id": POLICY_ID,
            "version": "1.0.0",
            "status": "operational" if self.enabled and self.executor is not None else "disabled",
            "available": self.enabled and self.executor is not None,
            "enabled": self.enabled,
            "provisional": False,
            "description_length": "arbitrary",
            "input_language": "es",
            "requires_cohort": False,
            "requires_image": False,
            "maximum_questions": 3,
            "stages": ["E0", "E1", "E2", "E3"],
            "ground_truth": False,
            "vlm": False,
        }

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"freetext-operational-[0-9a-f-]{36}", session_id):
            raise FreeTextConflict("session_id FreeText operacional inválido")
        return self.session_root / session_id / "session.json"

    def _persist(self, document: dict[str, Any]) -> dict[str, Any]:
        document["updated_at"] = utcnow()
        payload = {key: value for key, value in document.items() if key != "session_sha256"}
        document["session_sha256"] = digest(payload)
        atomic(self._path(document["session_id"]), document)
        return document

    def load(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        if not path.is_file():
            raise FreeTextConflict("sesión FreeText operacional no encontrada")
        document = json.loads(path.read_text(encoding="utf-8"))
        payload = {key: value for key, value in document.items() if key != "session_sha256"}
        if digest(payload) != document.get("session_sha256") or document.get("session_id") != session_id:
            raise FreeTextConflict("sesión FreeText operacional corrupta")
        if datetime.now(timezone.utc) > datetime.fromisoformat(document["expires_at"].replace("Z", "+00:00")):
            raise OperationalFreeTextExpired("sesión FreeText operacional expirada")
        for stage in document.get("state", {}).get("stages", []):
            validate_full_ranking(stage["ranking"], set(document["state"]["candidate_universe"]))
            if digest(stage["ranking"]) != stage["ranking_sha256"]:
                raise FreeTextConflict("ranking FreeText operacional corrupto")
        return document

    def _append_event(self, document: dict[str, Any], stage: str, status: str, message: str, error: str | None = None) -> dict[str, Any]:
        if status not in EVENT_STATUSES:
            raise ValueError("estado de evento FreeText inválido")
        event = {
            "session_id": document["session_id"],
            "event_id": str(len(document["events"]) + 1),
            "stage": stage,
            "status": status,
            "timestamp": utcnow(),
            "message": message,
            "error": error,
        }
        document["events"].append(event)
        self._persist(document)
        return event

    def record_executor_event(self, session_id: str, stage: str, component: str, status: str) -> dict[str, Any]:
        document = self.load(session_id)
        mapped = status if status in EVENT_STATUSES else "unknown"
        return self._append_event(document, f"{stage}_{component}", mapped, f"{component} {stage}: {mapped}")

    def _idempotency(self, operation: str, key: str, body: Mapping[str, Any], session_id: str | None = None) -> dict[str, Any] | None:
        if not key or len(key) > 200:
            raise FreeTextConflict("Idempotency-Key obligatorio o inválido")
        body_sha = hashlib.sha256(canonical(body)).hexdigest()
        records = self.session_root / ".idempotency"
        records.mkdir(parents=True, exist_ok=True)
        record_id = hashlib.sha256(f"{operation}\0{session_id or ''}\0{key}".encode()).hexdigest()
        path = records / f"{record_id}.json"
        if path.is_file():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("body_sha256") != body_sha:
                raise FreeTextConflict("Idempotency-Key reutilizada con otro cuerpo")
            if not record.get("session_id"):
                raise FreeTextConflict("resultado previo incierto; no se reintenta automáticamente")
            return self.load(record["session_id"])
        atomic(path, {"operation": operation, "key_sha256": hashlib.sha256(key.encode()).hexdigest(), "body_sha256": body_sha, "session_id": session_id, "status": "reserved", "created_at": utcnow()})
        return None

    def _complete_idempotency(self, operation: str, key: str, body: Mapping[str, Any], session_id: str) -> None:
        records = self.session_root / ".idempotency"
        record_id = hashlib.sha256(f"{operation}\0{session_id if operation == 'answer' else ''}\0{key}".encode()).hexdigest()
        atomic(records / f"{record_id}.json", {"operation": operation, "key_sha256": hashlib.sha256(key.encode()).hexdigest(), "body_sha256": hashlib.sha256(canonical(body)).hexdigest(), "session_id": session_id, "status": "completed", "updated_at": utcnow()})

    def prepare_start(self, description: str, client_operation_id: str, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        if not self.enabled or self.executor is None:
            raise FreeTextUnavailable("política FreeText operacional deshabilitada")
        body = {"policy_id": POLICY_ID, "description_es": description, "client_operation_id": client_operation_id}
        lock = self.session_root / ".operations.lock"
        with lock.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            existing = self._idempotency("create", idempotency_key, body)
            if existing is not None:
                return existing, False
            session_id = f"freetext-operational-{uuid.uuid4()}"
            document = {
                "schema_version": "1.0",
                "contract_version": "atlas-dialogue-freetext-operational-session-v1",
                "session_id": session_id,
                "policy_id": POLICY_ID,
                "description_es": description,
                "description_sha256": hashlib.sha256(description.encode()).hexdigest(),
                "status": "pending",
                "stop_reason": None,
                "state": {"status": "pending", "turns": [], "stages": []},
                "events": [],
                "latency_ms": {"transitions": [], "total": 0.0},
                "executor_identity": dict(getattr(self.executor, "identity", {})),
                "created_at": utcnow(),
                "expires_at": datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + self.ttl_seconds, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            }
            self._persist(document)
            self._complete_idempotency("create", idempotency_key, body, session_id)
            self._append_event(document, "session", "pending", "Sesión persistida antes de ejecutar E0.")
            return self.load(session_id), True

    def run_start(self, session_id: str) -> dict[str, Any]:
        document = self.load(session_id)
        if document["status"] != "pending":
            return document
        document["status"] = "running"
        self._append_event(document, "E0", "running", "E0 iniciado.")
        started = time.perf_counter()
        try:
            self.executor.progress_callback = lambda stage, component, status: self.record_executor_event(session_id, stage, component, status)
            document["state"] = self.executor.start(query_id=session_id, description=document["description_es"], session_root=self._path(session_id).parent)
            persisted_events = self.load(session_id)["events"]
            document["events"] = persisted_events
            document["status"] = "waiting_user" if document["state"]["status"] == "awaiting_answer" else document["state"]["status"]
            document["stop_reason"] = document["state"].get("stop_reason")
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            document["latency_ms"]["transitions"].append({"stage": "E0", "elapsed_ms": elapsed})
            document["latency_ms"]["total"] = round(document["latency_ms"]["total"] + elapsed, 3)
            self._append_event(document, "E0", document["status"], "E0 persistido; espera respuesta." if document["status"] == "waiting_user" else "E0 completó la sesión.")
        except Exception as error:
            persisted_events = self.load(session_id)["events"]
            document["events"] = persisted_events
            document["status"] = "failed"
            document["stop_reason"] = "runtime_error_no_retry"
            document["failure"] = {"stage": "E0", "error_type": type(error).__name__}
            self._append_event(document, "E0", "failed", "E0 falló; no se reintenta.", type(error).__name__)
            raise
        finally:
            self.executor.progress_callback = None
        return self._persist(document)

    def start(self, description: str, client_operation_id: str, idempotency_key: str) -> dict[str, Any]:
        """Compatibilidad síncrona para herramientas/tests; HTTP usa prepare/run."""
        document, execute = self.prepare_start(description, client_operation_id, idempotency_key)
        return self.run_start(document["session_id"]) if execute else document

    def prepare_answer(self, session_id: str, answer: str, turn_index: int, question_id: str | None, question_sha256: str | None, client_operation_id: str, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        body = {"turn_index": turn_index, "question_id": question_id, "question_sha256": question_sha256, "answer_literal": answer, "human_attested": True, "external_context_used": False, "client_operation_id": client_operation_id}
        lock = self.session_root / ".operations.lock"
        with lock.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            existing = self._idempotency("answer", idempotency_key, body, session_id)
            if existing is not None:
                return existing, False
            document = self.load(session_id)
            if document["status"] != "waiting_user":
                raise FreeTextConflict("sesión FreeText operacional no espera respuesta")
            current = document["state"]["turns"][-1]
            if turn_index != current["index"] or (question_id is not None and question_id != current["question"]["intent_key"]) or (question_sha256 is not None and question_sha256 != current["question"]["sha256"]):
                raise FreeTextConflict("respuesta ligada a otra pregunta o turno")
            stage = f"E{len(document['state'].get('turns', []))}"
            document["pending_answer"] = {"literal": answer, "sha256": hashlib.sha256(answer.encode()).hexdigest(), "human_attested": True, "external_context_used": False}
            document["status"] = "running"
            self._persist(document)
            self._complete_idempotency("answer", idempotency_key, body, session_id)
            self._append_event(document, stage, "running", f"{stage} iniciado con respuesta persistida.")
            return self.load(session_id), True

    def run_answer(self, session_id: str) -> dict[str, Any]:
        document = self.load(session_id)
        if document["status"] != "running" or "pending_answer" not in document:
            return document
        answer = document["pending_answer"]["literal"]
        stage = f"E{len(document['state'].get('turns', []))}"
        started = time.perf_counter()
        try:
            self.executor.progress_callback = lambda emitted_stage, component, status: self.record_executor_event(session_id, emitted_stage, component, status)
            document["state"] = self.executor.answer(state=document["state"], answer=answer, answer_kind="free_text", session_root=self._path(session_id).parent)
            persisted_events = self.load(session_id)["events"]
            document["events"] = persisted_events
            document.pop("pending_answer", None)
            document["status"] = "waiting_user" if document["state"]["status"] == "awaiting_answer" else document["state"]["status"]
            document["stop_reason"] = document["state"].get("stop_reason")
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            document["latency_ms"]["transitions"].append({"stage": stage, "elapsed_ms": elapsed})
            document["latency_ms"]["total"] = round(document["latency_ms"]["total"] + elapsed, 3)
            self._append_event(document, stage, document["status"], f"{stage} persistido.")
        except Exception as error:
            persisted_events = self.load(session_id)["events"]
            document["events"] = persisted_events
            document["status"] = "failed"
            document["stop_reason"] = "runtime_error_no_retry"
            document["failure"] = {"stage": stage, "error_type": type(error).__name__}
            self._append_event(document, stage, "failed", f"{stage} falló; no se reintenta.", type(error).__name__)
            raise
        finally:
            self.executor.progress_callback = None
        return self._persist(document)

    def answer(self, session_id: str, answer: str, turn_index: int, question_id: str | None, question_sha256: str | None, client_operation_id: str, idempotency_key: str) -> dict[str, Any]:
        """Compatibilidad síncrona para herramientas/tests; HTTP usa prepare/run."""
        document, execute = self.prepare_answer(session_id, answer, turn_index, question_id, question_sha256, client_operation_id, idempotency_key)
        return self.run_answer(session_id) if execute else document

    def events(self, session_id: str, after: str | None = None) -> list[dict[str, Any]]:
        rows = self.load(session_id)["events"]
        if after is None:
            return rows
        try:
            ordinal = int(after)
        except ValueError as error:
            raise FreeTextConflict("Last-Event-ID inválido") from error
        return [event for event in rows if int(event["event_id"]) > ordinal]

    def reconcile(self) -> None:
        for path in self.session_root.glob("freetext-operational-*/session.json"):
            try:
                document = self.load(path.parent.name)
            except Exception:
                continue
            if document["status"] == "running":
                document["status"] = "unknown"
                document["stop_reason"] = "startup_reconciliation_no_terminal_evidence_no_retry"
                self._append_event(document, "reconciliation", "unknown", "Operación interrumpida; estado desconocido y sin reintento.", "uncertain_outcome")

    def public(self, document: Mapping[str, Any]) -> dict[str, Any]:
        state = document["state"]
        current = state.get("turns", [])[-1] if document["status"] == "waiting_user" and state.get("turns") else None
        stages = [{"stage": row["stage"], "transcript": row["transcript"], "transcript_sha256": row["transcript_sha256"], "prompt_version": row["prompt_version"], "prompt_sha256": row["prompt_sha256"], "qwen": row["qwen"], "ranking_sha256": row["ranking_sha256"], "ranking": row["ranking"]} for row in state.get("stages", [])]
        turns = [{"index": turn["index"], "question": turn["question"]["literal"], "question_sha256": turn["question"]["sha256"], "answer_literal": turn["answer"]["literal"] if turn.get("answer") else None, "answer_sha256": turn["answer"]["sha256"] if turn.get("answer") else None} for turn in state.get("turns", [])]
        snapshots = [{"stage": row["stage"], "ranking_sha256": row["ranking_sha256"], "gallery_id": row["ranking"].get("gallery_id"), "candidate_count": len(row["ranking"]["results"]), "results": row["ranking"]["results"][:10]} for row in state.get("stages", [])]
        return {
            "schema_version": "1.0",
            "contract_version": "atlas-dialogue-freetext-operational-session-public-v1",
            "session_id": document["session_id"],
            "policy_id": POLICY_ID,
            "description_es": document["description_es"],
            "description_sha256": document["description_sha256"],
            "status": document["status"],
            "stop_reason": document.get("stop_reason"),
            "experimental_query_id": document["session_id"],
            "turns": turns,
            "transcript": turns,
            "current_question": None if current is None else {"turn_index": current["index"], "question_id": current["question"]["intent_key"], "question": current["question"]["literal"], "question_sha256": current["question"]["sha256"]},
            "stages": stages,
            "stage_snapshots": snapshots,
            "final_stage": state.get("final_stage"),
            "latency_ms": document["latency_ms"],
            "executor_identity": document["executor_identity"],
            "event_count": len(document["events"]),
            "session_sha256": document["session_sha256"],
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
            "updated_at_utc": document["updated_at"],
            "expires_at": document["expires_at"],
        }
