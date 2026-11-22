"""Reusable, fail-closed admission for local FreeText application sessions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Mapping

from .dialogue_sessions import canonical, sha256_file
from .freetext_authorization import executor_identity
from .freetext_operational import OperationalFreeTextExpired, OperationalFreeTextSessionService, utcnow
from .freetext_sessions import FreeTextConflict, FreeTextUnavailable


POLICY_ID = "dialogue-vpr-freetext-v1-application"
PROFILE_CONTRACT = "atlas-dialogue-freetext-application-profile-v1"
PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
OPEN_STATUSES = ("pending", "running", "waiting_user")
QUOTAS = {
    "maximum_qwen_loads": 4,
    "maximum_qwen_calls": 4,
    "maximum_ct2l_loads": 4,
    "maximum_ct2l_calls": 4,
    "maximum_questions": 3,
    "automatic_retries": 0,
}
CONSTRAINTS = {
    "access_mode": "loopback",
    "network_permitted": False,
    "ground_truth_permitted": False,
    "references_permitted": False,
    "vlm_permitted": False,
    "h38_h61_permitted": False,
}


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FreeTextUnavailable(f"perfil application: {field} inválido")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FreeTextUnavailable(f"perfil application: {field} inválido") from error
    if result.tzinfo is None:
        raise FreeTextUnavailable(f"perfil application: {field} sin zona horaria")
    return result.astimezone(timezone.utc)


class ApplicationFreeTextSessionService(OperationalFreeTextSessionService):
    """Executes E0-E3 while SQLite atomically admits reusable sessions."""

    def __init__(self, *, session_root: Path, state_root: Path, profile_path: Path, executor=None, enabled: bool = False, policy_identity: Mapping[str, str]):
        self.state_root = state_root
        self.profile_path = profile_path
        self.policy_identity = dict(policy_identity)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.state_root / "freetext-application.sqlite3"
        super().__init__(session_root=session_root, executor=executor, enabled=enabled)
        self._initialize_ledger()
        self.reconcile()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.ledger_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize_ledger(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    profile_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    operation TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    key_sha256 TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    PRIMARY KEY (operation, scope, key_sha256)
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    session_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    qwen_loads INTEGER NOT NULL CHECK(qwen_loads = 1),
                    qwen_calls INTEGER NOT NULL CHECK(qwen_calls = 1),
                    ct2l_loads INTEGER NOT NULL CHECK(ct2l_loads = 1),
                    ct2l_calls INTEGER NOT NULL CHECK(ct2l_calls = 1),
                    questions INTEGER NOT NULL CHECK(questions IN (0, 1)),
                    reserved_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, stage),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );
                """
            )

    def _profile(self) -> dict[str, Any]:
        if not self.enabled or self.executor is None:
            raise FreeTextUnavailable("política FreeText application deshabilitada")
        try:
            document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FreeTextUnavailable("perfil FreeText application ausente o ilegible") from error
        identity, identity_sha256 = executor_identity(self.executor)
        required = {
            "schema_version": "1.0",
            "contract_version": PROFILE_CONTRACT,
            "status": "APPROVED",
            "approved": True,
            **self.policy_identity,
            "executor_identity": identity,
            "executor_identity_sha256": identity_sha256,
            "per_session_quotas": QUOTAS,
            "constraints": CONSTRAINTS,
        }
        expected = set(required) | {"profile_id", "profile_version", "approved_at", "valid_from", "expires_at", "max_sessions_total", "max_open_sessions", "global_quotas"}
        if set(document) != expected or any(document.get(key) != value for key, value in required.items()):
            raise FreeTextUnavailable("perfil FreeText application pendiente, no aprobado o incompatible")
        if not isinstance(document.get("profile_id"), str) or not PROFILE_ID.fullmatch(document["profile_id"]):
            raise FreeTextUnavailable("profile_id FreeText application inválido")
        if not isinstance(document.get("profile_version"), str) or not document["profile_version"]:
            raise FreeTextUnavailable("profile_version FreeText application inválido")
        if document.get("max_sessions_total") is not None or document.get("max_open_sessions") != 1:
            raise FreeTextUnavailable("límites de sesiones FreeText application incompatibles")
        expected_global = {"maximum_qwen_units": None, "maximum_ct2l_units": None, "maximum_questions": None}
        if document.get("global_quotas") != expected_global:
            raise FreeTextUnavailable("cuotas globales FreeText application incompatibles")
        approved = _instant(document["approved_at"], "approved_at")
        valid_from = _instant(document["valid_from"], "valid_from")
        expires = _instant(document["expires_at"], "expires_at")
        now = datetime.now(timezone.utc)
        if approved > now or valid_from > now or expires <= now or expires <= valid_from or expires - valid_from > timedelta(days=90):
            raise FreeTextUnavailable("perfil FreeText application fuera de su ventana temporal")
        return {"document": document, "sha256": sha256_file(self.profile_path), "identity": identity, "identity_sha256": identity_sha256}

    def policy(self) -> dict[str, Any]:
        try:
            profile = self._profile()
            available = True
            metadata = {
                "profile_id": profile["document"]["profile_id"],
                "profile_version": profile["document"]["profile_version"],
                "expires_at": profile["document"]["expires_at"],
                "max_sessions_total": profile["document"]["max_sessions_total"],
                "max_open_sessions": profile["document"]["max_open_sessions"],
                "access_mode": "loopback",
                "per_session_quotas": dict(QUOTAS),
                "constraints": dict(CONSTRAINTS),
            }
        except FreeTextUnavailable:
            available = False
            metadata = {"access_mode": "loopback"}
        if available:
            with self._connect() as connection:
                admitted = connection.execute("SELECT COUNT(*) FROM sessions WHERE profile_id=?", (profile["document"]["profile_id"],)).fetchone()[0]
                opened = connection.execute("SELECT COUNT(*) FROM sessions WHERE profile_id=? AND status IN (?,?,?)", (profile["document"]["profile_id"], *OPEN_STATUSES)).fetchone()[0]
            total = profile["document"]["max_sessions_total"]
            metadata.update(sessions_admitted=admitted, sessions_remaining=None if total is None else max(0, total-admitted), open_sessions=opened)
        return {
            "schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-policy-public-v1",
            "policy_id": POLICY_ID, "version": "1.0.0", "status": "application" if available else "disabled",
            "available": available, "enabled": self.enabled, "provisional": False, "description_length": "arbitrary",
            "input_language": "es", "requires_cohort": False, "requires_image": False, "maximum_questions": 3,
            "stages": ["E0", "E1", "E2", "E3"], "ground_truth": False, "vlm": False, "profile": metadata,
        }

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"freetext-application-[0-9a-f-]{36}", session_id):
            raise FreeTextConflict("session_id FreeText application inválido")
        return self.session_root / session_id / "session.json"

    def _authorized(self, document: Mapping[str, Any]) -> dict[str, Any]:
        profile = self._profile()
        if document.get("profile_binding") != {
            "profile_id": profile["document"]["profile_id"],
            "profile_sha256": profile["sha256"],
            "executor_identity_sha256": profile["identity_sha256"],
        } or document.get("executor_identity") != profile["identity"]:
            raise FreeTextUnavailable("perfil o identidad actual FreeText application divergente")
        return profile

    def load(self, session_id: str) -> dict[str, Any]:
        document = super().load(session_id)
        self._authorized(document)
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is not None and row["status"] == "unknown" and document["status"] != "unknown":
            document["status"] = "unknown"
            document["stop_reason"] = "durable_ledger_uncertain_outcome_no_retry"
            self._append_event(document, "reconciliation", "unknown", "Resultado incierto conservado sin reintento.", "uncertain_outcome")
        return document

    @staticmethod
    def _body_sha(body: Mapping[str, Any]) -> str:
        return hashlib.sha256(canonical(body)).hexdigest()

    def _lookup_idempotency(self, connection: sqlite3.Connection, operation: str, scope: str, key: str, body: Mapping[str, Any]) -> str | None:
        row = connection.execute("SELECT body_sha256, session_id FROM idempotency WHERE operation=? AND scope=? AND key_sha256=?", (operation, scope, hashlib.sha256(key.encode()).hexdigest())).fetchone()
        if row is None:
            return None
        if row["body_sha256"] != self._body_sha(body):
            raise FreeTextConflict("Idempotency-Key reutilizada con otro cuerpo")
        return row["session_id"]

    def session_for_create_operation(self, client_operation_id: str) -> dict[str, Any]:
        if not client_operation_id or len(client_operation_id) > 200:
            raise FreeTextConflict("client_operation_id application inválido")
        with self._connect() as connection:
            row = connection.execute("SELECT session_id FROM idempotency WHERE operation='create' AND scope='' AND key_sha256=?", (hashlib.sha256(client_operation_id.encode()).hexdigest(),)).fetchone()
        if row is None:
            raise FreeTextConflict("operación de creación application no encontrada")
        return self.load(row["session_id"])

    def prepare_start(self, description: str, client_operation_id: str, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        if not isinstance(description, str) or not 3 <= len(description) <= 2400:
            raise FreeTextConflict("description_es debe contener entre 3 y 2400 caracteres")
        if idempotency_key != client_operation_id or not idempotency_key or len(idempotency_key) > 200:
            raise FreeTextConflict("Idempotency-Key y client_operation_id deben coincidir")
        profile_lock = self.state_root / "freetext-application-profile.lock"
        with profile_lock.open("a+b") as lock:
         fcntl.flock(lock,fcntl.LOCK_SH)
         profile = self._profile()
         body = {"policy_id": POLICY_ID, "description_es": description, "client_operation_id": client_operation_id}
         with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._lookup_idempotency(connection, "create", "", idempotency_key, body)
            if existing is not None:
                connection.commit()
                return self.load(existing), False
            limits = profile["document"]
            opened = connection.execute("SELECT COUNT(*) FROM sessions WHERE profile_id=? AND status IN (?,?,?)", (limits["profile_id"], *OPEN_STATUSES)).fetchone()[0]
            if opened >= limits["max_open_sessions"]:
                raise FreeTextUnavailable("límite de sesiones abiertas FreeText application agotado")
            session_id = f"freetext-application-{uuid.uuid4()}"
            created_at = utcnow()
            connection.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (session_id, limits["profile_id"], profile["sha256"], "pending", created_at))
            connection.execute("INSERT INTO idempotency VALUES (?,?,?,?,?)", ("create", "", hashlib.sha256(idempotency_key.encode()).hexdigest(), self._body_sha(body), session_id))
            document = {
                "schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-application-session-v1",
                "session_id": session_id, "policy_id": POLICY_ID, "description_es": description,
                "description_sha256": hashlib.sha256(description.encode()).hexdigest(), "status": "pending", "stop_reason": None,
                "state": {"status": "pending", "turns": [], "stages": []}, "events": [],
                "latency_ms": {"transitions": [], "total": 0.0}, "executor_identity": profile["identity"],
                "profile_binding": {"profile_id": limits["profile_id"], "profile_sha256": profile["sha256"], "executor_identity_sha256": profile["identity_sha256"]},
                "budget_reservations": {"qwen_loads": 0, "qwen_calls": 0, "ct2l_loads": 0, "ct2l_calls": 0, "questions": 0, "retries": 0, "stages": []},
                "created_at": created_at, "expires_at": limits["expires_at"],
            }
            connection.commit()
        try:
            self._persist(document)
        except Exception:
            self._set_ledger_status(session_id, "unknown")
            raise
        self._append_event(document, "session", "pending", "Sesión application admitida y persistida antes de E0.")
        return self.load(session_id), True

    def _reserve_stage(self, document: dict[str, Any], stage: str) -> None:
        question = 0 if stage == "E3" else 1
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("INSERT INTO reservations VALUES (?,?,?,?,?,?,?,?)", (document["session_id"], stage, 1, 1, 1, 1, question, utcnow()))
            except sqlite3.IntegrityError as error:
                raise FreeTextConflict("etapa FreeText ya reservada; no se reintenta") from error
            rows = connection.execute("SELECT COUNT(*) AS stages, COALESCE(SUM(questions),0) AS questions FROM reservations WHERE session_id=?", (document["session_id"],)).fetchone()
            if rows["stages"] > 4 or rows["questions"] > 3:
                raise FreeTextConflict("presupuesto de inferencia FreeText agotado")
            connection.commit()
        budgets = document["budget_reservations"]
        for key in ("qwen_loads", "qwen_calls", "ct2l_loads", "ct2l_calls"):
            budgets[key] += 1
        budgets["questions"] += question
        budgets["stages"].append(stage)
        self._persist(document)

    def _set_ledger_status(self, session_id: str, status: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE sessions SET status=? WHERE session_id=?", (status, session_id))
            connection.commit()

    def _persist(self, document: dict[str, Any]) -> dict[str, Any]:
        result = super()._persist(document)
        if self.ledger_path.exists():
            self._set_ledger_status(document["session_id"], document["status"])
        return result

    def prepare_answer(self, session_id: str, answer: str, turn_index: int, question_id: str | None, question_sha256: str | None, client_operation_id: str, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        lock_path = self.session_root / session_id / ".transition.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._prepare_answer_locked(session_id, answer, turn_index, question_id, question_sha256, client_operation_id, idempotency_key)

    def _prepare_answer_locked(self, session_id: str, answer: str, turn_index: int, question_id: str | None, question_sha256: str | None, client_operation_id: str, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        if idempotency_key != client_operation_id or not idempotency_key or len(idempotency_key) > 200:
            raise FreeTextConflict("Idempotency-Key y client_operation_id deben coincidir")
        body = {"turn_index": turn_index, "question_id": question_id, "question_sha256": question_sha256, "answer_literal": answer, "human_attested": True, "external_context_used": False, "client_operation_id": client_operation_id}
        document = self.load(session_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._lookup_idempotency(connection, "answer", session_id, idempotency_key, body)
            if existing is not None:
                connection.commit()
                return self.load(existing), False
            if document["status"] != "waiting_user":
                raise FreeTextConflict("sesión FreeText application no espera respuesta")
            current = document["state"]["turns"][-1]
            if turn_index != current["index"] or (question_id is not None and question_id != current["question"]["intent_key"]) or (question_sha256 is not None and question_sha256 != current["question"]["sha256"]):
                raise FreeTextConflict("respuesta ligada a otra pregunta o turno")
            stage = f"E{len(document['state']['turns'])}"
            question_count = 0 if stage == "E3" else 1
            try:
                connection.execute("INSERT INTO reservations VALUES (?,?,?,?,?,?,?,?)", (session_id, stage, 1, 1, 1, 1, question_count, utcnow()))
            except sqlite3.IntegrityError as error:
                raise FreeTextConflict("etapa FreeText ya reservada; no se reintenta") from error
            rows = connection.execute("SELECT COUNT(*) AS stages, COALESCE(SUM(questions),0) AS questions FROM reservations WHERE session_id=?", (session_id,)).fetchone()
            if rows["stages"] > 4 or rows["questions"] > 3:
                raise FreeTextConflict("presupuesto de inferencia FreeText agotado")
            connection.execute("INSERT INTO idempotency VALUES (?,?,?,?,?)", ("answer", session_id, hashlib.sha256(idempotency_key.encode()).hexdigest(), self._body_sha(body), session_id))
            connection.execute("UPDATE sessions SET status='running' WHERE session_id=?", (session_id,))
            connection.commit()
            document["pending_answer"] = {"literal": answer, "sha256": hashlib.sha256(answer.encode()).hexdigest(), "human_attested": True, "external_context_used": False}
            document["status"] = "running"
            budgets = document["budget_reservations"]
            for key in ("qwen_loads", "qwen_calls", "ct2l_loads", "ct2l_calls"):
                budgets[key] += 1
            budgets["questions"] += question_count
            budgets["stages"].append(stage)
            try:
                self._persist(document)
            except Exception:
                self._set_ledger_status(session_id, "unknown")
                raise
        self._append_event(document, stage, "running", f"{stage} iniciado con respuesta persistida.")
        return self.load(session_id), True

    def reconcile(self) -> None:
        if not hasattr(self, "ledger_path") or not self.ledger_path.exists():
            return
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for row in connection.execute("SELECT session_id FROM sessions WHERE status IN (?,?,?)", OPEN_STATUSES).fetchall():
                if not self._path(row["session_id"]).is_file():
                    connection.execute("UPDATE sessions SET status='unknown' WHERE session_id=?", (row["session_id"],))
            connection.commit()
        for path in self.session_root.glob("freetext-application-*/session.json"):
            try:
                document = super().load(path.parent.name)
            except Exception:
                continue
            with self._connect() as connection:
                row=connection.execute("SELECT status FROM sessions WHERE session_id=?",(document["session_id"],)).fetchone()
            ledger_status=row["status"] if row else None
            if ledger_status == "unknown" or document["status"] in {"pending", "running"} or ledger_status in {"pending", "running"} and ledger_status != document["status"]:
                if document["status"] != "unknown":
                    document["status"] = "unknown"
                    document["stop_reason"] = "startup_reconciliation_no_terminal_evidence_no_retry"
                    self._append_event(document, "reconciliation", "unknown", "Operación interrumpida; estado desconocido y sin reintento.", "uncertain_outcome")
            else:
                self._set_ledger_status(document["session_id"], document["status"])

    def public(self, document: Mapping[str, Any]) -> dict[str, Any]:
        result = super().public(document)
        result["contract_version"] = "atlas-dialogue-freetext-application-session-public-v1"
        result["policy_id"] = POLICY_ID
        result["maximum_questions"] = QUOTAS["maximum_questions"]
        return result
