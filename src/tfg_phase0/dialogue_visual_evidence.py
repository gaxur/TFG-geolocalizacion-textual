"""Contratos fail-closed para evidencia visual opcional en diálogo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from jsonschema import Draft202012Validator

from .interactive_dialogue import InteractiveDialogueError, QuestionIntent
from .visual_reranking import LIMITATIONS, compact_atomic_verdict_schema, verdict_only_prompt
from .visual_verifier import SUPPORTED_LOCAL_MODELS


VISUAL_EVIDENCE_CONTRACT = "dialogue-visual-evidence-v1"
VISUAL_STATES = {"supported", "contradicted", "unverifiable"}
VLM_IDENTITY = SUPPORTED_LOCAL_MODELS["qwen3-vl-8b"]
OBSERVER_MANIFEST_CONTRACT = "dialogue-observer-image-manifest-v1"
RESERVED_SET_EXCLUSION = "confirmed_not_from_ground_truth_h26_h37_h38_h61_or_other_reserved_sets"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


@dataclass(frozen=True)
class VisualEvidencePolicy:
    enabled: bool = False
    maximum_calls: int = 3
    allow_query_update: bool = False
    allow_ranking_update: bool = False
    require_observer_relation: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_calls <= 3:
            raise InteractiveDialogueError("presupuesto visual fuera de rango")
        if self.allow_query_update or self.allow_ranking_update:
            raise InteractiveDialogueError("la evidencia visual no puede modificar consulta o ranking")
        if not self.require_observer_relation:
            raise InteractiveDialogueError("la relación explícita con el observador es obligatoria")


@dataclass(frozen=True)
class VisualImageReference:
    image_id: str
    path: Path
    sha256: str
    provenance: Mapping[str, Any]
    authorized: bool
    authorization_id: str | None
    observer_relation: str = "unknown"


class DialogueVisualEvidenceProvider(Protocol):
    @property
    def metadata(self) -> Mapping[str, Any]: ...
    def has_image_for(self, feature: str) -> bool: ...
    def image_for(self, feature: str) -> VisualImageReference: ...
    def inspect(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


def load_observer_image_manifest(path: Path, schema_path: Path) -> tuple[dict[str, Any], VisualImageReference]:
    try:document=json.loads(path.read_text(encoding="utf-8"));schema=json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as error:raise InteractiveDialogueError("manifest observer_view ilegible") from error
    errors=list(Draft202012Validator(schema).iter_errors(document))
    if errors:raise InteractiveDialogueError("manifest observer_view inválido: "+errors[0].message)
    if document["contract_version"]!=OBSERVER_MANIFEST_CONTRACT or document["status"]!="authorized" or document["authorized"] is not True:raise InteractiveDialogueError("manifest observer_view no autorizado")
    if document["observer_relation"]!="observer_view" or not document["observer_relation_evidence"].strip():raise InteractiveDialogueError("relación observer_view no acreditada")
    if document["reserved_set_exclusion"]!=RESERVED_SET_EXCLUSION:raise InteractiveDialogueError("exclusión de GT y conjuntos reservados no acreditada")
    if not all(str(document[key]).strip() for key in ("source","author","license_or_authorization","session_id","intent_family","authorization_id")):raise InteractiveDialogueError("procedencia o autorización incompleta")
    logical=Path(document["logical_path"])
    if logical.is_absolute() or ".." in logical.parts:raise InteractiveDialogueError("ruta observer_view insegura")
    root=path.resolve().parent;image_path=(root/logical).resolve()
    if image_path.parent!=root or not image_path.is_file():raise InteractiveDialogueError("imagen observer_view ausente o fuera del directorio autorizado")
    if file_sha256(image_path)!=document["sha256"]:raise InteractiveDialogueError("hash observer_view divergente")
    provenance={"source":document["source"],"author":document["author"],"license_or_authorization":document["license_or_authorization"],"acquired_at_utc":document["acquired_at_utc"],"provenance_url":document["provenance_url"],"observer_relation_evidence":document["observer_relation_evidence"],"usage_restrictions":document["usage_restrictions"],"reserved_set_exclusion":document["reserved_set_exclusion"]}
    return document,VisualImageReference(document["image_id"],image_path,document["sha256"],provenance,True,document["authorization_id"],"observer_view")


def visual_claim(intent: QuestionIntent) -> dict[str, Any]:
    payload = {"kind": "object_presence", "value": {"feature": intent.feature, "label": intent.label}, "source_intent_id": intent.intent_id}
    return {"claim_id": "dialogue-visual-claim-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest(), **payload}


def validate_image(reference: VisualImageReference) -> tuple[bool, str | None]:
    if not reference.image_id.strip() or not reference.sha256 or len(reference.sha256) != 64:
        return False, "invalid_image_identity"
    if not reference.provenance or not reference.provenance.get("source"):
        return False, "missing_provenance"
    if not reference.authorized or not reference.authorization_id:
        return False, "image_not_authorized"
    if not reference.path.is_file():
        return False, "image_missing"
    if file_sha256(reference.path) != reference.sha256:
        return False, "image_hash_mismatch"
    return True, None


def evidence_record(*, request: Mapping[str, Any], provider: Mapping[str, Any], state: str, observed_evidence: str | None, raw_output: str | None, abstention_reason: str | None, limitations: list[str]) -> dict[str, Any]:
    if state not in VISUAL_STATES:
        raise InteractiveDialogueError("estado visual inválido")
    if state in {"supported", "contradicted"} and (not isinstance(observed_evidence, str) or not observed_evidence.strip()):
        raise InteractiveDialogueError("veredicto visual sin evidencia explícita")
    if state == "unverifiable" and not abstention_reason:
        raise InteractiveDialogueError("abstención visual sin motivo")
    payload = {
        "contract_version": VISUAL_EVIDENCE_CONTRACT,
        "session_id": request["session_id"], "turn_index": request["turn_index"],
        "intent_id": request["intent"]["intent_id"], "intent_family": request["intent"]["feature"],
        "question_sha256": request["question_sha256"], "input_ranking_sha256": request["input_ranking_sha256"],
        "claim": request["claim"], "image": request["image"], "provider": dict(provider),
        "state": state, "observed_evidence": observed_evidence, "raw_output": raw_output,
        "abstention_reason": abstention_reason, "limitations": limitations,
        "scope": "image_pixels_only_not_geographic_truth", "query_update_allowed": False,
        "ranking_update_allowed": False, "recorded_at_utc": utc_now(),
    }
    return {"evidence_id": "dialogue-visual-evidence-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest(), **payload}


def validate_evidence(record: Mapping[str, Any]) -> None:
    expected = {"evidence_id", "contract_version", "session_id", "turn_index", "intent_id", "intent_family", "question_sha256", "input_ranking_sha256", "claim", "image", "provider", "state", "observed_evidence", "raw_output", "abstention_reason", "limitations", "scope", "query_update_allowed", "ranking_update_allowed", "recorded_at_utc"}
    if set(record) != expected or record["contract_version"] != VISUAL_EVIDENCE_CONTRACT or record["state"] not in VISUAL_STATES:
        raise InteractiveDialogueError("contrato de evidencia visual incompatible")
    payload = {key: record[key] for key in record if key != "evidence_id"}
    if record["evidence_id"] != "dialogue-visual-evidence-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest():
        raise InteractiveDialogueError("hash de evidencia visual inválido")
    if record["query_update_allowed"] or record["ranking_update_allowed"] or record["scope"] != "image_pixels_only_not_geographic_truth":
        raise InteractiveDialogueError("evidencia visual excede su alcance")
    image = record["image"]; provider = record["provider"]
    if not isinstance(image, Mapping) or not isinstance(provider, Mapping) or not provider.get("model_id") or not provider.get("revision"):
        raise InteractiveDialogueError("evidencia visual sin identidad o productor")
    if record["state"] in {"supported", "contradicted"} and (not isinstance(record["observed_evidence"], str) or not record["observed_evidence"].strip()):
        raise InteractiveDialogueError("evidencia visual concluyente sin observación")
    if record["observed_evidence"] is not None and (not isinstance(record["observed_evidence"], str) or len(record["observed_evidence"]) > 120):
        raise InteractiveDialogueError("texto de evidencia visual inválido")
    if not isinstance(record["limitations"], list) or len(record["limitations"]) > 2 or len(record["limitations"]) != len(set(record["limitations"])) or any(value not in LIMITATIONS | {"runtime_not_initialized", "invalid_model_output", "provider_timeout", "observer_relation_unverified", "image_not_authorized", "image_missing", "image_hash_mismatch", "missing_provenance", "invalid_image_identity"} and not value.startswith("provider_error:") for value in record["limitations"]):
        raise InteractiveDialogueError("limitaciones visuales inválidas")
    if record["state"] in {"supported", "contradicted"} and (image.get("authorized") is not True or not image.get("authorization_id") or not image.get("provenance", {}).get("source") or image.get("observer_relation") != "observer_view"):
        raise InteractiveDialogueError("evidencia visual concluyente sin autorización o relación observador")
    if record["state"] == "unverifiable" and not record["abstention_reason"]:
        raise InteractiveDialogueError("evidencia visual no verificable sin motivo")


class FakeVisualEvidenceProvider:
    """Proveedor CPU determinista; nunca importa runtimes de modelo."""
    def __init__(self, *, images: Mapping[str, VisualImageReference], scenarios: Mapping[str, Mapping[str, Any]] | None = None):
        self.images = dict(images); self.scenarios = dict(scenarios or {}); self.calls: list[dict[str, Any]] = []

    @property
    def metadata(self) -> Mapping[str, Any]:
        return {"adapter": "fake-dialogue-visual-v1", "model_id": "fake/qwen3-vl-8b", "revision": "test", "real_model_inference": False, "gpu_used": False, "calls": list(self.calls)}

    def has_image_for(self, feature: str) -> bool:
        return feature in self.images
    def image_for(self, feature: str) -> VisualImageReference: return self.images[feature]

    def inspect(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        feature = request["intent"]["feature"]; reference = self.images[feature]; scenario = self.scenarios.get(feature, {"state": "unverifiable", "reason": "scripted_unverifiable"})
        self.calls.append({"feature": feature, "session_id": request["session_id"], "turn_index": request["turn_index"]})
        if scenario.get("mode") == "timeout": raise TimeoutError("fake visual timeout")
        if scenario.get("mode") == "exception": raise RuntimeError("fake visual exception")
        valid, reason = validate_image(reference)
        if not valid:
            return evidence_record(request=request, provider=self.metadata, state="unverifiable", observed_evidence=None, raw_output=None, abstention_reason=reason, limitations=[reason])
        if scenario.get("mode") == "invalid_output":
            return {"invalid": True}
        state = scenario.get("state", "unverifiable")
        return evidence_record(request=request, provider=self.metadata, state=state, observed_evidence=scenario.get("observed_evidence"), raw_output=scenario.get("raw_output", json.dumps({"verdict": state})), abstention_reason=scenario.get("reason") if state == "unverifiable" else None, limitations=list(scenario.get("limitations", [])))


class Qwen3VLDialogueEvidenceAdapter:
    """Frontera preparada para un ejecutor Qwen3-VL ya existente; no carga modelos."""
    def __init__(self, *, images: Mapping[str, VisualImageReference], timeout_seconds: float = 30.0):
        if timeout_seconds <= 0:
            raise InteractiveDialogueError("timeout VLM inválido")
        self.images = dict(images); self.timeout_seconds = timeout_seconds; self.calls: list[dict[str, Any]] = []
        self._metadata = {"adapter": "qwen3-vl-dialogue-evidence-v1", "model_id": VLM_IDENTITY["model_id"], "revision": VLM_IDENTITY["revision"], "weight_sha256": VLM_IDENTITY["weight_sha256"], "dtype": "bfloat16", "attention": "sdpa", "real_model_inference": False, "runtime_status": "request_builder_only"}

    @property
    def metadata(self) -> Mapping[str, Any]: return {**self._metadata, "calls": list(self.calls)}
    def has_image_for(self, feature: str) -> bool: return feature in self.images
    def image_for(self, feature: str) -> VisualImageReference: return self.images[feature]

    def inspect(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        reference = self.images[request["intent"]["feature"]]; valid, reason = validate_image(reference)
        if not valid: return evidence_record(request=request, provider=self.metadata, state="unverifiable", observed_evidence=None, raw_output=None, abstention_reason=reason, limitations=[reason])
        base_prompt = verdict_only_prompt({"kind": request["claim"]["kind"], "value": request["claim"]["value"], "evidence": {"text": request["intent"]["label"]}})
        prompt = base_prompt + " Devuelve además observed_evidence literal de los píxeles o null y limitations; no uses la mera ausencia como contradicción."
        call = {"prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "schema": compact_atomic_verdict_schema(), "image_id": reference.image_id, "image_sha256": reference.sha256, "do_sample": False, "max_new_tokens": 192, "timeout_seconds": self.timeout_seconds}
        self.calls.append(call)
        return evidence_record(request=request, provider=self.metadata, state="unverifiable", observed_evidence=None, raw_output=None, abstention_reason="runtime_not_initialized", limitations=["runtime_not_initialized"])


class RealQwen3VLDialogueEvidenceProvider:
    """Proveedor del diálogo que delega la inferencia a un worker externo aislado."""
    def __init__(self, *, manifest: Mapping[str,Any], reference: VisualImageReference, executor):
        self.manifest=dict(manifest);self.reference=reference;self.executor=executor;self.calls=[]
        self._metadata={"adapter":"qwen3-vl-dialogue-worker-v2","model_id":VLM_IDENTITY["model_id"],"revision":VLM_IDENTITY["revision"],"weight_sha256":VLM_IDENTITY["weight_sha256"],"dtype":"bfloat16","attention":"sdpa","real_model_inference":True,"runtime_status":"external_isolated_worker"}
    @property
    def metadata(self):return {**self._metadata,"calls":list(self.calls)}
    def has_image_for(self,feature):return feature==self.manifest["intent_family"]
    def image_for(self,feature):
        if not self.has_image_for(feature):raise InteractiveDialogueError("intención sin imagen observer_view")
        return self.reference
    def inspect(self,request):
        if request["session_id"]!=self.manifest["session_id"]:raise InteractiveDialogueError("sesión observer_view incompatible")
        if request["intent"]["feature"]!=self.manifest["intent_family"]:raise InteractiveDialogueError("intención observer_view incompatible")
        valid,reason=validate_image(self.reference)
        if not valid:raise InteractiveDialogueError(reason)
        result=self.executor(request,self.reference);raw=result.get("raw_output")
        parsed=result.get("parsed_output")
        if raw is not None:
            validated=parse_qwen3_vl_dialogue_output(raw)
            if parsed is not None and parsed!=validated:raise InteractiveDialogueError("respuesta worker divergente")
            parsed=validated
        elif isinstance(parsed,Mapping):parsed=parse_qwen3_vl_dialogue_output(json.dumps(parsed,ensure_ascii=False))
        else:raise InteractiveDialogueError("respuesta worker ausente")
        self.calls.append({"session_id":request["session_id"],"intent_family":request["intent"]["feature"],"image_sha256":self.reference.sha256,"worker_status":result.get("status")})
        state=parsed["verdict"];limitations=list(parsed["limitations"])
        return evidence_record(request=request,provider=self.metadata,state=state,observed_evidence=parsed["observed_evidence"],raw_output=json.dumps(parsed,ensure_ascii=False,separators=(",",":")),abstention_reason="worker_unverifiable" if state=="unverifiable" else None,limitations=limitations)


def parse_qwen3_vl_dialogue_output(raw: str) -> dict[str, Any]:
    """Valida una salida futura; la ejecución aislada se implementará en otro BUILD."""
    try: parsed = json.loads(raw)
    except json.JSONDecodeError as error: raise InteractiveDialogueError("salida VLM no es JSON") from error
    if not isinstance(parsed, dict) or set(parsed) != {"verdict", "observed_evidence", "ocr_text", "limitations"} or parsed["verdict"] not in VISUAL_STATES: raise InteractiveDialogueError("salida VLM incompatible")
    observed, ocr, limitations = parsed["observed_evidence"], parsed["ocr_text"], parsed["limitations"]
    if observed is not None and (not isinstance(observed, str) or not observed.strip() or len(observed) > 120): raise InteractiveDialogueError("observed_evidence inválida")
    if ocr is not None and (not isinstance(ocr, str) or len(ocr) > 160): raise InteractiveDialogueError("ocr_text inválido")
    if not isinstance(limitations, list) or len(limitations) > 2 or len(limitations) != len(set(limitations)) or any(value not in LIMITATIONS - {"generation_failed"} for value in limitations): raise InteractiveDialogueError("limitations inválidas")
    if parsed["verdict"] in {"supported", "contradicted"} and observed is None: raise InteractiveDialogueError("veredicto concluyente sin observación")
    if parsed["verdict"] == "unverifiable" and observed is not None: raise InteractiveDialogueError("abstención con evidencia concluyente")
    return parsed
