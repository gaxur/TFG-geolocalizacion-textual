"""Runtime genérico DQ-Pilot para GB10; el núcleo no importa Torch ni Transformers."""
from __future__ import annotations

import gc
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from research.dq_pilot_iterative_controller_v1 import canonical
from research.dq_pilot_generation_transaction_v1 import GenerationTransaction, GenerationTransactionError
from research.dq_pilot_runtime_manifest_v2 import RuntimeManifestSpec
from research.dq_pilot_zero_shot_v1 import DQPilotHostError, INSTRUCTIONS, SYSTEM_PROMPT, validate_native_question


REQUEST_CONTRACT = "dq-pilot13-native-round-request-v1"
AUTHORIZATION_CONTRACT = "dq-pilot14-generation-authorization-v1"
AUTHORIZATION_CONTRACT_V2 = "dq-pilot17-generation-authorization-v2"
RUNTIME_CONTRACT = "dq-pilot14-gb10-runtime-v1"
RESULT_CONTRACT = "dq-pilot14-public-generation-v1"
TELEMETRY_CONTRACT = "dq-pilot14-runtime-telemetry-v1"
EXPECTED_MODEL_ID = "graysonggg/dlgpr"
EXPECTED_REVISION = "cf5c7b8a79ce055a83706fcbe0b94edf31b1cb40"
EXPECTED_PARAMETER_COUNT = 8_292_166_656
GENERATION = {
    "do_sample": False,
    "num_beams": 1,
    "max_new_tokens": 1024,
    "repetition_penalty": 1.05,
    "eos_token_ids": [151645, 151643],
    "pad_token_id": 151643,
    "use_cache": True,
    "automatic_retries": 0,
    "fallbacks": 0,
}
FORBIDDEN_KEYS = {
    "ground_truth", "ground_truth_candidate", "target_candidate_id",
    "correct_candidate", "reference_coordinate", "evaluation_metrics",
    "latitude", "longitude", "ct2l_rank", "cosine_similarity",
}


class DQPilotRuntimeError(RuntimeError):
    def __init__(self, code: str, stage: str, message: str):
        self.code = code
        self.stage = stage
        super().__init__(message)


class DQPilotBackend(Protocol):
    @property
    def identity(self) -> Mapping[str, Any]: ...
    def load(self) -> Mapping[str, Any]: ...
    def generate(self, *, request: Mapping[str, Any], request_root: Path) -> Mapping[str, Any]: ...
    def release(self, *, reason: str) -> Mapping[str, Any]: ...
    def resource_snapshot(self) -> Mapping[str, Any]: ...


class ResourceProbe(Protocol):
    def snapshot(self) -> Mapping[str, Any]: ...


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_private_json(path: Path, document: Mapping[str, Any], *, mode: int = 0o600) -> None:
    payload = canonical(document) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if path.exists():
        if path.read_bytes() != payload:
            raise DQPilotRuntimeError("OUTPUT_ROOT_CONFLICT", "publication", f"artefacto divergente: {path.name}")
        return
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def _reject_forbidden(value: Any, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() in FORBIDDEN_KEYS:
                raise DQPilotRuntimeError("REQUEST_INVALID", "validation", f"campo prohibido: {path}.{key}")
            _reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}[{index}]")


def load_and_validate_request(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    file_hash = sha256_bytes(raw)
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "request JSON inválido") from error
    if request.get("schema_version") != "1.0" or request.get("contract_version") != REQUEST_CONTRACT:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "contrato request incompatible")
    expected_id = "dq-pilot13-round-request-sha256-" + hashlib.sha256(canonical({key: value for key, value in request.items() if key != "request_id"})).hexdigest()
    if request.get("request_id") != expected_id:
        raise DQPilotRuntimeError("REQUEST_HASH_MISMATCH", "validation", "request_id divergente")
    if type(request.get("round_index")) is not int or request.get("round_index") not in {0, 1, 2}:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "DQ-Pilot solo admite rounds 0-2")
    if request.get("generation") != {key: GENERATION[key] for key in ("do_sample", "num_beams", "max_new_tokens", "repetition_penalty", "eos_token_ids", "pad_token_id", "use_cache", "automatic_retries", "fallbacks")}:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "configuración generativa divergente")
    constraints = request.get("constraints", {})
    if constraints != {"ground_truth_used": False, "coordinates_sent": False, "ranks_sent": False, "scores_sent": False, "answerer_used": False, "cmpl_used": False, "question_templates_used": False, "translation_performed": False}:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "restricciones request divergentes")
    images = request.get("images", [])
    if len(images) != 4 or [row.get("image_ref") for row in images] != ["I1", "I2", "I3", "I4"]:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "se requieren I1-I4")
    if [row.get("candidate_ref") for row in images] != ["C1", "C2", "C3", "C4"]:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "se requieren C1-C4")
    if len({row.get("sha256") for row in images}) != 4:
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "imágenes físicas duplicadas")
    history = request.get("history")
    if not isinstance(history, Mapping) or type(history.get("native_text")) is not str or type(history.get("turn_count")) is not int or not isinstance(history.get("prior_questions"), list) or any(type(value) is not str for value in history["prior_questions"]):
        raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "historial inválido")
    if history.get("sha256") != hashlib.sha256(history["native_text"].encode()).hexdigest() or history["turn_count"] != len(history["prior_questions"]):
        raise DQPilotRuntimeError("REQUEST_HASH_MISMATCH", "validation", "historial divergente")
    prompt_identity = request.get("native_prompt_identity", {})
    instruction_index = prompt_identity.get("instruction_index")
    if type(instruction_index) is not int or instruction_index not in range(len(INSTRUCTIONS)) or prompt_identity.get("instruction_sha256") != hashlib.sha256(INSTRUCTIONS[instruction_index].encode()).hexdigest() or prompt_identity.get("system_prompt_sha256") != hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() or type(prompt_identity.get("seed")) is not int:
        raise DQPilotRuntimeError("REQUEST_HASH_MISMATCH", "validation", "identidad prompt nativo divergente")
    _reject_forbidden(request)
    root = path.parent.resolve()
    for row in images:
        if type(row.get("size_bytes")) is not int or row["size_bytes"] < 1 or type(row.get("sha256")) is not str or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "metadata imagen inválida")
        logical = Path(str(row.get("logical_path", "")))
        image = (root / logical).resolve()
        if logical.is_absolute() or ".." in logical.parts or root not in image.parents or not image.is_file() or image.is_symlink():
            raise DQPilotRuntimeError("REQUEST_INVALID", "validation", "ruta de imagen inválida")
        if image.stat().st_size != row.get("size_bytes") or sha256_file(image) != row.get("sha256"):
            raise DQPilotRuntimeError("REQUEST_HASH_MISMATCH", "validation", "imagen divergente")
    return request, file_hash


def validate_authorization(
    document: Mapping[str, Any],
    *,
    request_sha256: str,
    runtime_sha256: str,
    runtime_implementation_sha256: str,
    checkpoint_manifest_sha256: str,
    worker_sha256: str,
    execution_supervisor_sha256: str,
    panel_artifact_sha256: str,
    ranking_artifact_sha256: str,
    configuration_sha256: str,
    preflight_sha256: str,
    source_panel_sha256: str,
    source_ranking_sha256: str,
    output_root: str,
    normalized_runtime_sha256: str | None = None,
    checkpoint_root: str | None = None,
    checkpoint_auxiliary_sha256: Mapping[str, str] | None = None,
    panel_ranking_lineage_sha256: str | None = None,
    source_package_manifest_sha256: str | None = None,
    failed_run_manifest_sha256: str | None = None,
    mode: str,
    require_approved: bool = True,
) -> None:
    expected = {
        "schema_version": "1.0",
        "contract_version": document.get("contract_version"),
        "request_sha256": request_sha256,
        "runtime_sha256": runtime_sha256,
        "runtime_implementation_sha256": runtime_implementation_sha256,
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "worker_sha256": worker_sha256,
        "execution_supervisor_sha256": execution_supervisor_sha256,
        "panel_artifact_sha256": panel_artifact_sha256,
        "ranking_artifact_sha256": ranking_artifact_sha256,
        "configuration_sha256": configuration_sha256,
        "preflight_sha256": preflight_sha256,
        "source_panel_sha256": source_panel_sha256,
        "source_ranking_sha256": source_ranking_sha256,
        "output_root": output_root,
        "mode": mode,
        "maximum_model_loads": 1,
        "maximum_generate_calls": 1,
        "queries": 1,
        "images": 4,
        "generation": GENERATION,
        "network_permitted": False,
        "downloads_permitted": False,
        "training_permitted": False,
        "ground_truth_permitted": False,
        "retain_private_output": True,
        "automatic_retries": 0,
        "fallbacks": 0,
        "authorization_consumed": False,
        "one_shot": True,
        "reusable": False,
    }
    contract = document.get("contract_version")
    if contract not in {AUTHORIZATION_CONTRACT, AUTHORIZATION_CONTRACT_V2}:
        raise DQPilotRuntimeError("AUTHORIZATION_SCOPE_MISMATCH", "authorization", "contract_version")
    if contract == AUTHORIZATION_CONTRACT_V2:
        expected.update({
            "normalized_runtime_sha256": normalized_runtime_sha256,
            "checkpoint_root": checkpoint_root,
            "checkpoint_auxiliary_sha256": dict(checkpoint_auxiliary_sha256 or {}),
            "panel_ranking_lineage_sha256": panel_ranking_lineage_sha256,
            "source_package_manifest_sha256": source_package_manifest_sha256,
            "failed_run_manifest_sha256": failed_run_manifest_sha256,
        })
    divergent = [key for key, value in expected.items() if document.get(key) != value]
    if divergent:
        raise DQPilotRuntimeError("AUTHORIZATION_SCOPE_MISMATCH", "authorization", ",".join(sorted(divergent)))
    if require_approved and (document.get("status") != "OPERATOR_AUTHORIZED" or document.get("approved") is not True or document.get("gpu_authorized") is not True):
        raise DQPilotRuntimeError("AUTHORIZATION_INVALID", "authorization", "autorización GPU no aprobada")
    if not require_approved and (document.get("approved") not in {False, True} or document.get("gpu_authorized") not in {False, True}):
        raise DQPilotRuntimeError("AUTHORIZATION_INVALID", "authorization", "estado de autorización inválido")


@dataclass(frozen=True)
class RuntimePolicy:
    mode: str = "one_shot"
    idle_unload_seconds: float | None = None
    lock_timeout_seconds: float = 0.0
    minimum_host_available_bytes: int = 40 * 1024**3
    maximum_available_spread_bytes: int = 1024**3
    maximum_psi_avg10: float = 0.10
    minimum_disk_free_bytes: int = 128 * 1024**2
    maximum_requests_per_session: int = 3
    maximum_model_loads_per_session: int = 3

    def __post_init__(self):
        if self.mode not in {"one_shot", "resident"}:
            raise ValueError("modo runtime inválido")
        if self.mode == "one_shot" and self.idle_unload_seconds is not None:
            raise ValueError("one-shot no admite idle timeout")
        if self.maximum_requests_per_session < 1 or self.maximum_model_loads_per_session < 1:
            raise ValueError("presupuesto de sesión inválido")


def evaluate_resource_guard(snapshot: Mapping[str, Any], policy: RuntimePolicy) -> list[str]:
    reasons = []
    if int(snapshot.get("host_available_bytes", 0)) < policy.minimum_host_available_bytes:
        reasons.append("host_available_below_threshold")
    if int(snapshot.get("host_available_spread_bytes", 0)) > policy.maximum_available_spread_bytes:
        reasons.append("host_memory_unstable")
    if float(snapshot.get("memory_psi_avg10", 999.0)) >= policy.maximum_psi_avg10:
        reasons.append("memory_psi_high_or_unverified")
    if snapshot.get("foreign_cuda_processes"):
        reasons.append("foreign_cuda_processes")
    if snapshot.get("ollama_models"):
        reasons.append("ollama_resident_or_unverified")
    if snapshot.get("blocking_vmstat_deltas"):
        reasons.append("active_swap_reclaim_or_oom")
    if int(snapshot.get("disk_free_bytes", 0)) < policy.minimum_disk_free_bytes:
        reasons.append("disk_free_below_threshold")
    return reasons


class LinuxGB10ResourceProbe:
    """Sonda host read-only; no importa Torch ni inicializa CUDA."""

    def __init__(self, *, disk_path: Path, samples: int = 5, interval_seconds: float = 2.0, sleep: Callable[[float], None] = time.sleep, ollama_observer=None):
        self.disk_path = disk_path
        self.samples = samples
        self.interval_seconds = interval_seconds
        self.sleep = sleep
        self.ollama_observer = ollama_observer

    @staticmethod
    def _sample() -> dict[str, Any]:
        mem = {line.split(":", 1)[0]: int(line.split(":", 1)[1].strip().split()[0]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()}
        wanted = {"pswpin", "pswpout", "pgmajfault", "pgscan_direct", "pgsteal_direct", "oom_kill"}
        vmstat = {key: int(value) for key, value in (line.split() for line in Path("/proc/vmstat").read_text().splitlines()) if key in wanted}
        psi_rows = {}
        for line in Path("/proc/pressure/memory").read_text().splitlines():
            parts = line.split(); psi_rows[parts[0]] = float(dict(item.split("=", 1) for item in parts[1:])["avg10"])
        gpu = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False)
        processes = []
        if gpu.returncode != 0:
            processes = ["NOT_VERIFIED"]
        else:
            for line in gpu.stdout.splitlines():
                value = line.strip()
                if value and value.split(",", 1)[0].strip() != str(os.getpid()):
                    processes.append(value)
        return {"available": mem["MemAvailable"], "swap_used": mem["SwapTotal"] - mem["SwapFree"], "vmstat": vmstat, "psi": max(psi_rows.values()), "gpu": processes}

    def snapshot(self) -> Mapping[str, Any]:
        rows = []
        for index in range(self.samples):
            rows.append(self._sample())
            if index + 1 < self.samples:
                self.sleep(self.interval_seconds)
        first, last = rows[0], rows[-1]
        deltas = {key: last["vmstat"][key] - first["vmstat"][key] for key in first["vmstat"]}
        available = [row["available"] for row in rows]
        if self.ollama_observer is not None:
            ollama_models = self.ollama_observer()
        else:
            ollama = subprocess.run(["ollama", "ps"], capture_output=True, text=True, check=False)
            if ollama.returncode != 0:
                ollama_models = ["NOT_VERIFIED"]
            else:
                lines = [line.strip() for line in ollama.stdout.splitlines() if line.strip()]
                ollama_models = lines[1:] if lines and lines[0].casefold().startswith("name") else lines
        return {
            "host_available_bytes": min(available),
            "host_available_spread_bytes": max(available) - min(available),
            "memory_psi_avg10": max(row["psi"] for row in rows),
            "swap_used_bytes": max(row["swap_used"] for row in rows),
            "foreign_cuda_processes": sorted({process for row in rows for process in row["gpu"]}),
            "ollama_models": ollama_models,
            "vmstat_deltas": deltas,
            "blocking_vmstat_deltas": {key: value for key, value in deltas.items() if key != "pgmajfault" and value != 0},
            "diagnostic_pgmajfault_delta": deltas.get("pgmajfault"),
            "disk_free_bytes": shutil.disk_usage(self.disk_path).free,
            "samples": rows,
        }


class DQPilotRuntime:
    """Lifecycle serializado one-shot/residente con autorizaciones por request."""

    def __init__(self, *, backend: DQPilotBackend, probe: ResourceProbe, policy: RuntimePolicy, outcome_schema: Mapping[str, Any], clock: Callable[[], float] = time.monotonic, stage_sink=None):
        self.backend = backend
        self.probe = probe
        self.policy = policy
        self.outcome_schema = outcome_schema
        self.clock = clock
        self.stage_sink = stage_sink
        self.state = "NEW"
        self.load_count = 0
        self.generate_count = 0
        self.request_sequence = 0
        self.last_activity: float | None = None
        self.completed_request_ids: set[str] = set()
        self.completed_rounds: set[int] = set()
        self.session_id: str | None = None
        self._lock = threading.Lock()

    def _stage(self, stage: str, **detail: Any) -> None:
        if self.stage_sink is not None:
            try:
                self.stage_sink.emit(stage, detail)
            except Exception as error:
                raise DQPilotRuntimeError("MONITOR_INTEGRITY_FAILURE", "monitor", type(error).__name__) from error

    def execute(self, *, request_path: Path, authorization: Mapping[str, Any], operation_root: Path, identities: Mapping[str, str]) -> dict[str, Any]:
        acquired = self._lock.acquire(timeout=self.policy.lock_timeout_seconds)
        if not acquired:
            raise DQPilotRuntimeError("RUNTIME_BUSY", "admission", "runtime ocupado")
        request = None
        request_sha = None
        started = self.clock()
        loaded_this_call = False
        try:
            if self.state in {"CLOSED", "FAILED"}:
                raise DQPilotRuntimeError("RUNTIME_FAILED", "admission", f"runtime {self.state}")
            request, request_sha = load_and_validate_request(request_path)
            if self.session_id is None:
                self.session_id = request.get("session_id")
            elif request.get("session_id") != self.session_id:
                raise DQPilotRuntimeError("REQUEST_INVALID", "admission", "request pertenece a otra sesión")
            if request["request_id"] in self.completed_request_ids or request["round_index"] in self.completed_rounds:
                raise DQPilotRuntimeError("REQUEST_INVALID", "admission", "request o ronda ya ejecutados en esta sesión")
            if self.generate_count >= self.policy.maximum_requests_per_session:
                raise DQPilotRuntimeError("AUTHORIZATION_SCOPE_MISMATCH", "admission", "máximo de requests de la sesión")
            if self.request_sequence == 0:
                self._stage("PRELOAD", request_id=request["request_id"], request_sequence=1)
            validate_authorization(authorization, request_sha256=request_sha, runtime_sha256=identities["runtime_sha256"], runtime_implementation_sha256=identities["runtime_implementation_sha256"], checkpoint_manifest_sha256=identities["checkpoint_manifest_sha256"], worker_sha256=identities["worker_sha256"], execution_supervisor_sha256=identities["execution_supervisor_sha256"], panel_artifact_sha256=identities["panel_artifact_sha256"], ranking_artifact_sha256=identities["ranking_artifact_sha256"], configuration_sha256=identities["configuration_sha256"], preflight_sha256=identities["preflight_sha256"], source_panel_sha256=request["source_panel_sha256"], source_ranking_sha256=request["source_ranking_sha256"], output_root=str(operation_root), normalized_runtime_sha256=identities.get("normalized_runtime_sha256"), checkpoint_root=identities.get("checkpoint_root"), checkpoint_auxiliary_sha256=identities.get("checkpoint_auxiliary_sha256"), panel_ranking_lineage_sha256=identities.get("panel_ranking_lineage_sha256"), source_package_manifest_sha256=identities.get("source_package_manifest_sha256"), failed_run_manifest_sha256=identities.get("failed_run_manifest_sha256"), mode=self.policy.mode)
            snapshot = dict(self.probe.snapshot())
            resource_snapshot = getattr(self.backend, "resource_snapshot", None)
            if callable(resource_snapshot):
                snapshot["backend"] = dict(resource_snapshot())
            reasons = evaluate_resource_guard(snapshot, self.policy)
            if reasons:
                raise DQPilotRuntimeError("MEMORY_PRESSURE_BLOCKED", "resource_guard", ",".join(reasons))
            operation_root.mkdir(parents=True, exist_ok=True)
            if self.state == "NEW":
                if self.policy.mode == "resident" and self.load_count > 0:
                    self.state = "FAILED"
                    raise DQPilotRuntimeError("RUNTIME_FAILED", "load", "sesión residente no permite recarga tras unload")
                if self.load_count >= self.policy.maximum_model_loads_per_session:
                    raise DQPilotRuntimeError("AUTHORIZATION_SCOPE_MISMATCH", "load", "presupuesto de cargas agotado")
                self.state = "LOADING"
                self._stage("MODEL_LOADING", load_sequence=self.load_count + 1)
                try:
                    load_metrics = dict(self.backend.load())
                except DQPilotRuntimeError:
                    raise
                except Exception as error:
                    raise DQPilotRuntimeError("BACKEND_LOAD_FAILED", "load", type(error).__name__) from error
                self.load_count += 1
                loaded_this_call = True
                self.state = "READY"
                self._stage("MODEL_READY", load_count=self.load_count)
            else:
                load_metrics = {"cache_hit": True, "load_ms": 0.0}
            self._stage("PROCESSING", request_id=request["request_id"])
            self.state = "GENERATING"
            self._stage("GENERATING", request_id=request["request_id"])
            transaction = GenerationTransaction.prepare(operation_root, request_sha256=request_sha, request_id=request["request_id"])
            transaction.mark_generate_started()
            try:
                generation = dict(self.backend.generate(request=request, request_root=request_path.parent))
            except DQPilotRuntimeError:
                raise
            except Exception as error:
                raise DQPilotRuntimeError("BACKEND_GENERATE_FAILED", "generation", type(error).__name__) from error
            self.generate_count += 1
            if generation.get("raw_output") is None:
                raise DQPilotRuntimeError("BACKEND_GENERATE_FAILED", "generation", "raw output ausente")
            private = transaction.commit_private(generation["raw_output"], {key: value for key, value in generation.items() if key != "raw_output"})
            transaction.validation_started()
            prior_questions = request.get("history", {}).get("prior_questions", [])
            try:
                checked = validate_native_question(generation["raw_output"], history_questions=prior_questions, outcome_schema=self.outcome_schema)
            except DQPilotHostError as error:
                transaction.host_decision(decision="REJECT", reasons=list(error.reasons), question=None, raw_commit_sha256=private["raw_commit_sha256"])
                transaction.terminal(status="HOST_REJECTED")
                raise DQPilotRuntimeError("PUBLIC_OUTPUT_INVALID", "validation", ",".join(error.reasons)) from error
            host_decision = transaction.host_decision(decision="ACCEPT", reasons=[], question=checked["public_question"], raw_commit_sha256=private["raw_commit_sha256"])
            result = {
                "schema_version": "1.0", "contract_version": RESULT_CONTRACT,
                "status": "generated", "request_id": request["request_id"],
                "request_sha256": request_sha, "panel_sha256": request["source_panel_sha256"],
                "source_ranking_sha256": request["source_ranking_sha256"],
                "question": checked["public_question"], "raw_output_sha256": private["raw_output_sha256"],
                "private_output_retained": True, "private_output_sha256": private["private_output_sha256"],
                "raw_commit_sha256": private["raw_commit_sha256"], "host_decision_sha256": host_decision["sha256"],
                "reasoning_public": False, "ground_truth_used": False,
                "host_validation": {"format": True, "text_safety": True, "exact_redundancy": True},
            }
            self.request_sequence += 1
            self.completed_request_ids.add(request["request_id"])
            self.completed_rounds.add(request["round_index"])
            self.last_activity = self.clock()
            self.state = "READY"
            self._stage("IDLE", request_id=request["request_id"], generate_count=self.generate_count)
            telemetry = {
                "schema_version": "1.0", "contract_version": TELEMETRY_CONTRACT,
                "request_id": request["request_id"], "request_sha256": request_sha,
                "mode": self.policy.mode, "request_sequence": self.request_sequence,
                "model_loads_total": self.load_count, "generate_calls_total": self.generate_count,
                "loaded_this_call": loaded_this_call, "load": load_metrics,
                "generation": {key: value for key, value in generation.items() if key != "raw_output"},
                "resource_guard": snapshot, "wall_ms": (self.clock() - started) * 1000,
                "automatic_retries": 0, "fallbacks": 0, "private_reasoning_exposed": False,
            }
            atomic_private_json(operation_root / "telemetry.json", telemetry)
            result["telemetry_sha256"] = sha256_file(operation_root / "telemetry.json")
            if self.policy.mode == "one_shot":
                release = self._release_locked("one_shot_complete")
                atomic_private_json(operation_root / "release.json", release)
                result["release_sha256"] = sha256_file(operation_root / "release.json")
            transaction.public_projection(result)
            atomic_private_json(operation_root / "public-result.json", result)
            transaction.terminal(status="PUBLISHED")
            return result
        except GenerationTransactionError as error:
            try:
                if 'transaction' in locals() and transaction.journal_path.exists() and transaction.journal().get("state") not in {"PRIVATE_RAW_COMMITTED", "HOST_ACCEPTED", "HOST_REJECTED", "PUBLIC_PROJECTION_COMMITTED", "TERMINAL_COMMITTED"}:
                    transaction._state("UNCERTAIN", persistence_error_code=error.code, persistence_error_stage=error.stage)
            except Exception:
                pass
            self.state = "FAILED"
            try:
                release = self._release_locked("private_persistence_failure")
                atomic_private_json(operation_root / "release.json", release)
            except Exception:
                self.state = "FAILED"
            raise DQPilotRuntimeError("PRIVATE_PERSISTENCE_FAILED", error.stage, error.code) from error
        except DQPilotRuntimeError as error:
            failure = {"schema_version": "1.0", "contract_version": "dq-pilot14-runtime-failure-v1", "status": "failed", "code": error.code, "stage": error.stage, "error_type": type(error).__name__, "message": str(error)[:500], "request_sha256": request_sha, "model_loads": self.load_count, "generate_calls": self.generate_count, "retry_permitted": False}
            operation_root.mkdir(parents=True, exist_ok=True)
            atomic_private_json(operation_root / "failure.json", failure)
            if self.state in {"LOADING", "READY", "GENERATING"}:
                try:
                    release = self._release_locked("runtime_failure")
                    atomic_private_json(operation_root / "release.json", release)
                except Exception:
                    self.state = "FAILED"
            raise
        finally:
            self._lock.release()

    def _release_locked(self, reason: str) -> dict[str, Any]:
        self.state = "RELEASING"
        self._stage("RELEASING", reason=reason)
        try:
            release = dict(self.backend.release(reason=reason))
        except Exception as error:
            self.state = "FAILED"
            raise DQPilotRuntimeError("BACKEND_RELEASE_FAILED", "release", type(error).__name__) from error
        residual = int(release.get("cuda_allocated_after_release_bytes", 0)) > 0
        if residual and self.policy.mode == "resident":
            self.state = "FAILED"
        else:
            self.state = "CLOSED" if self.policy.mode == "one_shot" or reason == "operator_close" else "NEW"
        return {"schema_version": "1.0", "contract_version": "dq-pilot14-release-v1", "reason": reason, **release, "exit_required": residual, "runtime_state": self.state}

    def reap_if_needed(self, *, memory_pressure: bool = False) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self.state != "READY":
                return False
            idle = self.policy.idle_unload_seconds is not None and self.last_activity is not None and self.clock() - self.last_activity >= self.policy.idle_unload_seconds
            if not idle and not memory_pressure:
                return False
            self._release_locked("memory_pressure" if memory_pressure else "idle_timeout")
            return True
        finally:
            self._lock.release()

    def close(self) -> Mapping[str, Any]:
        with self._lock:
            if self.state in {"CLOSED", "NEW"}:
                self.state = "CLOSED"
                return {"status": "already_released", "runtime_state": self.state}
            if self.state == "FAILED":
                raise DQPilotRuntimeError("RUNTIME_FAILED", "release", "runtime fallido")
            return self._release_locked("operator_close")


class TransformersGB10Backend:
    """Backend real con imports perezosos; construirlo no toca CUDA."""

    def __init__(self, *, model_root: Path, runtime_manifest: RuntimeManifestSpec):
        if not isinstance(runtime_manifest, RuntimeManifestSpec):
            raise DQPilotRuntimeError("RUNTIME_MANIFEST_INVALID", "static_contract", "backend requiere RuntimeManifestSpec v2")
        if model_root.resolve() != Path(runtime_manifest.checkpoint_root).resolve():
            raise DQPilotRuntimeError("RUNTIME_MANIFEST_INVALID", "static_contract", "model_root divergente del runtime normalizado")
        self.model_root = model_root
        self.runtime_manifest = runtime_manifest
        self.model = self.processor = self.torch = None
        self._identity = {"backend": "transformers-gb10-bf16-sdpa-v1", "model_id": EXPECTED_MODEL_ID, "revision": EXPECTED_REVISION, "device_map": {"": "cuda:0"}, "dtype": "bfloat16", "attention": "sdpa"}

    @property
    def identity(self) -> Mapping[str, Any]:
        return self._identity

    def load(self) -> Mapping[str, Any]:
        started = time.perf_counter()
        import torch
        import transformers
        from transformers import AutoConfig, AutoProcessor, Qwen2_5_VLForConditionalGeneration
        expected = self.runtime_manifest.versions
        if platform.machine() != self.runtime_manifest.architecture or torch.__version__ != expected.torch or transformers.__version__ != expected.transformers or torch.version.cuda != expected.cuda_build:
            raise DQPilotRuntimeError("BACKEND_LOAD_FAILED", "runtime_identity", "runtime efectivo divergente")
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise DQPilotRuntimeError("BACKEND_LOAD_FAILED", "runtime_identity", "se requiere una GPU visible")
        torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats(0)
        config = AutoConfig.from_pretrained(self.model_root, local_files_only=True)
        config._attn_implementation = self.runtime_manifest.attention
        self.processor = AutoProcessor.from_pretrained(self.model_root, local_files_only=True)
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(self.model_root, config=config, local_files_only=True, dtype=torch.bfloat16, attn_implementation=self.runtime_manifest.attention, device_map=dict(self.runtime_manifest.device_map), low_cpu_mem_usage=True, use_safetensors=True)
        self.model.eval(); torch.cuda.synchronize(0)
        if sum(parameter.numel() for parameter in self.model.parameters()) != self.runtime_manifest.parameter_count or {str(parameter.device) for parameter in self.model.parameters()} != {"cuda:0"} or {str(parameter.dtype) for parameter in self.model.parameters()} != {"torch.bfloat16"}:
            raise DQPilotRuntimeError("BACKEND_LOAD_FAILED", "model_identity", "placement/dtype/parámetros divergentes")
        configured_eos = self.model.generation_config.eos_token_id
        configured_eos = [configured_eos] if isinstance(configured_eos, int) else list(configured_eos or [])
        if configured_eos != GENERATION["eos_token_ids"] or self.processor.tokenizer.pad_token_id != GENERATION["pad_token_id"]:
            raise DQPilotRuntimeError("BACKEND_LOAD_FAILED", "generation_identity", "tokens especiales divergentes")
        self.torch = torch
        return {"cache_hit": False, "load_ms": (time.perf_counter() - started) * 1000, "cuda_allocated_bytes": torch.cuda.memory_allocated(0), "cuda_reserved_bytes": torch.cuda.memory_reserved(0), "device_name": torch.cuda.get_device_name(0), "compute_capability": list(torch.cuda.get_device_capability(0))}

    def generate(self, *, request: Mapping[str, Any], request_root: Path) -> Mapping[str, Any]:
        from PIL import Image
        images = {}
        preparation_started = time.perf_counter()
        try:
            for row in request["images"]:
                with Image.open(request_root / row["logical_path"]) as image:
                    images[row["image_ref"]] = image.convert("RGB").copy()
            messages = []
            image_order = []
            for message in request["native_messages"]:
                if isinstance(message["content"], str):
                    messages.append(message); continue
                content = []
                for item in message["content"]:
                    if item["type"] == "image":
                        image_order.append(item["image_ref"]); content.append({"type": "image", "image": images[item["image_ref"]]})
                    else:
                        content.append(item)
                messages.append({"role": message["role"], "content": content})
            inputs = self.processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
        finally:
            for image in images.values(): image.close()
        preparation_ms = (time.perf_counter() - preparation_started) * 1000
        expectation = request.get("processor_expectation")
        observed_grid = inputs.image_grid_thw.tolist()
        observed_shape = list(inputs.pixel_values.shape)
        observed_tokens = int(inputs.input_ids.shape[1])
        if not isinstance(expectation, Mapping) or set(expectation) != {"profile", "preprocessing", "image_order", "input_tokens", "pixel_values_shape", "image_grid_thw"} or type(expectation.get("profile")) is not str or expectation.get("preprocessing") != "rgb-convert-no-exif-transpose" or expectation.get("image_order") != ["I1", "I2", "I3", "I4"] or type(expectation.get("input_tokens")) is not int or not isinstance(expectation.get("pixel_values_shape"), list) or not isinstance(expectation.get("image_grid_thw"), list):
            raise DQPilotRuntimeError("REQUEST_INVALID", "processor", "perfil processor no congelado")
        if image_order != expectation["image_order"] or observed_grid != expectation["image_grid_thw"] or observed_shape != expectation["pixel_values_shape"] or observed_tokens != expectation["input_tokens"]:
            raise DQPilotRuntimeError("REQUEST_INVALID", "processor", "processor H27 divergente")
        inputs = inputs.to("cuda:0")
        timer = _FirstTokenTimer(time.perf_counter)
        started = time.perf_counter()
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=1024, repetition_penalty=1.05, eos_token_id=GENERATION["eos_token_ids"], pad_token_id=GENERATION["pad_token_id"], use_cache=True, streamer=timer, return_dict_in_generate=True)
        self.torch.cuda.synchronize(0)
        generation_ms = (time.perf_counter() - started) * 1000
        input_tokens = int(inputs.input_ids.shape[1])
        token_ids = output.sequences[0, input_tokens:].detach().cpu().tolist()
        raw = self.processor.decode(token_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        generated = len(token_ids)
        metrics = {"raw_output": raw, "image_preparation_ms": preparation_ms, "input_tokens": input_tokens, "generated_tokens": generated, "generation_ms": generation_ms, "time_to_first_token_ms": (timer.first_token_at - started) * 1000 if timer.first_token_at else None, "tokens_per_second": generated / (generation_ms / 1000) if generation_ms > 0 else None, "image_grid_thw": inputs.image_grid_thw.detach().cpu().tolist(), "pixel_values_shape": list(inputs.pixel_values.shape), "termination_reason": "eos_or_stop_token" if token_ids and token_ids[-1] in GENERATION["eos_token_ids"] else "maximum_new_tokens" if generated >= 1024 else "other", "cuda_peak_allocated_bytes": self.torch.cuda.max_memory_allocated(0), "cuda_peak_reserved_bytes": self.torch.cuda.max_memory_reserved(0)}
        del output, inputs, messages, images
        return metrics

    def resource_snapshot(self) -> Mapping[str, Any]:
        if self.torch is None:
            return {"model_resident": False, "cuda_allocated_bytes": 0, "cuda_reserved_bytes": 0}
        return {"model_resident": self.model is not None, "cuda_allocated_bytes": self.torch.cuda.memory_allocated(0), "cuda_reserved_bytes": self.torch.cuda.memory_reserved(0), "cuda_peak_allocated_bytes": self.torch.cuda.max_memory_allocated(0), "cuda_peak_reserved_bytes": self.torch.cuda.max_memory_reserved(0)}

    def release(self, *, reason: str) -> Mapping[str, Any]:
        started = time.perf_counter()
        self.model = None; self.processor = None
        gc.collect()
        if self.torch is not None:
            self.torch.cuda.empty_cache()
            try: self.torch.cuda.synchronize(0)
            except Exception: pass
            allocated = self.torch.cuda.memory_allocated(0); reserved = self.torch.cuda.memory_reserved(0)
        else:
            allocated = reserved = 0
        status = "IN_PROCESS_RELEASE_COMPLETE" if allocated == 0 and reserved == 0 else "IN_PROCESS_RESIDUAL_ALLOCATIONS"
        self.torch = None
        return {"status": status, "release_ms": (time.perf_counter() - started) * 1000, "cuda_allocated_after_release_bytes": allocated, "cuda_reserved_after_release_bytes": reserved}


class _FirstTokenTimer:
    def __init__(self, clock: Callable[[], float]):
        self.clock = clock; self.calls = 0; self.first_token_at = None
    def put(self, value) -> None:
        self.calls += 1
        if self.calls == 2 and self.first_token_at is None: self.first_token_at = self.clock()
    def end(self) -> None: pass


class DQPilotRuntimeExecutionPort:
    """Conecta PreparedDQPilotQuestionerAdapter con un runtime ya construido."""

    def __init__(self, *, runtime: DQPilotRuntime, authorization_resolver: Callable[[Path], tuple[Mapping[str, Any], Mapping[str, str]]]):
        self.runtime = runtime
        self.authorization_resolver = authorization_resolver

    def execute(self, *, request_path: Path, operation_root: Path) -> Mapping[str, Any]:
        authorization, identities = self.authorization_resolver(request_path)
        runtime_root = operation_root / "runtime"
        try:
            return self.runtime.execute(request_path=request_path, authorization=authorization, operation_root=runtime_root, identities=identities)
        except DQPilotRuntimeError as error:
            terminal_path, decision_path = runtime_root / "terminal-commit.json", runtime_root / "host-decision.json"
            if error.code == "PUBLIC_OUTPUT_INVALID" and terminal_path.is_file() and decision_path.is_file():
                terminal, decision = json.loads(terminal_path.read_text()), json.loads(decision_path.read_text())
                if terminal.get("status") == "HOST_REJECTED" and decision.get("decision") == "REJECT" and decision.get("publishable") is False:
                    request = json.loads(request_path.read_text())
                    return {"schema_version": "1.0", "contract_version": RESULT_CONTRACT, "status": "host_rejected", "request_id": request["request_id"], "request_sha256": sha256_file(request_path), "panel_sha256": request["source_panel_sha256"], "source_ranking_sha256": request["source_ranking_sha256"], "question": None, "private_output_retained": True, "reasoning_public": False, "ground_truth_used": False, "host_validation": {"status": "rejected", "reason_codes": decision.get("reason_codes", [])}, "host_decision_sha256": sha256_file(decision_path), "terminal_commit_sha256": sha256_file(terminal_path)}
            raise
