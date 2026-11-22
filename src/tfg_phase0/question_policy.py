"""Puerto común de políticas de preguntas para el bucle FreeText-v1."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Callable, Mapping, Protocol, Sequence

ACTIONS = ("ASK", "STOP", "ABSTAIN", "ERROR")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class QuestionPolicyDecision:
    action: str
    policy_id: str
    question: str | None = None
    reason: str | None = None
    question_origin: str | None = None
    question_type: str | None = None
    evidence: tuple[Mapping[str, Any], ...] = ()
    raw: Mapping[str, Any] | None = None
    telemetry: Mapping[str, Any] | None = None
    lineage: Mapping[str, Any] | None = None
    error: Mapping[str, Any] | None = None

    def validate(self) -> "QuestionPolicyDecision":
        if self.action not in ACTIONS:
            raise ValueError("acción de question policy inválida")
        if not self.policy_id:
            raise ValueError("question policy sin identidad")
        if self.action == "ASK":
            if not self.question or self.reason is not None or self.error is not None:
                raise ValueError("ASK de question policy inválido")
        elif self.question is not None:
            raise ValueError("decisión no ASK contiene pregunta")
        if self.action in {"STOP", "ABSTAIN"} and (not self.reason or self.error is not None):
            raise ValueError("STOP/ABSTAIN sin reason válido")
        if self.action == "ERROR" and (self.error is None or self.reason is not None):
            raise ValueError("ERROR de question policy inválido")
        return self

    def document(self) -> dict[str, Any]:
        self.validate()
        value = asdict(self)
        value["evidence"] = list(self.evidence)
        value["question_sha256"] = hashlib.sha256(self.question.encode()).hexdigest() if self.question is not None else None
        value["decision_id"] = "question-policy-decision-sha256-" + hashlib.sha256(canonical(value)).hexdigest()
        return value


class QuestionPolicyPort(Protocol):
    @property
    def identity(self) -> Mapping[str, Any]: ...

    def decide(self, *, original_description: str, literal_history: Sequence[Mapping[str, Any]], ranking: Mapping[str, Any], stage: str, remaining_questions: int) -> QuestionPolicyDecision: ...


def normalize_visual_v10_result(output: Mapping[str, Any]) -> dict[str, Any]:
    """Proyecta artefactos V10 al puerto común sin modificar la pregunta."""
    if output.get("action") in ACTIONS:
        return dict(output)
    if output.get("status") == "failed" or output.get("failure"):
        failure = dict(output.get("failure") or output)
        return {"action": "ERROR", "question_origin": "technical_failure", "error": failure, "raw": output.get("raw"), "telemetry": output.get("telemetry"), "lineage": output.get("lineage", {})}
    decision = output.get("decision")
    if not isinstance(decision, Mapping):
        raise ValueError("resultado Worker V10 sin decisión")
    status = decision.get("status")
    if status == "ask":
        return {"action": "ASK", "question": decision.get("question"), "question_origin": decision.get("question_origin"), "question_type": decision.get("question_type"), "evidence": list(decision.get("selected_evidence", ())), "raw": output.get("raw"), "telemetry": output.get("telemetry"), "lineage": {"decision_id": decision.get("decision_id"), "response_sha256": output.get("response_sha256"), **dict(output.get("lineage", {}))}}
    if status == "abstained":
        kind = str(decision.get("abstention_kind", "")).upper()
        if kind not in {"STOP", "ABSTAIN"}:
            raise ValueError("abstención Worker V10 sin kind común")
        return {"action": kind, "reason": decision.get("abstention_reason"), "question_origin": decision.get("question_origin"), "raw": output.get("raw"), "telemetry": output.get("telemetry"), "lineage": {"response_sha256": output.get("response_sha256"), **dict(output.get("lineage", {}))}}
    raise ValueError("estado Worker V10 no proyectable")


def normalize_visual_outcome_v2(output: Mapping[str, Any]) -> dict[str, Any]:
    """Proyección prospectiva V9a; conserva outcome y compatibilidad legacy."""
    from src.tfg_phase0.question_policy_outcome_v2 import legacy_projection
    outcome = output.get("outcome_v2") or output.get("outcome")
    if not isinstance(outcome, Mapping):
        return normalize_visual_v10_result(output)
    projected = legacy_projection(outcome)
    projected["raw"] = output.get("raw")
    projected["telemetry"] = output.get("telemetry")
    projected["lineage"] = {"final_outcome": outcome["final_outcome"], "outcome_id": outcome["outcome_id"], **dict(output.get("lineage", {}))}
    if outcome["final_outcome"] == "VALIDATION_REJECTED":
        projected["question_origin"] = "validation_rejection"
    return projected


class VisualV8QuestionPolicyAdapter:
    """Adaptador CPU/inyección para Worker V10; no ejecuta ni formula preguntas."""

    def __init__(self, *, identity: Mapping[str, Any], context_builder: Callable[..., Mapping[str, Any]], invoke: Callable[[Mapping[str, Any]], Mapping[str, Any]]):
        self._identity = dict(identity)
        self.context_builder = context_builder
        self.invoke = invoke

    @property
    def identity(self) -> Mapping[str, Any]:
        return dict(self._identity)

    def decide(self, *, original_description: str, literal_history: Sequence[Mapping[str, Any]], ranking: Mapping[str, Any], stage: str, remaining_questions: int) -> QuestionPolicyDecision:
        context = self.context_builder(original_description=original_description, literal_history=literal_history, ranking=ranking, stage=stage, remaining_questions=remaining_questions)
        request = {"schema_version": "1.0", "contract_version": "freetext-v1-visual-question-policy-request-v1", "policy_identity": self.identity, "stage": stage, "remaining_questions": remaining_questions, "original_description": original_description, "literal_history": list(literal_history), "ranking": ranking, "visual_context": context}
        output = normalize_visual_v10_result(self.invoke(request))
        action = output.get("action")
        if action not in ACTIONS:
            raise ValueError("salida visual sin acción común")
        decision = QuestionPolicyDecision(action=action, policy_id=str(self._identity.get("policy_id", "dialoguevpr_visual_v8")), question=output.get("question"), reason=output.get("reason"), question_origin=output.get("question_origin"), question_type=output.get("question_type"), evidence=tuple(output.get("evidence", ())), raw=output.get("raw"), telemetry=output.get("telemetry"), lineage={"adapter": "visual_v8_worker_v10", "request_sha256": hashlib.sha256(canonical(request)).hexdigest(), "context": context, **dict(output.get("lineage", {}))}, error=output.get("error"))
        return decision.validate()
