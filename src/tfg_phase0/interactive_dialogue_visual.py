"""Extensión v3 del diálogo multivuelta con evidencia visual conservadora."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import os
from typing import Any, Mapping

from .dialogue_visual_evidence import DialogueVisualEvidenceProvider, VisualEvidencePolicy, evidence_record, validate_evidence, validate_image, visual_claim
from .interactive_dialogue import InteractiveDialogueError, QuestionIntent, _canonical_json_bytes, _sha256
from .interactive_dialogue_multiturn import MultiTurnConfig, MultiTurnDialogueOrchestrator, project_visual_session_to_v2, validate_multiturn_session


CONTRACT_VERSION_V3 = "interactive-dialogue-session-v3"


@dataclass(frozen=True)
class VisualMultiTurnConfig:
    dialogue: MultiTurnConfig = MultiTurnConfig()
    visual: VisualEvidencePolicy = VisualEvidencePolicy()


def _as_v2(session: Mapping[str, Any]) -> dict[str, Any]:
    return project_visual_session_to_v2(session)


class VisualMultiTurnDialogueOrchestrator:
    def __init__(self, *, retriever, evidence, config: VisualMultiTurnConfig, text_adapter=None, visual_provider: DialogueVisualEvidenceProvider | None = None):
        self.retriever = retriever; self.evidence = evidence; self.config = config; self.text_adapter = text_adapter; self.visual_provider = visual_provider
        if config.visual.enabled and visual_provider is None:
            raise InteractiveDialogueError("evidencia visual habilitada sin proveedor")
        self._base = MultiTurnDialogueOrchestrator(retriever=retriever, evidence=evidence, config=config.dialogue, text_adapter=text_adapter)

    def start(self, *, session_label: str, description: str, language: str = "es") -> dict[str, Any]:
        session = self._base.start(session_label=session_label, description=description, language=language)
        return self.from_base_session(session, inspect_pending=True)

    def from_base_session(self, session: Mapping[str, Any], *, inspect_pending: bool = False) -> dict[str, Any]:
        """Convierte una transición v2 ya ejecutada sin repetir recuperación."""
        validate_multiturn_session(session);session=json.loads(json.dumps(session,ensure_ascii=False))
        session["contract_version"] = CONTRACT_VERSION_V3
        session["visual_policy"] = {"enabled": self.config.visual.enabled, "maximum_calls": self.config.visual.maximum_calls, "allow_query_update": False, "allow_ranking_update": False, "require_observer_relation": self.config.visual.require_observer_relation}
        session["visual_evidence"] = []; session["source_conflicts"] = []
        session["models"]["vlm"] = {"enabled": self.config.visual.enabled, "provider": dict(self.visual_provider.metadata) if self.visual_provider else None, "calls": 0, "query_updates": 0, "ranking_updates": 0}
        if inspect_pending and self.config.visual.enabled and session["status"] == "awaiting_answer": self._inspect_pending(session)
        validate_visual_session(session)
        return session

    def inspect_pending(self, session: Mapping[str,Any]) -> dict[str,Any]:
        """Aplica solo la transición visual pendiente; nunca ejecuta retrieval."""
        validate_visual_session(session);result=json.loads(json.dumps(session,ensure_ascii=False))
        if not self.config.visual.enabled or result["status"]!="awaiting_answer":raise InteractiveDialogueError("sesión sin inspección visual pendiente")
        result["models"]["vlm"]={"enabled":True,"provider":dict(self.visual_provider.metadata),"calls":len(result["visual_evidence"]),"query_updates":0,"ranking_updates":0}
        self._inspect_pending(result);validate_visual_session(result);return result

    def answer(self, session: Mapping[str, Any], answer: str) -> dict[str, Any]:
        validate_visual_session(session)
        result = self._base.answer(_as_v2(session), answer)
        return self.from_base_answer_result(session,result,inspect_pending=True)

    def from_base_answer_result(self, session: Mapping[str,Any], result: Mapping[str,Any], *, inspect_pending: bool = False) -> dict[str,Any]:
        """Fusiona una transición v2 aislada con la evidencia v3 previa."""
        validate_visual_session(session);validate_multiturn_session(result);result=json.loads(json.dumps(result,ensure_ascii=False));previous_visual=json.loads(json.dumps(session["visual_evidence"],ensure_ascii=False));previous_conflicts=json.loads(json.dumps(session["source_conflicts"],ensure_ascii=False));previous_policy=dict(session["visual_policy"]);visual_links={turn["index"]:turn.get("visual_evidence_id") for turn in session["turns"]}
        for turn in result["turns"]: turn["visual_evidence_id"] = visual_links.get(turn["index"])
        result["contract_version"] = CONTRACT_VERSION_V3; result["visual_policy"] = previous_policy; result["visual_evidence"] = previous_visual; result["source_conflicts"] = previous_conflicts
        result["models"]["vlm"] = {"enabled": self.config.visual.enabled, "provider": dict(self.visual_provider.metadata) if self.visual_provider else None, "calls": len(previous_visual), "query_updates": 0, "ranking_updates": 0}
        answered = result["turns"][len([turn for turn in result["turns"] if turn["answer"] is not None]) - 1]
        self._detect_conflict(result, answered)
        if inspect_pending and self.config.visual.enabled and result["status"] == "awaiting_answer": self._inspect_pending(result)
        validate_visual_session(result)
        return result

    def _inspect_pending(self, session: dict[str, Any]) -> None:
        turn = session["turns"][-1]; feature = turn["question"]["feature"]
        if len(session["visual_evidence"]) >= self.config.visual.maximum_calls or not self.visual_provider.has_image_for(feature): return
        intent = QuestionIntent(turn["question"]["intent_id"], feature, turn["question"]["label"], tuple(turn["question"]["supported_hypothesis_ids"]), tuple(turn["question"]["unknown_hypothesis_ids"]), tuple(turn["question"]["evidence_refs"]), turn["question"]["deterministic_question"], ())
        reference = self.visual_provider.image_for(feature)
        request = {"session_id": session["session_id"], "turn_index": turn["index"], "intent": {"intent_id": intent.intent_id, "feature": intent.feature, "label": intent.label}, "question_sha256": hashlib.sha256(turn["question"]["final_question"].encode()).hexdigest(), "input_ranking_sha256": turn["input_ranking_sha256"], "claim": visual_claim(intent), "image": {"image_id": reference.image_id, "sha256": reference.sha256, "logical_path": str(reference.path), "provenance": dict(reference.provenance), "authorized": reference.authorized, "authorization_id": reference.authorization_id, "observer_relation": reference.observer_relation}}
        valid, reason = validate_image(reference)
        if not valid:
            record = evidence_record(request=request, provider=dict(self.visual_provider.metadata), state="unverifiable", observed_evidence=None, raw_output=None, abstention_reason=reason, limitations=[reason])
        elif self.config.visual.require_observer_relation and reference.observer_relation != "observer_view":
            record = evidence_record(request=request, provider=dict(self.visual_provider.metadata), state="unverifiable", observed_evidence=None, raw_output=None, abstention_reason="observer_relation_unverified", limitations=["observer_relation_unverified"])
        else:
            try:
                record = self.visual_provider.inspect(request); validate_evidence(record)
            except TimeoutError: record = self._fallback(request, "provider_timeout")
            except Exception as error: record = self._fallback(request, f"provider_error:{type(error).__name__}")
        validate_evidence(record); session["visual_evidence"].append(record); turn["visual_evidence_id"] = record["evidence_id"]
        session["models"]["vlm"] = {"enabled": True, "provider": dict(self.visual_provider.metadata), "calls": len(session["visual_evidence"]), "query_updates": 0, "ranking_updates": 0}
        self._base._event(session["events"], "visual_evidence_recorded", {"turn_index": turn["index"], "evidence_id": record["evidence_id"], "state": record["state"], "evidence_sha256": _sha256(record), "query_changed": False, "ranking_changed": False})

    def _fallback(self, request: Mapping[str, Any], reason: str) -> dict[str, Any]:
        from .dialogue_visual_evidence import evidence_record
        return evidence_record(request=request, provider=dict(self.visual_provider.metadata), state="unverifiable", observed_evidence=None, raw_output=None, abstention_reason=reason, limitations=[reason])

    @staticmethod
    def _detect_conflict(session: dict[str, Any], turn: Mapping[str, Any]) -> None:
        evidence_id = turn.get("visual_evidence_id")
        if not evidence_id or not turn.get("answer") or not turn["answer"]["interpretation"]["informative"]: return
        visual = next(row for row in session["visual_evidence"] if row["evidence_id"] == evidence_id); interpretation = turn["answer"]["interpretation"]; polarity = interpretation["polarity"]
        answered_feature = interpretation.get("correction", {}).get("feature") if interpretation.get("correction") else turn["question"]["feature"]
        if answered_feature != visual["intent_family"]: return
        conflict = (polarity == "positive" and visual["state"] == "contradicted") or (polarity == "negative" and visual["state"] == "supported")
        if conflict:
            payload = {"turn_index": turn["index"], "intent_family": turn["question"]["feature"], "human_answer_sha256": turn["answer"]["sha256"], "visual_evidence_id": evidence_id, "resolution": "preserve_human_query_and_record_conflict", "query_changed": False, "ranking_changed": False}
            record = {"conflict_id": "dialogue-source-conflict-sha256-" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(), **payload}; session["source_conflicts"].append(record)
            VisualMultiTurnDialogueOrchestrator._append_visual_conflict_event(session, record)

    @staticmethod
    def _append_visual_conflict_event(session: dict[str, Any], record: Mapping[str, Any]) -> None:
        # Añadir el evento después de los eventos textuales conserva su cadena y procedencia.
        MultiTurnDialogueOrchestrator._event(session["events"], "source_conflict_recorded", {"conflict_id": record["conflict_id"], "turn_index": record["turn_index"], "query_changed": False, "ranking_changed": False})


def validate_visual_session(session: Mapping[str, Any]) -> None:
    required = set(_as_v2(session)) | {"visual_policy", "visual_evidence", "source_conflicts"}
    if set(session) != required or session.get("contract_version") != CONTRACT_VERSION_V3:
        raise InteractiveDialogueError("contrato de sesión visual incompatible")
    validate_multiturn_session(_as_v2(session))
    policy = session["visual_policy"]
    vlm_model = session["models"]["vlm"]
    if policy["require_observer_relation"] is not True or policy["enabled"] != vlm_model["enabled"] or len(session["visual_evidence"]) > policy["maximum_calls"] or (session["visual_evidence"] and not vlm_model.get("provider")):
        raise InteractiveDialogueError("política visual persistida incoherente")
    if policy["allow_query_update"] or policy["allow_ranking_update"] or vlm_model["query_updates"] or vlm_model["ranking_updates"]:
        raise InteractiveDialogueError("VLM modificó recuperación o consulta")
    by_id = {}
    for record in session["visual_evidence"]:
        validate_evidence(record); by_id[record["evidence_id"]] = record
        turn = session["turns"][record["turn_index"] - 1]
        intent = QuestionIntent(turn["question"]["intent_id"], turn["question"]["feature"], turn["question"]["label"], tuple(turn["question"]["supported_hypothesis_ids"]), tuple(turn["question"]["unknown_hypothesis_ids"]), tuple(turn["question"]["evidence_refs"]), turn["question"]["deterministic_question"], ())
        expected_claim = visual_claim(intent); session_provider = vlm_model.get("provider") or {}
        provider_matches = all(record["provider"].get(key) == session_provider.get(key) for key in ("adapter", "model_id", "revision", "real_model_inference"))
        if record["session_id"] != session["session_id"] or record["intent_id"] != turn["question"]["intent_id"] or record["intent_family"] != turn["question"]["feature"] or record["claim"] != expected_claim or not provider_matches or record["question_sha256"] != hashlib.sha256(turn["question"]["final_question"].encode()).hexdigest() or record["input_ranking_sha256"] != turn["input_ranking_sha256"]:
            raise InteractiveDialogueError("evidencia visual no corresponde al turno")
        if turn.get("visual_evidence_id") != record["evidence_id"]:
            raise InteractiveDialogueError("turno y evidencia visual no enlazados")
    if len(by_id) != len(session["visual_evidence"]) or session["models"]["vlm"]["calls"] != len(by_id): raise InteractiveDialogueError("conteo visual incoherente")
    visual_events = [event for event in session["events"] if event["kind"] == "visual_evidence_recorded"]
    if len(visual_events) != len(by_id): raise InteractiveDialogueError("eventos visuales incompletos")
    for event in visual_events:
        record = by_id.get(event["payload"]["evidence_id"])
        if record is None or event["payload"] != {"turn_index": record["turn_index"], "evidence_id": record["evidence_id"], "state": record["state"], "evidence_sha256": _sha256(record), "query_changed": False, "ranking_changed": False}: raise InteractiveDialogueError("evento visual inválido")
    for conflict in session["source_conflicts"]:
        payload = {key: conflict[key] for key in conflict if key != "conflict_id"}
        visual = by_id.get(conflict["visual_evidence_id"]); turn = session["turns"][conflict["turn_index"] - 1]
        interpretation = turn.get("answer", {}).get("interpretation", {}); polarity = interpretation.get("polarity")
        actual_conflict = visual is not None and conflict["intent_family"] == visual["intent_family"] == turn["question"]["feature"] and ((polarity == "positive" and visual["state"] == "contradicted") or (polarity == "negative" and visual["state"] == "supported"))
        if conflict["conflict_id"] != "dialogue-source-conflict-sha256-" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest() or not actual_conflict or conflict["human_answer_sha256"] != turn["answer"]["sha256"] or conflict["query_changed"] or conflict["ranking_changed"]: raise InteractiveDialogueError("conflicto de fuentes inválido")
    conflict_events = [event for event in session["events"] if event["kind"] == "source_conflict_recorded"]
    if len(conflict_events) != len(session["source_conflicts"]): raise InteractiveDialogueError("eventos de conflicto incompletos")
    conflicts_by_id = {record["conflict_id"]: record for record in session["source_conflicts"]}
    for event in conflict_events:
        record = conflicts_by_id.get(event["payload"].get("conflict_id"))
        if record is None or event["payload"] != {"conflict_id": record["conflict_id"], "turn_index": record["turn_index"], "query_changed": False, "ranking_changed": False}: raise InteractiveDialogueError("evento de conflicto inválido")


def write_visual_session(session: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    validate_visual_session(session); output_dir.mkdir(parents=True, exist_ok=False)
    session_path, events_path = output_dir / "session.json", output_dir / "events.jsonl"
    payloads = {session_path: _canonical_json_bytes(session, newline=True), events_path: b"".join(_canonical_json_bytes(row, newline=True) for row in session["events"])}
    temporaries = []
    try:
        for path, payload in payloads.items():
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp"); temporaries.append(temporary)
            with temporary.open("xb") as stream: stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        for path, temporary in zip(payloads, temporaries, strict=True): os.replace(temporary, path)
        directory_fd=os.open(output_dir,os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        if json.loads(session_path.read_text(encoding="utf-8")) != session or [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] != session["events"]: raise InteractiveDialogueError("persistencia visual divergente")
    except Exception:
        for path in (*temporaries,session_path,events_path):
            if path.exists(): path.unlink()
        raise
    return session_path, events_path
