"""Controlador CPU durable del bucle LLM -> CT2L -> Mapillary -> DQ-Pilot."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from research.dq_pilot_translation_v1 import TranslationContractError, validate_translation

STATES = (
    "INITIAL_DESCRIPTION", "LLM_INTERPRETATION", "CT2L_RETRIEVAL",
    "MAPILLARY_PANEL", "DQ_GENERATION", "QUESTION_VALIDATION",
    "SPANISH_TRANSLATION", "AWAITING_USER", "ACCUMULATE_ANSWER",
    "AWAITING_PANEL_REVIEW", "AWAITING_QUESTION_REVIEW",
    "AWAITING_TRANSLATION_REVIEW",
    "CHECK_CONTINUATION", "COMPLETED", "FAILED",
)
MAX_QUESTIONS = 3


class IterativeDialogueError(ValueError):
    pass


class InterpreterPort(Protocol):
    def interpret(self, *, round_index: int, original_description: str, accumulated_description: str, dialogue_history: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]: ...


class RetrieverPort(Protocol):
    def retrieve(self, *, round_index: int, interpreted_text: str) -> Mapping[str, Any]: ...


class PanelPort(Protocol):
    def build(self, *, round_index: int, ranking: Mapping[str, Any], reserve: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]: ...


class QuestionerPort(Protocol):
    @property
    def identity(self) -> Mapping[str, Any]: ...
    def generate(self, *, session_id: str, query_id: str, round_index: int, panel: Mapping[str, Any], original_description: str, dialogue_history: Sequence[Mapping[str, Any]], operation_root: Path) -> Mapping[str, Any]: ...


class ValidatorPort(Protocol):
    @property
    def identity(self) -> Mapping[str, Any]: ...
    def validate(self, *, session_id: str, query_id: str, round_index: int, panel: Mapping[str, Any], generation: Mapping[str, Any], accumulated_description: str, dialogue_history: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]: ...


class TranslatorPort(Protocol):
    @property
    def identity(self) -> Mapping[str, Any]: ...
    def translate(self, *, round_index: int, question: str) -> Mapping[str, Any]: ...


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    payload = canonical(document) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise IterativeDialogueError(f"artefacto existente divergente: {path}")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def accumulated_description(original: str, turns: Sequence[Mapping[str, Any]]) -> str:
    parts = [original]
    for turn in turns:
        answer = turn.get("answer")
        if answer is not None:
            parts.append(f"Respuesta {turn['index']}: {answer['literal']}")
    return "\n".join(parts)


def dialogue_history(turns: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "index": turn["index"],
            "question_original": turn["question_original"],
            "question_es": turn["question_es"],
            "answer_literal": turn["answer"]["literal"] if turn.get("answer") else None,
        }
        for turn in turns
    ]


def validate_ranking(ranking: Mapping[str, Any]) -> None:
    rows = ranking.get("results", [])
    if not rows or [row.get("rank") for row in rows] != list(range(1, len(rows) + 1)):
        raise IterativeDialogueError("ranking CT2L inválido")
    ids = [row.get("candidate_id") for row in rows]
    if len(set(ids)) != len(ids):
        raise IterativeDialogueError("ranking CT2L contiene candidatos duplicados")
    scores = [row.get("cosine_similarity") for row in rows]
    if any(not isinstance(score, (int, float)) for score in scores) or any(scores[index] < scores[index + 1] for index in range(len(scores) - 1)):
        raise IterativeDialogueError("scores CT2L inválidos")


def retrieval_evidence(state, interpretation, ranking, *, top_n):
    """Registro y reserva comunes a la recuperación síncrona y supervisada."""
    validate_ranking(ranking)
    index = state["round_index"]
    reserve = {"schema_version": "1.0", "round_index": index, "step": "top-n-reserve",
               "contract_version": "dq-pilot12-top-n-reserve-v1", "source_ranking_sha256": digest(ranking),
               "top_n": top_n, "results": ranking["results"][:top_n]}
    prefix = f"rounds/round-{index}"
    record = {
        "round_index": index, "source_answer_count": sum(bool(turn.get("answer")) for turn in state["turns"]),
        "accumulated_description": state["accumulated_description"],
        "accumulated_description_sha256": digest_text(state["accumulated_description"]),
        "interpretation_ref": f"{prefix}/llm-interpretation.json", "interpretation_sha256": digest(interpretation),
        "ranking_ref": f"{prefix}/ct2l-ranking.json", "ranking_sha256": digest(ranking),
        "reserve_ref": f"{prefix}/top-n-reserve.json", "reserve_sha256": digest(reserve),
        "panel_ref": None, "generation_ref": None, "validation_ref": None, "translation_ref": None,
    }
    return reserve, record


class IterativeRunStore:
    def __init__(self, root: Path, *, on_transition=None):
        self.root = root
        self.state_path = root / "state.json"
        self.on_transition = on_transition

    @classmethod
    def prepare(cls, root: Path, *, session_id: str, query_id: str, original_description: str, top_n: int, identities: Mapping[str, Any]):
        if root.exists():
            raise IterativeDialogueError("run ya existe")
        root.mkdir(parents=True)
        (root / "rounds").mkdir()
        configuration = {
            "schema_version": "1.0",
            "contract_version": "dq-pilot12-iterative-configuration-v1",
            "session_id": session_id,
            "query_id": query_id,
            "top_n": top_n,
            "maximum_questions": MAX_QUESTIONS,
            "original_description": original_description,
            "original_description_sha256": digest_text(original_description),
            "identities": dict(identities),
            "ground_truth_permitted": False,
            "h38_h61_permitted": False,
            "synthetic_answers_permitted": False,
        }
        atomic_json(root / "configuration.json", configuration)
        state = {
            "schema_version": "1.0",
            "contract_version": "dq-pilot12-iterative-state-v1",
            "session_id": session_id,
            "query_id": query_id,
            "controller_state": "INITIAL_DESCRIPTION",
            "round_index": 0,
            "questions_asked": 0,
            "original_description": original_description,
            "accumulated_description": original_description,
            "turns": [],
            "rounds": [],
            "pending_question": None,
            "pending_panel": None,
            "pending_translation": None,
            "stop_reason": None,
            "failure": None,
            "generation": 0,
            "configuration_sha256": hashlib.sha256((root / "configuration.json").read_bytes()).hexdigest(),
        }
        store = cls(root)
        store.write_state(state)
        return store

    def load_state(self) -> dict[str, Any]:
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if value.get("controller_state") not in STATES:
            raise IterativeDialogueError("estado de controlador inválido")
        if value.get("questions_asked") != len(value.get("turns", [])) or value["questions_asked"] > MAX_QUESTIONS:
            raise IterativeDialogueError("conteo de preguntas inválido")
        return value

    def write_state(self, state: Mapping[str, Any]) -> None:
        temporary = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.tmp")
        payload = canonical(state) + b"\n"
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.state_path)

    def transition(self, state: dict[str, Any], controller_state: str) -> None:
        if controller_state not in STATES:
            raise IterativeDialogueError("transición a estado desconocido")
        state["controller_state"] = controller_state
        state["generation"] += 1
        self.write_state(state)
        if self.on_transition is not None:
            self.on_transition(state)

    def artifact(self, round_index: int, step: str, producer) -> tuple[dict[str, Any], bool]:
        path = self.root / "rounds" / f"round-{round_index}" / f"{step}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), True
        document = dict(producer())
        document.update({"schema_version": "1.0", "round_index": round_index, "step": step})
        atomic_json(path, document)
        return document, False


class IterativeDialogueController:
    def __init__(self, *, interpreter: InterpreterPort, retriever: RetrieverPort, panel: PanelPort, questioner: QuestionerPort, validator: ValidatorPort, translator: TranslatorPort, top_n: int):
        self.interpreter = interpreter
        self.retriever = retriever
        self.panel = panel
        self.questioner = questioner
        self.validator = validator
        self.translator = translator
        self.top_n = top_n

    @staticmethod
    def _validate_public_generation(generation: Mapping[str, Any]) -> None:
        forbidden = {"raw_output", "reasoning_internal", "think", "private_reasoning"}
        if forbidden & set(generation):
            raise IterativeDialogueError("generación pública filtra raw/think")
        if generation.get("reasoning_public") is not False or generation.get("private_output_retained") is not True:
            raise IterativeDialogueError("generación pública no acredita frontera privada")

    def _translate_and_present(self, store: IterativeRunStore, state: dict[str, Any], *, round_index: int, panel: Mapping[str, Any], question: str, round_record: dict[str, Any]) -> dict[str, Any]:
        store.transition(state, "SPANISH_TRANSLATION")
        try:
            translation, _ = store.artifact(round_index, "spanish-translation", lambda: self.translator.translate(round_index=round_index, question=question))
            translation = validate_translation(translation, round_index=round_index, source_question=question, translator_identity=self.translator.identity)
        except (TranslationContractError, IterativeDialogueError) as error:
            state["failure"] = {"type": type(error).__name__, "message": str(error)[:1000], "round_index": round_index, "component": "translator", "question_presented": False}
            state["stop_reason"] = "translation_rejected_before_user_presentation"
            state["pending_question"] = None
            store.transition(state, "CHECK_CONTINUATION")
            store.transition(state, "COMPLETED")
            return state
        round_record["translation_ref"] = f"rounds/round-{round_index}/spanish-translation.json"
        if translation["validation"]["semantic"] == "pending_human_review" and self.translator.identity.get("cpu_fixture_auto_review") is not True:
            state["pending_translation"] = {"round_index": round_index, "source_question_sha256": translation["source_question_sha256"], "translated_question_sha256": translation["translated_question_sha256"], "translation_sha256": digest(translation)}
            store.transition(state, "AWAITING_TRANSLATION_REVIEW")
            return state
        return self._present_translation(store, state, round_index=round_index, panel=panel, question=question, translation=translation)

    def _present_translation(self, store: IterativeRunStore, state: dict[str, Any], *, round_index: int, panel: Mapping[str, Any], question: str, translation: Mapping[str, Any]) -> dict[str, Any]:
        index = state["questions_asked"] + 1
        turn = {"index": index, "source_round": round_index, "panel_sha256": digest(panel), "question_original": question, "question_original_sha256": digest_text(question), "question_es": translation["translated_question"], "question_es_sha256": digest_text(translation["translated_question"]), "translator": dict(self.translator.identity), "answer": None}
        state["turns"].append(turn);state["questions_asked"] = index;state["pending_question"] = {"turn_index": index, "question_es": turn["question_es"], "question_original": turn["question_original"]}
        store.transition(state, "AWAITING_USER")
        return state

    def _continue_after_panel_review(
        self,
        store: IterativeRunStore,
        state: dict[str, Any],
        *,
        ranking: Mapping[str, Any],
        panel: Mapping[str, Any],
        round_record: dict[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        round_index = state["round_index"]
        store.transition(state, "DQ_GENERATION")
        operation_root = store.root / "rounds" / f"round-{round_index}" / "dq-operation"
        generation, _ = store.artifact(round_index, "dq-generation", lambda: self.questioner.generate(session_id=state["session_id"], query_id=state["query_id"], round_index=round_index, panel=panel, original_description=state["original_description"], dialogue_history=history, operation_root=operation_root))
        self._validate_public_generation(generation)
        if generation.get("panel_sha256") != digest(panel) or generation.get("source_ranking_sha256") != digest(ranking):
            raise IterativeDialogueError("generación DQ no está ligada al panel/ranking actuales")
        round_record["generation_ref"] = f"rounds/round-{round_index}/dq-generation.json"
        store.transition(state, "QUESTION_VALIDATION")
        validation, _ = store.artifact(round_index, "question-validation", lambda: self.validator.validate(session_id=state["session_id"], query_id=state["query_id"], round_index=round_index, panel=panel, generation=generation, accumulated_description=state["accumulated_description"], dialogue_history=history))
        if validation.get("generation_sha256") != digest(generation) or validation.get("panel_sha256") != digest(panel):
            raise IterativeDialogueError("validación no está ligada a generación/panel actuales")
        round_record["validation_ref"] = f"rounds/round-{round_index}/question-validation.json"
        store.write_state(state)
        if validation.get("status") == "pending_review":
            state["pending_question"] = {"round_index": round_index, "generation_sha256": digest(generation), "panel_sha256": digest(panel), "question_original": validation.get("question"), "review_required": True}
            store.transition(state, "AWAITING_QUESTION_REVIEW")
            return state
        if validation.get("status") != "valid" or validation.get("question") != generation.get("question"):
            store.transition(state, "CHECK_CONTINUATION")
            state["stop_reason"] = "question_invalid_or_abstained"
            store.transition(state, "COMPLETED")
            return state

        return self._translate_and_present(store, state, round_index=round_index, panel=panel, question=validation["question"], round_record=round_record)

    def _run_round(self, store: IterativeRunStore, state: dict[str, Any], *, terminal_after_retrieval: str | None = None) -> dict[str, Any]:
        round_index = state["round_index"]
        history = dialogue_history(state["turns"])
        state["accumulated_description"] = accumulated_description(state["original_description"], state["turns"])
        store.transition(state, "LLM_INTERPRETATION")
        interpretation, _ = store.artifact(round_index, "llm-interpretation", lambda: self.interpreter.interpret(round_index=round_index, original_description=state["original_description"], accumulated_description=state["accumulated_description"], dialogue_history=history))
        if not isinstance(interpretation.get("text"), str) or not interpretation["text"]:
            raise IterativeDialogueError("interpretación LLM vacía")
        store.transition(state, "CT2L_RETRIEVAL")
        ranking, _ = store.artifact(round_index, "ct2l-ranking", lambda: self.retriever.retrieve(round_index=round_index, interpreted_text=interpretation["text"]))
        reserve_expected, round_record = retrieval_evidence(state, interpretation, ranking, top_n=self.top_n)
        reserve_doc, _ = store.artifact(round_index, "top-n-reserve", lambda: reserve_expected)
        if reserve_doc != reserve_expected:
            raise IterativeDialogueError("reserva divergente del ranking actualizado")
        reserve = reserve_doc["results"]
        existing = next((row for row in state["rounds"] if row["round_index"] == round_index), None)
        if existing is None:
            state["rounds"].append(round_record)
        else:
            existing.update(round_record)
            round_record = existing
        store.write_state(state)
        if terminal_after_retrieval is not None or state["questions_asked"] >= MAX_QUESTIONS:
            store.transition(state, "CHECK_CONTINUATION")
            state["stop_reason"] = terminal_after_retrieval or "max_questions_reached_after_final_retrieval"
            store.transition(state, "COMPLETED")
            return state

        store.transition(state, "MAPILLARY_PANEL")
        panel, _ = store.artifact(round_index, "mapillary-panel", lambda: self.panel.build(round_index=round_index, ranking=ranking, reserve=reserve))
        if panel.get("source_ranking_sha256") != digest(ranking) or panel.get("candidate_ids") != [row["candidate_id"] for row in panel.get("candidates", [])]:
            raise IterativeDialogueError("panel no está ligado al ranking actualizado")
        round_record["panel_ref"] = f"rounds/round-{round_index}/mapillary-panel.json"
        store.write_state(state)
        if panel.get("status") not in {"ready", "prepared_pending_review"}:
            store.transition(state, "CHECK_CONTINUATION")
            state["stop_reason"] = "insufficient_visual_evidence"
            store.transition(state, "COMPLETED")
            return state
        if panel.get("review_required") is True:
            state["pending_panel"] = {"round_index": round_index, "panel_sha256": digest(panel), "source_ranking_sha256": digest(ranking)}
            store.transition(state, "AWAITING_PANEL_REVIEW")
            return state
        return self._continue_after_panel_review(store, state, ranking=ranking, panel=panel, round_record=round_record, history=history)

    def start(self, store: IterativeRunStore) -> dict[str, Any]:
        state = store.load_state()
        if state["controller_state"] in {"AWAITING_USER", "AWAITING_PANEL_REVIEW", "AWAITING_QUESTION_REVIEW", "AWAITING_TRANSLATION_REVIEW", "COMPLETED", "FAILED"}:
            return state
        try:
            return self._run_round(store, state)
        except Exception as error:
            state["failure"] = {"type": type(error).__name__, "message": str(error)[:1000], "round_index": state["round_index"]}
            store.transition(state, "FAILED")
            raise

    def resume(self, store: IterativeRunStore) -> dict[str, Any]:
        state = store.load_state()
        if state["controller_state"] in {"AWAITING_USER", "AWAITING_PANEL_REVIEW", "AWAITING_QUESTION_REVIEW", "AWAITING_TRANSLATION_REVIEW", "COMPLETED", "FAILED"}:
            return state
        if state["controller_state"] == "INITIAL_DESCRIPTION":
            return self.start(store)
        if state["controller_state"] == "ACCUMULATE_ANSWER":
            turn = state["turns"][-1]
            path = store.root / "rounds" / f"round-{turn['index']}" / "human-answer.json"
            if not path.is_file():
                raise IterativeDialogueError("respuesta durable ausente durante resume")
            answer = json.loads(path.read_text(encoding="utf-8"))
            if answer.get("literal_sha256") != digest_text(answer.get("literal", "")) or answer.get("turn_index") != turn["index"]:
                raise IterativeDialogueError("respuesta durable corrupta durante resume")
            if turn.get("answer") is None:
                turn["answer"] = {"literal": answer["literal"], "sha256": answer["literal_sha256"], "human_attested": True, "synthetic": False, "user_requests_stop": answer.get("user_requests_stop") is True}
            state["pending_question"] = None
            state["round_index"] = turn["index"]
            state["accumulated_description"] = accumulated_description(state["original_description"], state["turns"])
            store.write_state(state)
            terminal = "human_requested_stop_after_updated_retrieval" if turn["answer"].get("user_requests_stop") else None
            return self._run_round(store, state, terminal_after_retrieval=terminal)
        return self._run_round(store, state)

    def apply_panel_review(self, store: IterativeRunStore, *, approved: bool, review: Mapping[str, Any]) -> dict[str, Any]:
        state = store.load_state()
        if state["controller_state"] != "AWAITING_PANEL_REVIEW" or state.get("pending_panel") is None:
            raise IterativeDialogueError("controlador no espera revisión de panel")
        round_index = state["round_index"]
        round_root = store.root / "rounds" / f"round-{round_index}"
        panel = json.loads((round_root / "mapillary-panel.json").read_text(encoding="utf-8"))
        ranking = json.loads((round_root / "ct2l-ranking.json").read_text(encoding="utf-8"))
        if review.get("panel_sha256") != digest(panel) or review.get("source_ranking_sha256") != digest(ranking) or review.get("ground_truth_used") is not False:
            raise IterativeDialogueError("revisión no corresponde al panel/ranking")
        review_doc = {"contract_version": "dq-pilot13-panel-review-v1", "approved": approved, **dict(review)}
        atomic_json(round_root / "panel-review.json", review_doc)
        state["pending_panel"] = None
        if not approved:
            state["stop_reason"] = "panel_rejected_by_independent_review"
            store.transition(state, "CHECK_CONTINUATION")
            store.transition(state, "COMPLETED")
            return state
        approved_panel = {**panel, "status": "ready", "review_required": False, "panel_review_sha256": digest(review_doc)}
        atomic_json(round_root / "mapillary-panel-approved.json", approved_panel)
        record = next(row for row in state["rounds"] if row["round_index"] == round_index)
        record["panel_ref"] = f"rounds/round-{round_index}/mapillary-panel-approved.json"
        record["panel_review_ref"] = f"rounds/round-{round_index}/panel-review.json"
        store.write_state(state)
        return self._continue_after_panel_review(store, state, ranking=ranking, panel=approved_panel, round_record=record, history=dialogue_history(state["turns"]))

    def apply_question_review(self, store: IterativeRunStore, *, approved: bool, review: Mapping[str, Any]) -> dict[str, Any]:
        state = store.load_state()
        if state["controller_state"] != "AWAITING_QUESTION_REVIEW" or state["pending_question"] is None:
            raise IterativeDialogueError("controlador no espera revisión de pregunta")
        round_index = state["round_index"]
        panel_path = store.root / "rounds" / f"round-{round_index}" / "mapillary-panel-approved.json"
        if not panel_path.is_file():
            panel_path = store.root / "rounds" / f"round-{round_index}" / "mapillary-panel.json"
        panel = json.loads(panel_path.read_text())
        generation = json.loads((store.root / "rounds" / f"round-{round_index}" / "dq-generation.json").read_text())
        if review.get("generation_sha256") != digest(generation) or review.get("panel_sha256") != digest(panel) or review.get("ground_truth_used") is not False:
            raise IterativeDialogueError("revisión no corresponde a generación/panel")
        review_doc = {"contract_version": "dq-pilot12-question-review-v1", "approved": approved, **dict(review)}
        atomic_json(store.root / "rounds" / f"round-{round_index}" / "question-review.json", review_doc)
        if not approved:
            state["pending_question"] = None
            state["stop_reason"] = "question_rejected_by_independent_review"
            store.transition(state, "CHECK_CONTINUATION")
            store.transition(state, "COMPLETED")
            return state
        validation_path = store.root / "rounds" / f"round-{round_index}" / "question-validation-approved.json"
        approved_validation = {"schema_version": "1.0", "contract_version": "dq-pilot12-question-validation-approved-v1", "round_index": round_index, "step": "question-validation-approved", "status": "valid", "question": generation["question"], "generation_sha256": digest(generation), "panel_sha256": digest(panel), "review_sha256": digest(review_doc), "automatic_approval": False}
        atomic_json(validation_path, approved_validation)
        history = dialogue_history(state["turns"])
        record = next(row for row in state["rounds"] if row["round_index"] == round_index)
        return self._translate_and_present(store, state, round_index=round_index, panel=panel, question=generation["question"], round_record=record)

    def apply_translation_review(self, store: IterativeRunStore, *, approved: bool, review: Mapping[str, Any]) -> dict[str, Any]:
        state=store.load_state()
        if state["controller_state"]!="AWAITING_TRANSLATION_REVIEW" or state.get("pending_translation") is None:raise IterativeDialogueError("controlador no espera revisión de traducción")
        round_index=state["round_index"];root=store.root/"rounds"/f"round-{round_index}";translation=json.loads((root/"spanish-translation.json").read_text());panel_path=root/"mapillary-panel-approved.json"
        if not panel_path.is_file():panel_path=root/"mapillary-panel.json"
        panel=json.loads(panel_path.read_text());pending=state["pending_translation"]
        expected={"translation_sha256":digest(translation),"source_question_sha256":translation["source_question_sha256"],"translated_question_sha256":translation["translated_question_sha256"],"ground_truth_used":False}
        if any(review.get(key)!=value for key,value in expected.items()):raise IterativeDialogueError("revisión de traducción no corresponde al artefacto")
        required_checks={"polarity_preserved","alternatives_preserved","spatial_relations_preserved","proper_names_preserved","uncertainty_preserved","discriminative_content_preserved","no_added_information","single_clear_question"}
        checks=review.get("checks",{})
        if set(checks)!=required_checks or any(type(value)is not bool for value in checks.values()):raise IterativeDialogueError("rúbrica de traducción incompleta")
        effective_approved=approved and all(checks.values());review_doc={"schema_version":"1.0","contract_version":"dq-pilot23-translation-review-v1","approved":effective_approved,**dict(review)};atomic_json(root/"translation-review.json",review_doc);state["pending_translation"]=None
        if not effective_approved:
            state["stop_reason"]="translation_rejected_before_user_presentation";store.transition(state,"CHECK_CONTINUATION");store.transition(state,"COMPLETED");return state
        return self._present_translation(store,state,round_index=round_index,panel=panel,question=translation["source_question"],translation=translation)

    def apply_pilot_translation_decision(self, store: IterativeRunStore, *, decision: str, review: Mapping[str, Any]) -> dict[str, Any]:
        state=store.load_state()
        if state["controller_state"]!="AWAITING_TRANSLATION_REVIEW" or state.get("pending_translation") is None:raise IterativeDialogueError("controlador no espera decisión piloto de traducción")
        if decision not in {"accept_for_this_technical_pilot","reject","unresolved"}:raise IterativeDialogueError("decisión piloto de traducción inválida")
        round_index=state["round_index"];root=store.root/"rounds"/f"round-{round_index}";translation=json.loads((root/"spanish-translation.json").read_text());panel_path=root/"mapillary-panel-approved.json"
        if not panel_path.is_file():panel_path=root/"mapillary-panel.json"
        panel=json.loads(panel_path.read_text());expected={"translation_sha256":digest(translation),"source_question_sha256":translation["source_question_sha256"],"translated_question_sha256":translation["translated_question_sha256"],"ground_truth_used":False}
        if any(review.get(key)!=value for key,value in expected.items()) or not isinstance(review.get("reviewer_declaration"),str) or not review["reviewer_declaration"].strip():raise IterativeDialogueError("decisión piloto no corresponde a la traducción exacta")
        accepted=decision=="accept_for_this_technical_pilot";document={**expected,"reviewer_declaration":review["reviewer_declaration"],"schema_version":"1.0","contract_version":"dq-pilot28-pilot-translation-decision-v1","mode":"PILOT_TRANSLATION_UNVALIDATED","decision":decision,"accepted_for_this_technical_pilot":accepted,"formal_translation_validated":False,"automatic_approval":False};atomic_json(root/"pilot-translation-decision.json",document);state["pending_translation"]=None
        if not accepted:
            state["stop_reason"]="pilot_translation_rejected_or_unresolved";store.transition(state,"CHECK_CONTINUATION");store.transition(state,"COMPLETED");return state
        return self._present_translation(store,state,round_index=round_index,panel=panel,question=translation["source_question"],translation=translation)

    def answer(self, store: IterativeRunStore, *, answer_literal: str, user_requests_stop: bool = False) -> dict[str, Any]:
        state = store.load_state()
        if state["controller_state"] != "AWAITING_USER" or state["pending_question"] is None:
            raise IterativeDialogueError("controlador no espera respuesta")
        if not answer_literal or len(answer_literal) > 1200:
            raise IterativeDialogueError("respuesta literal inválida")
        turn = state["turns"][-1]
        if turn["answer"] is not None:
            raise IterativeDialogueError("respuesta ya persistida")
        store.transition(state, "ACCUMULATE_ANSWER")
        answer_doc, _ = store.artifact(turn["index"], "human-answer", lambda: {"contract_version": "dq-pilot12-human-answer-v1", "turn_index": turn["index"], "literal": answer_literal, "literal_sha256": digest_text(answer_literal), "human_attested": True, "synthetic": False, "user_requests_stop": user_requests_stop})
        turn["answer"] = {"literal": answer_doc["literal"], "sha256": answer_doc["literal_sha256"], "human_attested": True, "synthetic": False, "user_requests_stop": user_requests_stop}
        state["pending_question"] = None
        state["round_index"] = turn["index"]
        state["accumulated_description"] = accumulated_description(state["original_description"], state["turns"])
        store.write_state(state)
        terminal = "human_requested_stop_after_updated_retrieval" if user_requests_stop else None
        try:
            return self._run_round(store, state, terminal_after_retrieval=terminal)
        except Exception as error:
            state["failure"] = {"type": type(error).__name__, "message": str(error)[:1000], "round_index": state["round_index"]}
            store.transition(state, "FAILED")
            raise
