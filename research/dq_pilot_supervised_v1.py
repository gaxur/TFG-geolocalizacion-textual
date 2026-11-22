"""Contrato CPU de intercambio entre el supervisor de confianza y FastAPI."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from research.dq_pilot_iterative_controller_v1 import dialogue_history, digest, digest_text
from research.dq_pilot_real_adapters_v1 import (
    CT2L_IDENTITY, QWEN_IDENTITY, RealCT2LRetrieverAdapter, RealTextInterpreterAdapter, _history_turns,
)
from src.tfg_phase0.dialogue_freetext_v1 import build_freetext_prompt, render_literal_transcript

REGISTRATION = "atlas-dq-supervised-registration-v1"
OPERATION = "atlas-dq-supervised-operation-v1"
TERMINAL = "atlas-dq-supervised-terminal-v1"
POLICY_B_SHA256 = "df616dc79d3ddc2e77678d895902518cd0a3dfb68341739e4ef741624463b145"
POLICY_B_VERSION = "dq-pilot37-qwen-e0-memory-policy-b-v1"
QWEN_CPU_PROFILE = "qwen_cpu"
QWEN_CPU_CONFIG_SHA256 = digest(dict(profile=QWEN_CPU_PROFILE, version=1, device="cpu", dtype="bfloat16"))
HEX = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
OP_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
OperationId = Annotated[str, StringConstraints(pattern=OP_ID_PATTERN)]
DatasetId = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Stage = Literal["E0", "E1", "E2", "E3"]
Mode = Literal["cpu_fixture", "real"]
Component = Literal["qwen", "crosstext2loc", "dq_pilot", "qwen_translation"]
Status = Literal["SUCCEEDED", "FAILED", "STOPPED_MEMORY", "TIMED_OUT"]


class ContractError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ComponentConfig(StrictModel):
    configuration_sha256: HEX
    policy_sha256: HEX


class Registration(StrictModel):
    contract_version: Literal[REGISTRATION]
    session_id: str
    session_sha256: HEX
    description_sha256: HEX
    operation_id: OperationId
    mode: Mode
    qwen: ComponentConfig
    crosstext2loc: ComponentConfig
    candidate_set_sha256: HEX
    visual_dataset_id: DatasetId
    embedding_dataset_id: DatasetId
    dq_pilot: ComponentConfig | None = None
    qwen_translation: ComponentConfig | None = None


class Process(StrictModel):
    execution_id: DatasetId | None  # ID del contenedor/proceso observado, no el de la operación.
    terminated: bool
    running: bool | None
    restarting: bool | None
    pid: Annotated[int, Field(ge=0)] | None
    exit_code: int | None
    oom_killed: bool | None


class Release(StrictModel):
    verified: bool
    policy_compliant: bool
    cuda_released: bool
    worker_released: bool
    policy_sha256: HEX
    torch_allocated_bytes: Annotated[int, Field(ge=0)] | None
    torch_reserved_bytes: Annotated[int, Field(ge=0)] | None
    worker_device: Literal['cpu'] | None = None


class Evidence(StrictModel):
    supervisor_commit_sha256: HEX
    postflight_sha256: HEX
    worker_release_sha256: HEX | None


class DQPostExit(StrictModel):
    container_id: HEX
    launch_pid: Annotated[int, Field(gt=0)]
    cgroup_path: str
    cgroup_state: Literal['empty', 'removed']
    host_snapshot_sha256: HEX


class DQHostPostExit(StrictModel):
    invocation_id: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{32}$')]
    unit: str
    launch_pid: Annotated[int, Field(gt=0)]
    cgroup_path: str
    cgroup_state: Literal['empty', 'removed']
    host_snapshot_sha256: HEX


class VisualSafety(StrictModel):
    exclusive_lease_verified: Literal[True]
    timed_out: Literal[False]
    stop_reason: None
    dq_post_exit: DQPostExit | DQHostPostExit | None = None


class Terminal(StrictModel):
    contract_version: Literal[TERMINAL]
    mode: Mode
    session_id: str
    operation_id: OperationId
    operation_sha256: HEX
    stage: Stage
    component: Component
    model_revision: str
    configuration_sha256: HEX
    input_sha256: HEX
    status: Status
    output_sha256: HEX | None
    result: dict | None
    process: Process
    release: Release
    evidence: Evidence
    ground_truth_used: bool
    visual_safety: VisualSafety | None = None


def operation(registration, state, component, operation_id, *, interpretation=None, qwen_commit=None):
    stage = f"E{state['round_index']}"
    if stage not in {"E0", "E1", "E2", "E3"}:
        raise ContractError("etapa fuera del protocolo")
    input_doc = {"description_sha256": registration["description_sha256"],
                 "accumulated_description_sha256": digest_text(state["accumulated_description"])}
    if component == "qwen":
        transcript = render_literal_transcript(state["original_description"], _history_turns(dialogue_history(state["turns"])))
        prompt = build_freetext_prompt(transcript)
        input_doc.update(transcript=transcript, transcript_sha256=digest_text(transcript),
                         prompt=prompt, prompt_sha256=digest_text(prompt), session_sha256=registration["session_sha256"])
        model = QWEN_IDENTITY
        revision = model["revision"]
    elif component == "crosstext2loc":
        input_doc.update(text=interpretation["text"], text_sha256=interpretation["text_sha256"],
                         interpretation_sha256=digest(interpretation), qwen_terminal_sha256=qwen_commit,
                         query_id=f"{registration['session_id']}-{stage}", language="en", gallery_ids=["madrid-50m"], k=253,
                         candidate_set_sha256=registration["candidate_set_sha256"],
                         visual_dataset_id=registration["visual_dataset_id"], embedding_dataset_id=registration["embedding_dataset_id"])
        model = CT2L_IDENTITY
        revision = model["cvg_commit"]  # El checkpoint además tiene su propio SHA-256.
    else:
        raise ContractError("componente textual/descriptivo inválido")
    return dict(contract_version=OPERATION, session_id=registration["session_id"], operation_id=operation_id,
                stage=stage, component=component, mode=registration["mode"], model=model, model_revision=revision,
                **registration[component], input=input_doc, input_sha256=digest(input_doc), ground_truth_used=False)


BINDINGS = ("mode", "session_id", "operation_id", "stage", "component", "model_revision", "configuration_sha256", "input_sha256")


def validate_terminal(expected, terminal):
    if terminal["ground_truth_used"] is not False:
        raise ContractError("un resultado de inferencia no admite ground truth")
    if any(terminal[key] != expected[key] for key in BINDINGS) or terminal["operation_sha256"] != digest(expected):
        raise ContractError("terminal no corresponde a la operación esperada")
    process, release = terminal["process"], terminal["release"]
    if release["policy_sha256"] != expected["policy_sha256"]:
        raise ContractError("política de ejecución divergente")
    if terminal["status"] != "SUCCEEDED":
        if terminal["result"] is not None or terminal["output_sha256"] is not None:
            raise ContractError("un terminal fallido no admite salida")
        return
    if terminal["result"] is None or terminal["output_sha256"] != digest(terminal["result"]):
        raise ContractError("salida terminal ausente o hash divergente")
    visual = terminal.get('visual_safety') or {}
    if expected['component'] in {'dq_pilot','qwen_translation'} and (
            visual.get('exclusive_lease_verified') is not True or visual.get('timed_out') is not False
            or 'stop_reason' not in visual or visual['stop_reason'] is not None):
        raise ContractError('sin acreditación de lease, STOP y timeout visual')
    if (not process["execution_id"] or not process["terminated"] or process["running"] is not False
            or process["restarting"] is not False or process["pid"] != 0 or process["exit_code"] != 0
            or process["oom_killed"] is not False):
        raise ContractError("terminación correcta del proceso no acreditada")
    if not all(release[field] for field in ("verified", "policy_compliant", "cuda_released", "worker_released")):
        raise ContractError("cumplimiento de memoria o liberación no acreditados")
    allocated, reserved = release['torch_allocated_bytes'], release['torch_reserved_bytes']
    if expected['component'] == 'dq_pilot':
        proof = visual.get('dq_post_exit')
        valid_scope = False
        if proof is not None:
            path = proof['cgroup_path']; leaf = path.rsplit('/', 1)[-1]
            if 'invocation_id' in proof:
                unit = f"atlas-dq56-{expected['operation_id']}.service"
                valid_scope = proof['invocation_id'] == process['execution_id'] and proof['unit'] == leaf == unit
            else:
                cid = proof['container_id']
                valid_scope = cid == process['execution_id'] and leaf in (cid, f'docker-{cid}.scope')
            valid_scope = valid_scope and path.startswith('/') and '..' not in path.split('/')
        if (proof is None and (expected['mode'] == 'real' or allocated != 0 or reserved != 0)
                or proof is not None and not valid_scope
                or allocated is None or reserved is None or not 0 <= allocated <= reserved
                or terminal['evidence']['worker_release_sha256'] is None):
            raise ContractError('salida del contenedor/cgroup o release nativo DQ no acreditados')
    cpu_profile = (expected['component'] in {'qwen', 'qwen_translation'}
                   and expected['configuration_sha256'] == QWEN_CPU_CONFIG_SHA256)
    if cpu_profile or release.get('worker_device') is not None:
        proof = visual.get('dq_post_exit') or {}
        path = proof.get('cgroup_path', '')
        cid = proof.get('container_id')
        if (not cpu_profile or expected['mode'] != 'real' or expected['policy_sha256'] != POLICY_B_SHA256
                or release.get('worker_device') != 'cpu' or allocated is not None or reserved is not None
                or terminal['evidence']['worker_release_sha256'] is None
                or visual.get('exclusive_lease_verified') is not True or visual.get('timed_out') is not False
                or 'stop_reason' not in visual or visual['stop_reason'] is not None
                or proof.get('cgroup_state') not in ('empty', 'removed') or cid != process['execution_id']
                or not path.startswith('/') or '..' in path.split('/') or path.rsplit('/', 1)[-1] not in (cid, f'docker-{cid}.scope')):
            raise ContractError('liberación Qwen CPU no acreditada')
    elif expected['component'] in {'qwen', 'qwen_translation'} and (allocated != 0 or reserved != 0
                                                or terminal['evidence']['worker_release_sha256'] is None):
        raise ContractError("liberación Torch de Qwen no acreditada")


def project_qwen(expected, state, result):
    if result.get("ground_truth_used", False) is not False:
        raise ContractError("salida Qwen incompatible con el aislamiento de ground truth")
    input_doc = expected["input"]
    for key in ("description_sha256", "session_sha256", "transcript_sha256", "prompt_sha256"):
        if result.get(key) != input_doc[key]:
            raise ContractError(f"salida Qwen no ligada a {key}")
    if result.get("schema_version") != "1.0" or result.get("session_id") != expected["session_id"] or not isinstance(result.get("model"), dict):
        raise ContractError("sesión o modelo nativo Qwen divergente")
    if result["model"].get("prompt_version") != QWEN_IDENTITY["prompt_version"]:
        raise ContractError("prompt del modelo Qwen divergente")
    text, raw = result.get("text"), result.get("raw_output")
    if not isinstance(text, str) or not text.strip() or len(text) > 2400 or raw != text or text.startswith(("```", "{")) or "<think>" in text or "</think>" in text:
        raise ContractError("texto nativo Qwen inválido")

    class CommittedPort:
        def transform(self, **_):
            # El worker DQ32 no emite este flag. Solo el terminal verificado habilita el adaptador.
            return {**result, "model": {**result["model"], "real_model_inference": True}}

    projected = RealTextInterpreterAdapter(CommittedPort()).interpret(
        round_index=state["round_index"], original_description=state["original_description"],
        accumulated_description=state["accumulated_description"], dialogue_history=dialogue_history(state["turns"]))
    projected["model"]["real_model_inference"] = expected["mode"] == "real"
    return dict(projected, schema_version="1.0", step="llm-interpretation")


def project_ct2l(expected, state, result):
    if result.get("ground_truth_used", False) is not False:
        raise ContractError("salida CT2L incompatible con el aislamiento de ground truth")
    input_doc = expected["input"]

    class CommittedPort:
        def retrieve(self, **_):
            return result

    ranking = RealCT2LRetrieverAdapter(CommittedPort(), query_id=expected["session_id"],
        visual_dataset_id=input_doc["visual_dataset_id"], embedding_dataset_id=input_doc["embedding_dataset_id"]).retrieve(
        round_index=state["round_index"], interpreted_text=input_doc["text"])
    rows = ranking["results"]
    # Solo campos públicos del ranking; ni extras arbitrarios ni referencias privadas.
    fields = ("candidate_id", "rank", "latitude", "longitude", "cosine_similarity")
    for rank, row in enumerate(rows, 1):
        if not set(fields).issubset(row) or type(row["rank"]) is not int or row["rank"] != rank:
            raise ContractError("candidato CT2L incompleto")
        if any(type(row[key]) not in (int, float) or not low <= row[key] <= high
               for key, low, high in (("latitude", -90, 90), ("longitude", -180, 180), ("cosine_similarity", -1, 1))):
            raise ContractError("coordenadas o score CT2L inválidos")
    if rows != sorted(rows, key=lambda row: (-row["cosine_similarity"], row["candidate_id"])):
        raise ContractError("desempate CT2L no determinista")
    if digest(sorted(row["candidate_id"] for row in rows)) != input_doc["candidate_set_sha256"]:
        raise ContractError("universo CT2L divergente del catálogo fijado")
    return dict(ranking, results=[{field: row[field] for field in fields} for row in rows], schema_version="1.0", step="ct2l-ranking")


def make_terminal(expected, *, status, result, process, release, evidence, visual_safety=None):
    """Serializa el contrato común; no lee hardware ni autoriza ni lanza workers."""
    model = Terminal.model_validate(dict(contract_version=TERMINAL, **{key: expected[key] for key in BINDINGS},
        operation_sha256=digest(expected), status=status, result=result, output_sha256=digest(result) if result is not None else None,
        process=process, release=release, evidence=evidence, ground_truth_used=False,
        **({'visual_safety': visual_safety} if visual_safety is not None else {})))
    return model.model_dump(exclude_unset=True)


def from_qwen_postflight(expected, *, commit, postflight, worker_release=None, output_bytes=None, failure_status="FAILED"):
    """Proyecta los artefactos del lanzador con forma DQ38, sin alterar el worker.

    El supervisor debe haber verificado su claim/autorización antes de publicarlos.
    En una operación nueva, attempt_id es el UUID registrado y el plan vincula la operación.
    """
    if expected["component"] != "qwen" or (commit.get("session_id"), commit.get("attempt_id"), commit.get("plan_sha256"), commit.get("operation_sha256")) != (
            expected["session_id"], expected["operation_id"], expected["configuration_sha256"], digest(expected)):
        raise ContractError("commit nativo Qwen no ligado a la operación")
    if (expected["policy_sha256"] != POLICY_B_SHA256 or postflight.get("contract_version") != "dq-pilot37-postflight-b-v1"
            or postflight.get("memory_policy_version") != POLICY_B_VERSION
            or commit.get("postflight_sha256") != digest(postflight)
            or commit.get("worker_release_sha256") != (digest(worker_release) if worker_release is not None else None)):
        raise ContractError("postflight Qwen no ligado al terminal")
    completed = commit.get("status") in {"COMPLETED", "COMPLETED_WITH_MEMORY_WARNING"}
    if not completed and commit.get("status") != "FAILED":
        raise ContractError("commit nativo Qwen no terminal")
    memory = postflight.get("memory_policy") or {}
    host = postflight.get("host") or {}
    if completed and (commit.get("failure") is not None or postflight.get("status") != commit["status"]
            or postflight.get("errors") != [] or host.get("cuda_pids") != []
            or memory.get("version") != POLICY_B_VERSION or "stopped" not in memory or memory["stopped"] is not None
            or memory.get("has_memory_warning") is not (commit["status"] == "COMPLETED_WITH_MEMORY_WARNING")
            or not output_bytes or hashlib.sha256(output_bytes).hexdigest() != commit.get("result_sha256")):
        raise ContractError("archivo Qwen ausente o divergente del terminal nativo")
    if not completed and (failure_status == "SUCCEEDED" or commit.get("result_sha256") is not None):
        raise ContractError("commit fallido no admite salida")
    state, torch = postflight.get("state") or {}, worker_release or {}
    result = json.loads(output_bytes) if completed else None
    return make_terminal(expected, status="SUCCEEDED" if completed else failure_status, result=result,
        process=dict(execution_id=postflight.get("container_id"), terminated=postflight.get("container_termination_verified") is True,
                     running=state.get("Running"), restarting=state.get("Restarting"), pid=state.get("Pid"),
                     exit_code=state.get("ExitCode"), oom_killed=state.get("OOMKilled")),
        release=dict(verified=all(postflight.get(key) is True for key in ("verified", "resource_release_verified", "operation_succeeded")),
                     policy_compliant=postflight.get("policy_compliant") is True, cuda_released=postflight.get("cuda_release_observed") is True,
                     worker_released=postflight.get("worker_release_verified") is True, policy_sha256=expected["policy_sha256"],
                     torch_allocated_bytes=torch.get("allocated_bytes"), torch_reserved_bytes=torch.get("reserved_bytes")),
         evidence=dict(supervisor_commit_sha256=digest(commit), postflight_sha256=digest(postflight),
                       worker_release_sha256=digest(worker_release) if worker_release is not None else None))


def from_ct2l_postflight(expected, *, commit, postflight, output_bytes=None):
    """Usa la salida nativa intacta. La observación de release viene del supervisor, no del JSON de ranking."""
    if (expected["component"] != "crosstext2loc"
            or any(commit.get(key) != expected[key] for key in ("session_id", "operation_id", "configuration_sha256"))
            or commit.get("operation_sha256") != digest(expected) or commit.get("postflight_sha256") != digest(postflight)
            or postflight.get("contract_version") != "atlas-dq-ct2l-postflight-v1"
            or postflight.get("policy_sha256") != expected["policy_sha256"]):
        raise ContractError("commit/postflight CT2L no ligado a la operación")
    status = commit.get("status")
    if status == "SUCCEEDED":
        if not output_bytes or hashlib.sha256(output_bytes).hexdigest() != commit.get("result_sha256"):
            raise ContractError("archivo CT2L ausente o divergente del commit nativo")
        result = json.loads(output_bytes)
    elif status in {"FAILED", "STOPPED_MEMORY", "TIMED_OUT"} and commit.get("result_sha256") is None:
        result = None
    else:
        raise ContractError("commit CT2L no terminal o con salida en fallo")
    return make_terminal(expected, status=status, result=result, process=postflight["process"],
        release=dict(verified=postflight.get("resource_release_verified") is True,
                     policy_compliant=postflight.get("policy_compliant") is True,
                     cuda_released=postflight.get("cuda_pids") == [], worker_released=postflight.get("worker_close_verified") is True,
                     policy_sha256=expected["policy_sha256"], torch_allocated_bytes=None, torch_reserved_bytes=None),
        evidence=dict(supervisor_commit_sha256=digest(commit), postflight_sha256=digest(postflight), worker_release_sha256=None))
