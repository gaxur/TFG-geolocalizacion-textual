"""Orquestación fail-fast y no reanudable para el piloto asistido I02-I04."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .append_jsonl_checkpoint import canonical_bytes, finalize_json_atomic
from .immutable_attempt_ledger import ImmutableAttemptLedger, execute_immutable_attempt


class BoundedPilotError(ValueError):
    pass


TARGET_IDS = ("I02", "I03", "I04")


@dataclass(frozen=True)
class PilotJob:
    index: int
    target_id: str
    cache_entry_id: str
    identity: Mapping[str, Any]
    payload: Any


def validate_pilot_scope(plan: Mapping[str, Any], authorization: Mapping[str, Any]) -> tuple[str, ...]:
    if "ordered_target_ids" not in plan:
        raise BoundedPilotError("plan acotado sin ordered_target_ids")
    target_ids = plan["ordered_target_ids"]
    if not isinstance(target_ids, list):
        raise BoundedPilotError("ordered_target_ids debe ser una lista")
    if len(target_ids) != 3 or len(set(target_ids)) != 3 or tuple(target_ids) != TARGET_IDS:
        raise BoundedPilotError("ordered_target_ids debe ser exactamente I02,I03,I04")
    plan_budget = plan.get("budget")
    if not isinstance(plan_budget, Mapping):
        raise BoundedPilotError("plan acotado sin presupuesto")
    required_budget = {
        "maximum_model_loads": 1,
        "maximum_scene_calls": 0,
        "maximum_annotation_calls": 3,
        "maximum_total_future_calls": 3,
        "maximum_calls_per_observation": 1,
        "maximum_new_tokens_per_call": 2048,
        "maximum_generated_tokens_total": 6144,
        "retry_permitted": False,
        "resume_permitted": False,
    }
    if any(plan_budget.get(key) != value for key, value in required_budget.items()):
        raise BoundedPilotError("presupuesto del plan acotado incompatible")
    execution_policy = plan.get("execution_policy")
    if not isinstance(execution_policy, Mapping) or execution_policy.get("continue_after_failure") is not False:
        raise BoundedPilotError("plan acotado no es fail-fast")
    required_authorization = {
        "target_ids": list(TARGET_IDS),
        "maximum_scene_calls": 0,
        "maximum_annotation_calls": 3,
        "maximum_total_future_calls": 3,
        "maximum_model_loads": 1,
        "maximum_calls_per_observation": 1,
        "retry_permitted": False,
        "resume_permitted": False,
        "continue_after_failure": False,
    }
    if any(authorization.get(key) != value for key, value in required_authorization.items()):
        raise BoundedPilotError("alcance o presupuesto del piloto incompatible")
    return TARGET_IDS


def claim_runtime_root(path: Path) -> None:
    if not path.parent.is_dir():
        raise BoundedPilotError("el padre del runtime no existe")
    try:
        path.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise BoundedPilotError("runtime existente: reanudación prohibida") from error


def _checkpoint_header(plan_id: str, jobs: Sequence[PilotJob]) -> dict[str, Any]:
    job_plan = [{"index": job.index, "target_id": job.target_id, "cache_entry_id": job.cache_entry_id, "identity": job.identity} for job in jobs]
    return {
        "type": "header",
        "checkpoint_version": "i20-bounded-pilot-checkpoint-v1",
        "plan_id": plan_id,
        "job_count": len(jobs),
        "ordered_job_plan_sha256": hashlib.sha256(canonical_bytes(job_plan)).hexdigest(),
    }


def _append_checkpoint(path: Path, *, index: int, job: PilotJob, record: Mapping[str, Any]) -> None:
    frame = {"type": "result", "index": index, "target_id": job.target_id, "cache_entry_id": job.cache_entry_id, "record": dict(record)}
    with path.open("ab") as stream:
        stream.write(canonical_bytes(frame) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute_bounded_pilot(
    *,
    runtime_root: Path,
    plan_id: str,
    jobs: Sequence[PilotJob],
    load_runtime: Callable[[], Any],
    generate_raw: Callable[[Any, PilotJob], tuple[str, Mapping[str, Any]]],
    parse_and_build: Callable[[PilotJob, str, Mapping[str, Any]], Mapping[str, Any]],
    release_runtime: Callable[[Any], None],
    now: Callable[[], str],
    write_report: Callable[[Path, Mapping[str, Any]], None] = lambda path, doc: finalize_json_atomic(output_path=path, document=doc),
    append_checkpoint: Callable[..., None] = _append_checkpoint,
) -> list[Mapping[str, Any]]:
    if tuple(job.target_id for job in jobs) != TARGET_IDS or tuple(job.index for job in jobs) != (0, 1, 2):
        raise BoundedPilotError("jobs del piloto incompletos o desordenados")
    if len({job.cache_entry_id for job in jobs}) != 3:
        raise BoundedPilotError("identidades de caché duplicadas")
    claim_runtime_root(runtime_root)
    finalize_json_atomic(output_path=runtime_root/"run-start.json",document={"schema_version":"1.0","contract_version":"i20-assisted-bounded-pilot-start-v1","plan_id":plan_id,"target_ids":list(TARGET_IDS),"started_at_utc":now(),"maximum_attempts":3,"resume_permitted":False,"retry_permitted":False})
    ledger = ImmutableAttemptLedger(runtime_root / "diagnostics", plan_id=plan_id, maximum_attempts=3)
    checkpoint = runtime_root / "checkpoints" / "annotation-proposals.jsonl"
    checkpoint.parent.mkdir(parents=True, exist_ok=False)
    checkpoint.write_bytes(canonical_bytes(_checkpoint_header(plan_id, jobs)) + b"\n")
    model_runtime = None
    records=[]
    current_stage="load_runtime";current_target=None
    try:
        model_runtime = load_runtime()
        for job in jobs:
            current_stage="generation_validation_and_result";current_target=job.target_id
            record = execute_immutable_attempt(
                ledger=ledger,
                kind="annotation",
                target_id=job.target_id,
                cache_entry_id=job.cache_entry_id,
                now=now,
                generate_raw=lambda job=job: generate_raw(model_runtime, job),
                parse_and_build=lambda raw, metadata, job=job: parse_and_build(job, raw, metadata),
            )
            current_stage="checkpoint_append";append_checkpoint(checkpoint, index=job.index, job=job, record=record)
            records.append(record)
        current_stage="aggregate_report";current_target=None
        report={
            "schema_version":"1.0",
            "contract_version":"i20-assisted-bounded-pilot-report-v1",
            "plan_id":plan_id,
            "target_ids":list(TARGET_IDS),
            "calls":ledger.summary(),
            "valid_annotation_proposals":len(records),
            "valid_scene_proposals":0,
            "retry_performed":False,
            "resume_performed":False,
            "human_review_required":True,
        }
        write_report(runtime_root / "pilot-report.json", report)
        return records
    except Exception as error:
        failure={"schema_version":"1.0","contract_version":"i20-assisted-bounded-pilot-failure-v1","plan_id":plan_id,"failed_at_utc":now(),"stage":current_stage,"target_id":current_target,"exception_type":type(error).__name__,"exception_message":str(error),"calls":ledger.summary(),"retry_performed":False,"resume_permitted":False}
        try:finalize_json_atomic(output_path=runtime_root/"run-failure.json",document=failure)
        except Exception:pass
        raise
    finally:
        if model_runtime is not None:
            release_runtime(model_runtime)
