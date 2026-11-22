"""Gate A: FastAPI y controlador reales, cuatro puertos simulados sin pesos/GPU."""

import json
from hashlib import sha256
from pathlib import Path
from time import sleep

from fastapi.testclient import TestClient

from backend.atlas_api.dq_iterative_sessions import IterativeDialogueSessionService
from backend.atlas_api.main import create_app
from backend.atlas_api.settings import Settings
from research.dq_pilot_iterative_controller_v1 import IterativeDialogueController, digest
from research.dq_pilot_real_adapters_v1 import RealCT2LRetrieverAdapter, RealTextInterpreterAdapter
from tests.test_dq_pilot23_iterative_integration import CT2LPort, Panel, Questioner, QwenPort, Translator, Validator
from tests.test_dq_pilot24_session_api import FakeRetriever, answer, start


class ReviewRequiredTranslator(Translator):
    identity = {k: v for k, v in Translator.identity.items() if k != "cpu_fixture_auto_review"}


def fixture_app(tmp_path, *, panel_delay=0):
    trace = []

    class InterpreterFixture(QwenPort):
        def transform(self, **kwargs):
            trace.append(("qwen", kwargs["stage"], kwargs["transcript"]))
            output = super().transform(**kwargs)
            if "a la izquierda" in kwargs["transcript"]:
                text = "There is a square and a brick tower. The facade has a clock and the arch is on the left."
                output.update(text=text, raw_output=text, text_sha256=sha256(text.encode()).hexdigest())
            return output

    class RetrievalFixture(CT2LPort):
        def retrieve(self, **kwargs):
            trace.append(("ct2l", kwargs["stage"], kwargs["text"]))
            return super().retrieve(**kwargs)

    class PanelFixture(Panel):
        def build(self, **kwargs):
            if panel_delay:
                sleep(panel_delay)
            return super().build(**kwargs)

    class QuestionFixture(Questioner):
        def generate(self, **kwargs):
            panel = kwargs["panel"]
            trace.append(("dq", f"E{kwargs['round_index']}", panel["source_ranking_sha256"], panel["candidate_ids"]))
            return super().generate(**kwargs)

    def factory(session_id, description):
        interpreter = RealTextInterpreterAdapter(InterpreterFixture())
        retriever = RealCT2LRetrieverAdapter(RetrievalFixture(), query_id=session_id, visual_dataset_id="visual-v1", embedding_dataset_id="embedding-v1")
        questioner = QuestionFixture()
        translator = ReviewRequiredTranslator()
        controller = IterativeDialogueController(interpreter=interpreter, retriever=retriever, panel=PanelFixture(), questioner=questioner, validator=Validator(), translator=translator, top_n=20)
        return controller, {"interpreter": interpreter.identity, "retriever": retriever.identity, "questioner": questioner.identity, "translator": translator.identity}

    service = IterativeDialogueSessionService(session_root=tmp_path / "sessions", controller_factory=factory, enabled=True, fixture_mode=True, translation_available=True, quality_gate_available=True)
    return build_app(service), service, trace


def build_app(service):
    settings = Settings(Path("runtime"), Path("config/madrid.yaml"), "a" * 64, "clip", ())
    return create_app(settings=settings, retriever_factory=lambda _: FakeRetriever(), transformer_factory=lambda _: None, dq_iterative_service=service)


def test_cpu_session_three_rounds_bilingual_review_rankings_sse_and_recovery(tmp_path):
    app, service, trace = fixture_app(tmp_path)
    sessions = "/api/v1/dialogue-freetext/sessions"
    description = "Veo una plaza amplia y una torre de ladrillo."
    answers = ["Veo un reloj en la fachada.", "También hay un arco.", "El arco está a la izquierda."]
    with TestClient(app) as client:
        initial = client.post(sessions, json={**start(), "description_es": description}, headers={"Idempotency-Key": "dq-start-1"})
        assert initial.status_code == 200
        session_id = initial.json()["session_id"]
        url = f"{sessions}/{session_id}"
        run_root = service.session_root / session_id / "run"
        for index, literal in enumerate(answers):
            waiting = client.get(url).json()
            assert waiting["execution_mode"] == "cpu_fixture" and waiting["gpu_used"] is False
            assert waiting["status"] == "waiting_review" and waiting["current_question"] is None
            ranking = waiting["stage_snapshots"][-1]
            assert ranking["stage"] == f"E{index}" and ranking["candidate_count"] == 253
            assert len(ranking["results"]) == 10
            pending = waiting["pending_translation_review"]
            assert pending["source_question_en"] and pending["translated_question_es"].startswith("¿")
            assert pending["formal_translation_validated"] is False
            if index == 0:
                forged = {"turn_index": 1, "question_id": pending["translated_question_sha256"], "question_sha256": pending["translated_question_sha256"]}
                response = client.post(f"{url}/answers", json=answer(forged, operation="before-review"), headers={"Idempotency-Key": "before-review"})
                assert response.status_code == 409
                assert not (run_root.parent / "operations").exists()
                rows = client.get(f"{url}/events").json()["events"]
                stream = client.get(f"{url}/events/stream?follow=true", headers={"Last-Event-ID": rows[2]["event_id"]})
                assert stream.headers["content-type"].startswith("text/event-stream")
                assert [line.removeprefix("id: ") for line in stream.text.splitlines() if line.startswith("id: ")] == [row["event_id"] for row in rows[3:]]
                assert rows[-1]["state"] == "waiting_review"
            review = {k: pending[k] for k in ("translation_sha256", "source_question_sha256", "translated_question_sha256")}
            review.update(ground_truth_used=False, reviewer_declaration="Aceptación solo para la fixture de contrato.", formal_translation_validated=True, automatic_approval=True)
            reviewed = client.post(f"{url}/pilot-translation-decisions", json={"decision": "accept_for_this_technical_pilot", "client_operation_id": f"review-{index}", "review": review})
            assert reviewed.status_code == 200
            assert reviewed.json()["current_question"]["question"] == pending["translated_question_es"]
            decision = json.loads((run_root / "rounds" / f"round-{index}" / "pilot-translation-decision.json").read_text())
            assert decision["formal_translation_validated"] is decision["automatic_approval"] is False
            operation = f"answer-{index}"
            response = client.post(f"{url}/answers", json=answer(reviewed.json()["current_question"], literal=literal, operation=operation), headers={"Idempotency-Key": operation})
            assert response.status_code == 200

        final = client.get(url).json()
        assert final["description_es"] == description
        assert [turn["answer_literal"] for turn in final["turns"]] == answers
        assert all(literal in final["accumulated_description_es"] for literal in [description, *answers])
        assert final["status"] == "completed" and final["current_question"] is None and final["final_stage"] == "E3"
        assert final["stop_reason"] == "max_questions_reached_after_final_retrieval"
        assert [(row[0], row[1]) for row in trace] == [(component, f"E{index}") for index in range(4) for component in (["qwen", "ct2l", "dq"] if index < 3 else ["qwen", "ct2l"])]
        for index, snapshot in enumerate(final["stage_snapshots"]):
            round_root = run_root / "rounds" / f"round-{index}"
            ranking = json.loads((round_root / "ct2l-ranking.json").read_text())
            reserve = json.loads((round_root / "top-n-reserve.json").read_text())
            assert len(ranking["results"]) == 253 and reserve["results"] == ranking["results"][:20]
            assert snapshot["ranking_sha256"] == reserve["source_ranking_sha256"] == digest(ranking)
            assert snapshot["results"] == ranking["results"][:10]
            assert all(literal in trace[index * 3][2] for literal in [description, *answers[:index]])
            if index < 3:
                assert trace[index * 3 + 2][2:] == (digest(ranking), [row["candidate_id"] for row in reserve["results"][:4]])
            else:
                assert not (round_root / "mapillary-panel.json").exists()

    # Verificar otra instancia HTTP sin reconstruir el controlador ni ejecutar modelos.
    reopened = IterativeDialogueSessionService(session_root=service.session_root, enabled=True)
    with TestClient(build_app(reopened)) as client:
        assert client.get(url).json() == final
