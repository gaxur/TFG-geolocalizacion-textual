"""Ledger inmutable para intentos caros y recuperación sin repetir inferencias."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .append_jsonl_checkpoint import CheckpointError, canonical_bytes, finalize_json_atomic


class AttemptLedgerError(CheckpointError):
    pass


@dataclass(frozen=True)
class AttemptPaths:
    root: Path
    attempt: Path
    raw: Path
    result: Path
    failure: Path


def attempt_paths(root: Path, *, kind: str, target_id: str, ordinal: int = 1) -> AttemptPaths:
    safe_target = target_id.replace("/", "_")
    directory = root / "attempts" / f"{kind}-{safe_target}" / f"attempt-{ordinal:03d}"
    return AttemptPaths(directory, directory / "attempt.json", directory / "raw.json", directory / "result.json", directory / "failure.json")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class ImmutableAttemptLedger:
    def __init__(self, root: Path, *, plan_id: str, maximum_attempts: int):
        self.root = root
        self.plan_id = plan_id
        self.maximum_attempts = maximum_attempts

    def paths(self, *, kind: str, target_id: str, ordinal: int = 1) -> AttemptPaths:
        return attempt_paths(self.root, kind=kind, target_id=target_id, ordinal=ordinal)

    def _attempt_count(self) -> int:
        return sum(1 for _ in (self.root / "attempts").glob("*/attempt-*/attempt.json")) if (self.root / "attempts").exists() else 0

    def summary(self) -> dict[str, int]:
        attempts = list((self.root / "attempts").glob("*/attempt-*/attempt.json")) if (self.root / "attempts").exists() else []
        roots = [path.parent for path in attempts]
        return {
            "attempted": len(attempts),
            "completed": sum((root / "result.json").exists() for root in roots),
            "failed": sum((root / "failure.json").exists() for root in roots),
            "raw_preserved": sum((root / "raw.json").exists() for root in roots),
            "unterminated": sum(not (root / "result.json").exists() and not (root / "failure.json").exists() for root in roots),
        }

    @staticmethod
    def _assert_terminal_coherence(paths: AttemptPaths) -> None:
        if paths.result.exists() and paths.failure.exists():
            raise AttemptLedgerError("intento con estados terminales contradictorios")

    def begin(self, *, kind: str, target_id: str, cache_entry_id: str, started_at_utc: str, ordinal: int = 1) -> AttemptPaths:
        paths = self.paths(kind=kind, target_id=target_id, ordinal=ordinal)
        self._assert_terminal_coherence(paths)
        document = {
            "schema_version": "1.0",
            "contract_version": "i20-assisted-generation-attempt-v2",
            "plan_id": self.plan_id,
            "attempt_id": f"{kind}:{target_id}:{ordinal}",
            "attempt_ordinal": ordinal,
            "task_kind": kind,
            "target_id": target_id,
            "cache_entry_id": cache_entry_id,
            "started_at_utc": started_at_utc,
        }
        if not paths.attempt.exists() and self._attempt_count() >= self.maximum_attempts:
            raise AttemptLedgerError("presupuesto de intentos agotado")
        finalize_json_atomic(output_path=paths.attempt, document=document)
        return paths

    def preserve_raw(self, paths: AttemptPaths, *, raw_output: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        self._assert_terminal_coherence(paths)
        document = {
            "schema_version": "1.0",
            "contract_version": "i20-assisted-generation-raw-v1",
            "plan_id": self.plan_id,
            "attempt_id": load_json(paths.attempt)["attempt_id"],
            "raw_output": raw_output,
            "raw_output_sha256": hashlib.sha256(raw_output.encode()).hexdigest(),
            "generation": dict(metadata),
        }
        finalize_json_atomic(output_path=paths.raw, document=document)
        return document

    def record_result(self, paths: AttemptPaths, *, record: Mapping[str, Any], finished_at_utc: str) -> dict[str, Any]:
        self._assert_terminal_coherence(paths)
        if paths.failure.exists():
            raise AttemptLedgerError("un fallo terminal no puede convertirse en resultado")
        raw = load_json(paths.raw)
        document = {
            "schema_version": "1.0",
            "contract_version": "i20-assisted-generation-result-v1",
            "plan_id": self.plan_id,
            "attempt_id": load_json(paths.attempt)["attempt_id"],
            "finished_at_utc": finished_at_utc,
            "raw_output_sha256": raw["raw_output_sha256"],
            "record": dict(record),
        }
        finalize_json_atomic(output_path=paths.result, document=document)
        return document

    def record_failure(self, paths: AttemptPaths, *, stage: str, error: BaseException, finished_at_utc: str) -> dict[str, Any]:
        self._assert_terminal_coherence(paths)
        if paths.result.exists():
            raise AttemptLedgerError("un resultado terminal no puede convertirse en fallo")
        document = {
            "schema_version": "1.0",
            "contract_version": "i20-assisted-generation-failure-v1",
            "plan_id": self.plan_id,
            "attempt_id": load_json(paths.attempt)["attempt_id"],
            "finished_at_utc": finished_at_utc,
            "stage": stage,
            "exception_type": type(error).__name__,
            "exception_message": str(error),
            "raw_output_sha256": load_json(paths.raw)["raw_output_sha256"] if paths.raw.exists() else None,
        }
        finalize_json_atomic(output_path=paths.failure, document=document)
        return document

    def recover_result(self, paths: AttemptPaths) -> Mapping[str, Any] | None:
        self._assert_terminal_coherence(paths)
        return load_json(paths.result)["record"] if paths.result.exists() else None

    def state(self, paths: AttemptPaths) -> str:
        self._assert_terminal_coherence(paths)
        if paths.result.exists(): return "result"
        if paths.failure.exists(): return "failure"
        if paths.raw.exists(): return "raw"
        if paths.attempt.exists(): return "attempt"
        return "missing"


def execute_immutable_attempt(
    *,
    ledger: ImmutableAttemptLedger,
    kind: str,
    target_id: str,
    cache_entry_id: str,
    now,
    generate_raw,
    parse_and_build,
) -> Mapping[str, Any]:
    paths = ledger.paths(kind=kind, target_id=target_id)
    state = ledger.state(paths)
    if state == "result":
        return ledger.recover_result(paths)  # type: ignore[return-value]
    if state == "failure":
        raise AttemptLedgerError("el intento terminó en fallo; retry no autorizado")
    if state == "attempt":
        raise AttemptLedgerError("intento interrumpido antes de preservar salida; retry no autorizado")
    if state == "missing":
        paths = ledger.begin(kind=kind, target_id=target_id, cache_entry_id=cache_entry_id, started_at_utc=now())
        try:
            raw_output, metadata = generate_raw()
            ledger.preserve_raw(paths, raw_output=raw_output, metadata=metadata)
        except Exception as error:
            ledger.record_failure(paths, stage="generation_or_raw_persistence", error=error, finished_at_utc=now())
            raise
    raw_document = load_json(paths.raw)
    try:
        record = parse_and_build(raw_document["raw_output"], raw_document["generation"])
        ledger.record_result(paths, record=record, finished_at_utc=now())
        return record
    except Exception as error:
        ledger.record_failure(paths, stage="parse_validation_or_build", error=error, finished_at_utc=now())
        raise
