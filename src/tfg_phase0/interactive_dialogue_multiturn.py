"""Diálogo adaptativo de hasta tres preguntas, sin ground truth ni inferencia visual."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .interactive_dialogue import (
    DialoguePolicyConfig,
    F3EvidenceIndex,
    InteractiveDialogueError,
    QuestionIntent,
    TextDialogueAdapter,
    _canonical_json_bytes,
    _sha256,
    _utc_now,
    _validate_ranking_document,
    clarification_from_answer,
    cluster_ranked_candidates,
    compare_rankings,
    select_question_intent,
    validate_controlled_rewrite,
    validate_question_redaction,
)


CONTRACT_VERSION_V2 = "interactive-dialogue-session-v2"
QUERY_POLICY_VERSION = "literal-clarifications-newest-first-300-v1"
STOP_REASONS = {
    "max_questions_reached", "no_discriminative_question", "repeated_question",
    "human_requested_stop", "unresolvable_contradiction",
    "insufficient_supported_evidence", "runtime_failure",
}
STOP_ANSWERS = {"terminar", "finalizar", "parar", "salir", "no quiero continuar"}
UNKNOWN_PREFIXES = (
    "no sé", "no se", "no puedo comprobarlo", "no puedo verlo", "no lo puedo ver",
    "no estoy seguro", "no estoy segura", "no se distingue",
)
CORRECTION_STOPWORDS = {"un", "una", "o", "elemento", "lugar", "algún", "alguna", "identificable", "amplio"}


class MultiTurnRetriever(Protocol):
    gallery_id: str
    @property
    def metadata(self) -> Mapping[str, Any]: ...
    def retrieve_full(self, *, query_id: str, text: str, language: str) -> dict[str, Any]: ...


class VisualEvidenceProvider(Protocol):
    @property
    def metadata(self) -> Mapping[str, Any]: ...
    def inspect(self, *, query: str, ranking: Mapping[str, Any], budget: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class MultiTurnConfig:
    max_questions: int = 3
    text_token_budget: int = 300
    policy: DialoguePolicyConfig = DialoguePolicyConfig()

    def __post_init__(self) -> None:
        if self.max_questions not in {1, 2, 3}:
            raise InteractiveDialogueError("max_questions debe estar entre 1 y 3")
        if self.text_token_budget != 300:
            raise InteractiveDialogueError("el presupuesto CT2L debe ser 300 tokens")


def _normalize(text: str) -> str:
    return " ".join(text.casefold().strip().rstrip(".!?¡¿").split())


def interpret_answer(answer: str, intent: QuestionIntent, previous_claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    literal = answer.strip()
    normalized = _normalize(literal)
    if not literal:
        raise InteractiveDialogueError("respuesta vacía")
    if normalized in STOP_ANSWERS or normalized.startswith(("quiero terminar", "prefiero parar")):
        return {"kind": "stop", "informative": False, "polarity": None, "clarification": None, "correction": None, "conflict": None}

    correction = None
    if normalized.startswith(("en realidad", "me corrijo", "corrijo")):
        answer_tokens = set(re.findall(r"[a-záéíóúüñ]+", normalized)) - CORRECTION_STOPWORDS
        matches = []
        for claim in reversed(previous_claims):
            label_tokens = set(re.findall(r"[a-záéíóúüñ]+", claim["label"].casefold())) - CORRECTION_STOPWORDS
            if label_tokens and label_tokens <= answer_tokens:
                matches.append(claim)
        if len(matches) == 1:
            claim = matches[0]
            polarity = "negative" if re.search(r"\b(no|ningun[ao]?)\b", normalized) else "positive" if re.search(r"\b(sí|si|veo|hay)\b", normalized) else None
            if polarity is not None and polarity != claim["polarity"]:
                correction = {"claim_id": claim["claim_id"], "feature": claim["feature"], "label": claim["label"], "old_polarity": claim["polarity"], "new_polarity": polarity, "explicit": True}
        if correction is None:
            return {"kind": "contradictory", "informative": False, "polarity": None, "clarification": None, "correction": None, "conflict": "unresolvable_explicit_correction"}

    if correction is not None:
        polarity, kind = correction["new_polarity"], "correction"
    elif normalized.startswith(UNKNOWN_PREFIXES) or normalized in {"desconocido", "quizá", "tal vez"}:
        kind = "unobservable" if normalized.startswith(("no puedo", "no se distingue")) else "unknown"
        return {"kind": kind, "informative": False, "polarity": None, "clarification": None, "correction": correction, "conflict": None}
    elif normalized in {"sí", "si"}:
        polarity, kind = "positive", "affirmation"
    elif normalized == "no":
        polarity, kind = "negative", "negation"
    elif re.search(r"\b(sí|si)\b", normalized) and re.search(r"\b(no|quizá|tal vez)\b", normalized):
        return {"kind": "ambiguous", "informative": False, "polarity": None, "clarification": None, "correction": correction, "conflict": None}
    elif normalized.startswith(("sí ", "si ", "veo ", "hay ")):
        polarity, kind = "positive", "partially_informative"
    elif normalized.startswith(("no ", "ningún ", "ninguna ")):
        polarity, kind = "negative", "partially_informative"
    else:
        return {"kind": "ambiguous", "informative": False, "polarity": None, "clarification": None, "correction": correction, "conflict": None}
    target = intent if correction is None else QuestionIntent("correction", correction["feature"], correction["label"], (), (), (), "", ())
    clarification = clarification_from_answer("Sí" if polarity == "positive" else "No", target)
    return {"kind": "correction" if correction else kind, "informative": True, "polarity": polarity, "clarification": clarification, "correction": correction, "conflict": None}


def build_canonical_query(original: str, active_claims: Sequence[Mapping[str, Any]], retriever: Any, *, budget: int = 300) -> dict[str, Any]:
    fragments = [
        {"kind": "clarification", "claim_id": row["claim_id"], "text": row["clarification"]}
        for row in reversed(active_claims) if row.get("active", True)
    ]
    fragments.append({"kind": "original", "claim_id": None, "text": original})
    included: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []

    def render(rows: Sequence[Mapping[str, Any]]) -> str:
        parts = []
        clarifications = [row["text"] for row in rows if row["kind"] == "clarification"]
        source = next((row["text"] for row in rows if row["kind"] == "original"), None)
        if clarifications:
            parts.append("[ACLARACIONES VALIDADAS]\n" + "\n".join(clarifications))
        if source:
            parts.append("[DESCRIPCIÓN ORIGINAL]\n" + source)
        return "\n".join(parts)

    count = getattr(retriever, "count_tokens", lambda value: None)
    for fragment in fragments:
        candidate = render([*included, fragment])
        measured = count(candidate)
        if measured is None:
            measured = len(candidate.split()) + 2
            method = "whitespace_fallback"
        else:
            method = "ct2l_tokenizer"
        if measured <= budget:
            included.append(fragment)
        elif fragment["kind"] == "original":
            words = fragment["text"].split()
            reduced = None
            while words:
                candidate_fragment = {**fragment, "text": " ".join(words), "reduced": True}
                candidate = render([*included, candidate_fragment])
                candidate_count = count(candidate)
                candidate_count = candidate_count if candidate_count is not None else len(candidate.split()) + 2
                if candidate_count <= budget:
                    reduced = candidate_fragment
                    break
                words.pop()
            if reduced is not None:
                included.append(reduced)
                omitted.append({**fragment, "reason": "token_budget", "omission": "original_suffix", "included_characters": len(reduced["text"])})
            else:
                omitted.append({**fragment, "reason": "token_budget"})
        else:
            omitted.append({**fragment, "reason": "token_budget"})
    text = render(included)
    token_count = count(text)
    method = "ct2l_tokenizer" if token_count is not None else "whitespace_fallback"
    token_count = token_count if token_count is not None else len(text.split()) + 2
    if not text or token_count > budget:
        raise InteractiveDialogueError("no se pudo construir una consulta CT2L dentro del presupuesto")
    return {"policy_version": QUERY_POLICY_VERSION, "text": text, "token_count": token_count, "token_count_method": method, "budget": budget, "included_fragments": included, "omitted_fragments": omitted, "is_complete_transcript": not omitted}


class MultiTurnDialogueOrchestrator:
    def __init__(self, *, retriever: MultiTurnRetriever, evidence: F3EvidenceIndex, config: MultiTurnConfig, text_adapter: TextDialogueAdapter | None = None, visual_provider: VisualEvidenceProvider | None = None):
        self.retriever = retriever
        self.evidence = evidence
        self.config = config
        self.text_adapter = text_adapter
        self.visual_provider = visual_provider
        if visual_provider is not None:
            raise InteractiveDialogueError("el proveedor VLM está reservado y no puede activarse en este BUILD")

    def start(self, *, session_label: str, description: str, language: str = "es") -> dict[str, Any]:
        if not session_label.strip() or not description.strip():
            raise InteractiveDialogueError("entrada inicial inválida")
        identity = {"label": session_label, "description": description, "language": language, "gallery": self.retriever.gallery_id, "max_questions": self.config.max_questions, "policy": self._policy()}
        session_id = "dialogue-session-v2-sha256-" + _sha256(identity)
        initial_query = build_canonical_query(description, (), self.retriever, budget=self.config.text_token_budget)
        ranking = self.retriever.retrieve_full(query_id=f"{session_id}-initial", text=initial_query["text"], language=language)
        _validate_ranking_document(ranking, self.retriever.gallery_id)
        events: list[dict[str, Any]] = []
        self._event(events, "session_started", {"description": description, "language": language})
        self._event(events, "retrieval_completed", {"turn_index": 0, "variant": "initial", "query_sha256": hashlib.sha256(initial_query["text"].encode()).hexdigest(), "ranking_sha256": _sha256(ranking)})
        session = {
            "schema_version": "1.0", "contract_version": CONTRACT_VERSION_V2, "session_id": session_id,
            "status": "awaiting_answer", "max_questions": self.config.max_questions, "questions_asked": 0,
            "gallery_id": self.retriever.gallery_id, "policy": self._policy(),
            "models": {"retrieval": dict(self.retriever.metadata), "text": dict(self.text_adapter.metadata) if self.text_adapter else None, "vlm": {"enabled": False, "adapter": None, "expected_model_id": "Qwen/Qwen3-VL-8B-Instruct", "expected_revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b", "evidence_states": ["supported", "contradicted", "unverifiable"], "calls": 0}},
            "inputs": {"description": {"text": description, "language": language, "source": "human_literal", "sha256": hashlib.sha256(description.encode()).hexdigest()}},
            "f3": {"dataset_id": self.evidence.dataset_id, "catalog_manifest_id": self.evidence.catalog_manifest_id, "catalog_manifest_sha256": self.evidence.catalog_manifest_sha256, "source_hashes": self.evidence.source_hashes, "absence_semantics": "unknown_not_contradicted", "visibility_inferred": False},
            "initial_query": initial_query, "initial_ranking": ranking, "current_ranking": ranking, "claims": [], "turns": [], "stop_reason": None,
            "events": events, "limitations": ["infrastructure_validation_only", "no_ground_truth_in_operational_contract", "ct2l_scores_not_probabilities", "f3_association_not_visibility", "no_vlm", "maximum_three_questions"],
        }
        self._select_next(session)
        validate_multiturn_session(session)
        return session

    def answer(self, session: Mapping[str, Any], answer: str) -> dict[str, Any]:
        validate_multiturn_session(session)
        if session["status"] != "awaiting_answer" or not session["turns"] or session["turns"][-1]["answer"] is not None:
            raise InteractiveDialogueError("la sesión no admite respuesta")
        result = json.loads(json.dumps(session, ensure_ascii=False))
        turn = result["turns"][-1]
        q = turn["question"]
        intent = QuestionIntent(q["intent_id"], q["feature"], q["label"], tuple(q["supported_hypothesis_ids"]), tuple(q["unknown_hypothesis_ids"]), tuple(q["evidence_refs"]), q["deterministic_question"], ())
        interpreted = interpret_answer(answer, intent, result["claims"])
        turn["answer"] = {"literal": answer, "sha256": hashlib.sha256(answer.encode()).hexdigest(), "interpretation": interpreted}
        self._event(result["events"], "human_answer_recorded", {"turn_index": turn["index"], "answer": answer, "answer_sha256": turn["answer"]["sha256"], "kind": interpreted["kind"]})
        if interpreted["kind"] == "stop":
            return self._stop(result, turn, "human_requested_stop")
        if interpreted["conflict"]:
            return self._stop(result, turn, "unresolvable_contradiction")
        if interpreted["correction"]:
            corrected = next(row for row in result["claims"] if row["claim_id"] == interpreted["correction"]["claim_id"])
            corrected["active"] = False
            turn["conflict_resolution"] = {"policy": "explicit_correction_supersedes_prior_claim", **interpreted["correction"]}
        if interpreted["informative"]:
            feature = interpreted["correction"]["feature"] if interpreted["correction"] else intent.feature
            label = interpreted["correction"]["label"] if interpreted["correction"] else intent.label
            claim = {"claim_id": f"claim-{turn['index']:03d}", "turn_index": turn["index"], "feature": feature, "label": label, "polarity": interpreted["polarity"], "clarification": interpreted["clarification"], "answer_literal": answer, "active": True, "supersedes": interpreted["correction"]["claim_id"] if interpreted["correction"] else None}
            result["claims"].append(claim)
            query = build_canonical_query(result["inputs"]["description"]["text"], result["claims"], self.retriever, budget=self.config.text_token_budget)
            turn["canonical_query"] = query
            updates = [{"variant": "literal_concatenation", "status": "accepted", "text": query["text"], "canonical_for_next_turn": True, "failure_reason": None}]
            if self.config.policy.enable_controlled_rewrite and self.text_adapter is not None:
                before = len(self.text_adapter.metadata.get("calls", []))
                try:
                    proposal = self.text_adapter.rewrite_query(result["inputs"]["description"]["text"], interpreted["clarification"])
                    valid, reason = validate_controlled_rewrite(result["inputs"]["description"]["text"], interpreted["clarification"], proposal)
                    call = list(self.text_adapter.metadata.get("calls", []))[before:]
                    runtime_audit = call[-1] if call else None
                    updates.append({"variant": "controlled_rewrite", "status": "accepted" if valid else "rejected", "text": proposal if valid else None, "raw_proposal": proposal, "canonical_for_next_turn": False, "failure_reason": reason, "audit": {"prompt_effective": runtime_audit.get("prompt_effective") if runtime_audit else None, "raw_output": proposal, "validated_output": proposal if valid else None, "accepted": valid, "rejection_reason": reason, "fallback": None if valid else "omit_experimental_variant", "generation": runtime_audit}})
                except Exception as error:
                    failure = f"runtime_error:{type(error).__name__}"
                    updates.append({"variant": "controlled_rewrite", "status": "failed", "text": None, "raw_proposal": None, "canonical_for_next_turn": False, "failure_reason": failure, "audit": {"prompt_effective": None, "raw_output": None, "validated_output": None, "accepted": False, "rejection_reason": failure, "fallback": "omit_experimental_variant", "generation": None}})
            turn["query_updates"] = updates
            try:
                ranking = self.retriever.retrieve_full(query_id=f"{result['session_id']}-turn-{turn['index']:03d}-literal", text=query["text"], language=result["inputs"]["description"]["language"])
                _validate_ranking_document(ranking, self.retriever.gallery_id)
            except Exception as error:
                turn["runtime_error"] = type(error).__name__
                return self._stop(result, turn, "runtime_failure")
            turn["posterior_ranking"] = ranking
            turn["comparison"] = compare_rankings(turn["input_ranking"], ranking)
            result["current_ranking"] = ranking
            self._event(result["events"], "retrieval_completed", {"turn_index": turn["index"], "variant": "literal_concatenation", "query_sha256": hashlib.sha256(query["text"].encode()).hexdigest(), "ranking_sha256": _sha256(ranking)})
        else:
            turn["continuation_reason"] = "non_informative_answer_try_independent_intent"
        if result["questions_asked"] >= result["max_questions"]:
            return self._stop(result, turn, "max_questions_reached")
        self._select_next(result)
        validate_multiturn_session(result)
        return result

    def _select_next(self, session: dict[str, Any]) -> None:
        hypotheses = cluster_ranked_candidates(session["current_ranking"], self.evidence, reserve_size=self.config.policy.reserve_size, radius_m=self.config.policy.cluster_radius_m)
        used = {turn["question"]["feature"] for turn in session["turns"]}
        blocked = used | {turn["question"]["feature"] for turn in session["turns"] if turn.get("answer", {}).get("interpretation", {}).get("kind") in {"unknown", "unobservable"}}
        description = session["inputs"]["description"]["text"] + " " + " ".join(row["clarification"] for row in session["claims"] if row["active"])
        intent = select_question_intent(description, hypotheses, self.config.policy)
        if intent is not None and intent.feature in blocked:
            # Deterministic family exclusion: find the best remaining feature by marking used families as mentioned.
            description += " " + " ".join(value for feature in blocked for value in self._feature_terms(feature))
            intent = select_question_intent(description, hypotheses, self.config.policy)
        if intent is None:
            reason = "insufficient_supported_evidence" if len(hypotheses) < self.config.policy.minimum_hypotheses else "no_discriminative_question"
            self._stop(session, session["turns"][-1] if session["turns"] else None, reason)
            return
        if intent.feature in used:
            self._stop(session, session["turns"][-1] if session["turns"] else None, "repeated_question")
            return
        question, source, fallback, audit = intent.deterministic_question, "deterministic_template", None, None
        if self.config.policy.allow_qwen_question and self.text_adapter is not None:
            before = len(self.text_adapter.metadata.get("calls", []))
            try:
                proposal = self.text_adapter.redact_question(intent)
                valid, fallback = validate_question_redaction(proposal, intent)
                calls = list(self.text_adapter.metadata.get("calls", []))[before:]
                audit = {"raw_output": proposal, "validated_output": " ".join(proposal.split()) if valid else None, "accepted": valid, "rejection_reason": fallback, "fallback": None if valid else "deterministic_template", "runtime": calls[-1] if calls else None}
                if valid:
                    question, source = " ".join(proposal.split()), "qwen_validated"
            except Exception as error:
                fallback = f"runtime_error:{type(error).__name__}"
                audit = {"raw_output": None, "validated_output": None, "accepted": False, "rejection_reason": fallback, "fallback": "deterministic_template", "runtime": None}
        turn = {"index": len(session["turns"]) + 1, "input_ranking": json.loads(json.dumps(session["current_ranking"])), "input_ranking_sha256": _sha256(session["current_ranking"]), "hypotheses": [self._hypothesis(row) for row in hypotheses], "f3_evidence_considered": list(intent.evidence_refs), "question": {"intent_id": intent.intent_id, "intent_family": intent.feature, "feature": intent.feature, "label": intent.label, "supported_hypothesis_ids": list(intent.supported_hypothesis_ids), "unknown_hypothesis_ids": list(intent.unknown_hypothesis_ids), "evidence_refs": list(intent.evidence_refs), "deterministic_question": intent.deterministic_question, "final_question": question, "source": source, "fallback_reason": fallback, "qwen_audit": audit, "absence_used_as_contradiction": False}, "answer": None, "conflict_resolution": None, "canonical_query": None, "query_updates": [], "posterior_ranking": None, "comparison": None, "continuation_reason": None, "runtime_error": None}
        session["turns"].append(turn)
        session["questions_asked"] += 1
        session["status"], session["stop_reason"] = "awaiting_answer", None
        if self.text_adapter is not None:
            session["models"]["text"] = dict(self.text_adapter.metadata)
        self._event(session["events"], "question_selected", {"turn_index": turn["index"], "intent_id": intent.intent_id, "intent_family": intent.feature, "input_ranking_sha256": turn["input_ranking_sha256"], "question": question, "source": source, "fallback_reason": fallback, "qwen_audit_sha256": _sha256(audit) if audit is not None else None})

    @staticmethod
    def _feature_terms(feature: str) -> tuple[str, ...]:
        from .interactive_dialogue import FEATURE_TERMS
        return tuple(sorted(FEATURE_TERMS.get(feature, ())))

    @staticmethod
    def _hypothesis(value: Any) -> dict[str, Any]:
        return {"hypothesis_id": value.hypothesis_id, "candidate_ids": list(value.candidate_ids), "best_rank": value.best_rank, "centroid_epsg25830": {"easting_m": value.centroid_easting_m, "northing_m": value.centroid_northing_m}, "features": [{"feature": feature.feature, "label": feature.label, "state": "supported", "source_refs": list(feature.source_refs), "visibility_inferred": False, "ambiguous": feature.ambiguous} for feature in value.features]}

    def _policy(self) -> dict[str, Any]:
        p = self.config.policy
        return {"version": "deterministic-positive-f3-adaptive-v2", "query_policy_version": QUERY_POLICY_VERSION, "max_questions": self.config.max_questions, "reserve_size": p.reserve_size, "cluster_radius_m": p.cluster_radius_m, "minimum_hypotheses": p.minimum_hypotheses, "minimum_supported_hypotheses": p.minimum_supported_hypotheses, "maximum_supported_fraction": p.maximum_supported_fraction, "allow_qwen_question": p.allow_qwen_question, "enable_controlled_rewrite": p.enable_controlled_rewrite, "canonical_variant": "literal_concatenation", "absence_semantics": "unknown_not_contradicted", "scores_are_probabilities": False}

    def _stop(self, session: dict[str, Any], turn: dict[str, Any] | None, reason: str) -> dict[str, Any]:
        if reason not in STOP_REASONS:
            raise InteractiveDialogueError("razón de parada no soportada")
        session["status"], session["stop_reason"] = "completed", reason
        if turn is not None:
            turn["continuation_reason"] = reason
        if self.text_adapter is not None:
            session["models"]["text"] = dict(self.text_adapter.metadata)
        session["models"]["retrieval"] = dict(self.retriever.metadata)
        self._event(session["events"], "session_stopped", {"reason": reason, "questions_asked": session["questions_asked"]})
        return session

    @staticmethod
    def _event(events: list[dict[str, Any]], kind: str, payload: Mapping[str, Any]) -> None:
        previous = events[-1]["event_hash"] if events else None
        preimage = {"sequence": len(events), "kind": kind, "payload": dict(payload), "previous_event_hash": previous, "recorded_at_utc": _utc_now()}
        events.append({**preimage, "event_hash": "dialogue-event-sha256-" + _sha256(preimage)})


def validate_multiturn_session(session: Mapping[str, Any]) -> None:
    forbidden = {"ground_truth", "ground_truth_candidate", "target_candidate_id", "reference_coordinate", "correct_candidate", "gt"}
    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            if forbidden & set(value):
                raise InteractiveDialogueError("el contrato operativo no admite ground truth")
            for nested in value.values(): visit(nested)
        elif isinstance(value, list):
            for nested in value: visit(nested)
    visit(session)
    required = {"schema_version", "contract_version", "session_id", "status", "max_questions", "questions_asked", "gallery_id", "policy", "models", "inputs", "f3", "initial_query", "initial_ranking", "current_ranking", "claims", "turns", "stop_reason", "events", "limitations"}
    if set(session) != required or session.get("contract_version") != CONTRACT_VERSION_V2 or session.get("schema_version") != "1.0":
        raise InteractiveDialogueError("contrato multivuelta incompatible")
    if session["max_questions"] not in {1, 2, 3} or session["questions_asked"] != len(session["turns"]) or len(session["turns"]) > session["max_questions"]:
        raise InteractiveDialogueError("contador de preguntas inválido")
    if session["status"] not in {"awaiting_answer", "completed"} or (session["status"] == "completed") != (session["stop_reason"] is not None):
        raise InteractiveDialogueError("estado multivuelta incoherente")
    if session["status"] == "awaiting_answer" and (not session["turns"] or session["turns"][-1]["answer"] is not None):
        raise InteractiveDialogueError("sesión en espera sin pregunta pendiente")
    _validate_ranking_document(session["initial_ranking"], session["gallery_id"])
    if session["initial_query"]["token_count"] > 300:
        raise InteractiveDialogueError("consulta inicial supera 300 tokens")
    _validate_ranking_document(session["current_ranking"], session["gallery_id"])
    universe = {row["candidate_id"] for row in session["initial_ranking"]["results"]}
    families = []
    expected_input = session["initial_ranking"]
    for index, turn in enumerate(session["turns"], 1):
        if turn["index"] != index or turn["input_ranking"] != expected_input or turn["input_ranking_sha256"] != _sha256(turn["input_ranking"]):
            raise InteractiveDialogueError("ranking de entrada de turno inválido")
        family = turn["question"]["intent_family"]
        if family in families: raise InteractiveDialogueError("intención semántica repetida")
        families.append(family)
        if turn["question"]["absence_used_as_contradiction"] is not False: raise InteractiveDialogueError("ausencia F3 usada como contradicción")
        posterior = turn["posterior_ranking"]
        if turn["answer"] is not None:
            literal = turn["answer"].get("literal")
            if not isinstance(literal, str) or turn["answer"].get("sha256") != hashlib.sha256(literal.encode()).hexdigest():
                raise InteractiveDialogueError("respuesta literal alterada")
        if posterior is not None:
            _validate_ranking_document(posterior, session["gallery_id"])
            if {row["candidate_id"] for row in posterior["results"]} != universe: raise InteractiveDialogueError("recuperación posterior no global")
            accepted = [row for row in turn["query_updates"] if row["variant"] == "literal_concatenation" and row["status"] == "accepted"]
            if len(accepted) != 1 or not accepted[0]["canonical_for_next_turn"]: raise InteractiveDialogueError("variante canónica inválida")
            if turn["canonical_query"]["token_count"] > 300: raise InteractiveDialogueError("consulta supera 300 tokens")
            expected_input = posterior
    if session["current_ranking"] != expected_input: raise InteractiveDialogueError("ranking actual no corresponde al último turno")
    previous = None
    for sequence, event in enumerate(session["events"]):
        if event["sequence"] != sequence or event["previous_event_hash"] != previous: raise InteractiveDialogueError("cadena de eventos inválida")
        preimage = {key: event[key] for key in ("sequence", "kind", "payload", "previous_event_hash", "recorded_at_utc")}
        previous = "dialogue-event-sha256-" + _sha256(preimage)
        if event["event_hash"] != previous: raise InteractiveDialogueError("hash de evento inválido")
    retrieval_events = [event for event in session["events"] if event["kind"] == "retrieval_completed"]
    expected_retrievals = [(0, "initial", session["initial_query"]["text"], session["initial_ranking"])]
    expected_retrievals.extend((turn["index"], "literal_concatenation", turn["canonical_query"]["text"], turn["posterior_ranking"]) for turn in session["turns"] if turn["posterior_ranking"] is not None)
    if len(retrieval_events) != len(expected_retrievals):
        raise InteractiveDialogueError("eventos de recuperación incompletos")
    for event, (turn_index, variant, query, ranking) in zip(retrieval_events, expected_retrievals, strict=True):
        payload = event["payload"]
        if payload.get("turn_index") != turn_index or payload.get("variant") != variant or payload.get("query_sha256") != hashlib.sha256(query.encode()).hexdigest() or payload.get("ranking_sha256") != _sha256(ranking):
            raise InteractiveDialogueError("evento de recuperación no corresponde al ranking")
    question_events = [event for event in session["events"] if event["kind"] == "question_selected"]
    if len(question_events) != len(session["turns"]):
        raise InteractiveDialogueError("eventos de pregunta incompletos")
    for event, turn in zip(question_events, session["turns"], strict=True):
        question = turn["question"]
        payload = event["payload"]
        expected = {"turn_index": turn["index"], "intent_id": question["intent_id"], "intent_family": question["intent_family"], "input_ranking_sha256": turn["input_ranking_sha256"], "question": question["final_question"], "source": question["source"], "fallback_reason": question["fallback_reason"], "qwen_audit_sha256": _sha256(question["qwen_audit"]) if question["qwen_audit"] is not None else None}
        if payload != expected:
            raise InteractiveDialogueError("evento de pregunta no corresponde al turno")
    answer_events = [event for event in session["events"] if event["kind"] == "human_answer_recorded"]
    answered_turns = [turn for turn in session["turns"] if turn["answer"] is not None]
    if len(answer_events) != len(answered_turns):
        raise InteractiveDialogueError("eventos de respuesta incompletos")
    for event, turn in zip(answer_events, answered_turns, strict=True):
        answer = turn["answer"]
        expected = {"turn_index": turn["index"], "answer": answer["literal"], "answer_sha256": answer["sha256"], "kind": answer["interpretation"]["kind"]}
        if event["payload"] != expected:
            raise InteractiveDialogueError("evento de respuesta no corresponde al turno")
    claims_by_id = {claim["claim_id"]: claim for claim in session["claims"]}
    if len(claims_by_id) != len(session["claims"]):
        raise InteractiveDialogueError("claims duplicados")
    for claim in session["claims"]:
        turn = session["turns"][claim["turn_index"] - 1]
        interpretation = turn["answer"]["interpretation"] if turn["answer"] else None
        if not interpretation or not interpretation["informative"] or claim["clarification"] != interpretation["clarification"] or claim["polarity"] != interpretation["polarity"] or claim["answer_literal"] != turn["answer"]["literal"]:
            raise InteractiveDialogueError("claim no corresponde a su respuesta")
        if claim["supersedes"] is None:
            question = turn["question"]
            if claim["feature"] != question["feature"] or claim["label"] != question["label"]:
                raise InteractiveDialogueError("claim no corresponde a la intención")
        else:
            previous_claim = claims_by_id.get(claim["supersedes"])
            resolution = turn["conflict_resolution"]
            if previous_claim is None or previous_claim["active"] is not False or claim["feature"] != previous_claim["feature"] or claim["label"] != previous_claim["label"] or not resolution or resolution.get("claim_id") != previous_claim["claim_id"]:
                raise InteractiveDialogueError("corrección de claim incoherente")
    stopped = [event for event in session["events"] if event["kind"] == "session_stopped"]
    if session["status"] == "completed":
        if len(stopped) != 1 or stopped[0]["payload"] != {"reason": session["stop_reason"], "questions_asked": session["questions_asked"]}:
            raise InteractiveDialogueError("evento de parada incoherente")
    elif stopped:
        raise InteractiveDialogueError("sesión activa contiene evento de parada")
    if session["models"]["vlm"]["enabled"] is not False or session["models"]["vlm"]["calls"] != 0:
        raise InteractiveDialogueError("VLM no permitido en este contrato")


def write_multiturn_session(session: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    validate_multiturn_session(session)
    output_dir.mkdir(parents=True, exist_ok=False)
    session_path, events_path = output_dir / "session.json", output_dir / "events.jsonl"
    session_path.write_bytes(_canonical_json_bytes(session, newline=True))
    events_path.write_bytes(b"".join(_canonical_json_bytes(row, newline=True) for row in session["events"]))
    return session_path, events_path
