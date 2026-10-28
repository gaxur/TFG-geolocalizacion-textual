"""Checkpoint JSONL append-only, reanudación estricta y publicación atómica."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence


class CheckpointError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class PlannedJob:
    key: tuple[str | None, str, str, str]
    fingerprint: Mapping[str, Any]
    payload: Any
    requires_execution: bool


@dataclass(frozen=True)
class Progress:
    total: int
    recovered: int
    completed: int
    executed_this_session: int
    remaining: int
    pending_executions: int
    elapsed_seconds: float
    mean_execution_seconds: float | None
    eta_seconds: float | None
    last_key: tuple[str | None, str, str, str] | None


def ordered_plan_sha256(jobs: Sequence[PlannedJob]) -> str:
    return hashlib.sha256(canonical_bytes([job.fingerprint for job in jobs])).hexdigest()


def _key_object(key):
    return {"query_id": key[0], "candidate_id": key[1], "image_id": key[2], "claim_id": key[3]}


def _validate_jobs(jobs):
    keys = [job.key for job in jobs]
    if len(keys) != len(set(keys)):
        raise CheckpointError("jobs duplicados")


def _read_checkpoint(path: Path, header: Mapping[str, Any], jobs: Sequence[PlannedJob]) -> list[Mapping[str, Any]]:
    expected_header = canonical_bytes(header)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(expected_header + b"\n")
            stream.flush();os.fsync(stream.fileno())
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        cut = raw.rfind(b"\n")
        if cut < 0:
            raise CheckpointError("checkpoint sin cabecera completa")
        raw = raw[:cut + 1]
        with path.open("wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
    lines = raw.splitlines()
    if not lines or lines[0] != expected_header:
        raise CheckpointError("cabecera/procedencia incompatible")
    records = []
    for index, line in enumerate(lines[1:]):
        try: frame = json.loads(line)
        except json.JSONDecodeError as error: raise CheckpointError("frame JSONL corrupto") from error
        if set(frame) != {"type", "index", "job_key", "record"} or frame["type"] != "result" or frame["index"] != index or index >= len(jobs):
            raise CheckpointError("índice o frame inválido")
        expected_key = _key_object(jobs[index].key)
        if frame["job_key"] != expected_key or any(frame["record"].get(key) != value for key, value in expected_key.items()):
            raise CheckpointError("clave de resultado incompatible")
        records.append(frame["record"])
    return records


def run_resumable(*, checkpoint_path: Path, provenance: Mapping[str, Any], jobs: Sequence[PlannedJob], execute: Callable[[PlannedJob], Mapping[str, Any]], policy_result: Callable[[PlannedJob], Mapping[str, Any]], on_progress: Callable[[Progress], None] | None = None, clock: Callable[[], float] = time.monotonic) -> list[Mapping[str, Any]]:
    _validate_jobs(jobs)
    header = {"type": "header", "checkpoint_version": "append-jsonl-checkpoint-v1", "provenance": {**provenance, "job_count": len(jobs), "ordered_job_plan_sha256": ordered_plan_sha256(jobs)}}
    recovered_records = _read_checkpoint(checkpoint_path, header, jobs)
    recovered = len(recovered_records);records=list(recovered_records);started=clock();execution_times=[];executed=0
    def emit(last_key=None):
        completed=len(records);remaining=len(jobs)-completed;pending=sum(job.requires_execution for job in jobs[completed:]);mean=sum(execution_times)/len(execution_times) if execution_times else None;eta=0.0 if pending==0 else mean*pending if mean is not None else None
        if on_progress:on_progress(Progress(len(jobs),recovered,completed,executed,remaining,pending,clock()-started,mean,eta,last_key))
    emit()
    with checkpoint_path.open("ab") as stream:
        for index in range(recovered,len(jobs)):
            job=jobs[index];before=clock();record=execute(job) if job.requires_execution else policy_result(job);after=clock()
            if job.requires_execution:execution_times.append(after-before);executed+=1
            expected=_key_object(job.key)
            if any(record.get(key)!=value for key,value in expected.items()):raise CheckpointError("callback devolvió identidad incorrecta")
            frame={"type":"result","index":index,"job_key":expected,"record":dict(record)};stream.write(canonical_bytes(frame)+b"\n");stream.flush();os.fsync(stream.fileno());records.append(dict(record));emit(job.key)
    return records


def finalize_json_atomic(*, output_path: Path, document: Mapping[str, Any]) -> None:
    payload=canonical_bytes(document)+b"\n";output_path.parent.mkdir(parents=True,exist_ok=True)
    if output_path.exists():
        if output_path.read_bytes()==payload:return
        raise CheckpointError("output existente diferente")
    fd,name=tempfile.mkstemp(prefix=output_path.name+".",suffix=".tmp",dir=output_path.parent)
    try:
        with os.fdopen(fd,"wb") as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(name,output_path)
        directory=os.open(output_path.parent,os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)
