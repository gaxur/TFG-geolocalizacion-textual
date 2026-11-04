import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jsonschema import Draft202012Validator

from scripts.run_interactive_dialogue import FakeRetriever, fake_evidence
from src.tfg_phase0.interactive_dialogue import (
    CandidateFeature,
    DialoguePolicyConfig,
    DialogueStateError,
    F3EvidenceIndex,
    FakeTextDialogueAdapter,
    InteractiveDialogueError,
    OneTurnDialogueOrchestrator,
    QuestionIntent,
    compare_rankings,
    literal_query,
    validate_controlled_rewrite,
    validate_question_redaction,
    validate_session,
    write_session,
)


def orchestrator(*, text_adapter=None, evidence=None, retriever=None, radius=75.0):
    return OneTurnDialogueOrchestrator(
        retriever=retriever or FakeRetriever(),
        evidence=evidence or fake_evidence(),
        config=DialoguePolicyConfig(reserve_size=4, cluster_radius_m=radius),
        text_adapter=text_adapter if text_adapter is not None else FakeTextDialogueAdapter(),
    )


class InteractiveDialogueTests(unittest.TestCase):
    def test_one_turn_preserves_literal_text_and_full_rankings(self):
        engine = orchestrator(text_adapter=FakeTextDialogueAdapter(rewrite="Veo una plaza y Veo una iglesia"))
        session = engine.start(session_label="s1", description="Veo una plaza")
        self.assertEqual(session["status"], "awaiting_answer")
        self.assertEqual(session["inputs"]["description"]["text"], "Veo una plaza")
        self.assertEqual(session["initial_ranking"]["effective_k"], 4)
        initial = json.loads(json.dumps(session["initial_ranking"]))
        completed = engine.answer(session, "Veo una iglesia")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["turns_used"], 1)
        self.assertEqual(completed["human_answer"]["text"], "Veo una iglesia")
        self.assertEqual(completed["initial_ranking"], initial)
        self.assertEqual(len(completed["updated_rankings"]), 2)
        self.assertTrue(all(row["ranking"]["effective_k"] == 4 for row in completed["updated_rankings"]))
        self.assertEqual(completed["updated_rankings"][0]["ranking"]["results"][0]["candidate_id"], "fake-c")
        self.assertFalse(any(value["geographic_improvement_evaluated"] for value in completed["comparisons"]))
        validate_session(completed)

    def test_second_turn_and_invalid_transition_are_rejected(self):
        engine = orchestrator()
        session = engine.start(session_label="s2", description="Una calle urbana")
        completed = engine.answer(session, "Sí, veo una iglesia")
        with self.assertRaises(DialogueStateError):
            engine.answer(completed, "Otra respuesta")
        with self.assertRaises(DialogueStateError):
            engine.answer(session, "  ")

    def test_unknown_answer_stops_without_new_retrieval(self):
        retriever = FakeRetriever()
        engine = orchestrator(retriever=retriever)
        session = engine.start(session_label="s3", description="Una calle urbana")
        completed = engine.answer(session, "No puedo comprobarlo")
        self.assertEqual(completed["stop_reason"], "human_could_not_answer")
        self.assertEqual(completed["updated_rankings"], [])
        self.assertEqual(len(retriever.calls), 1)

    def test_contradictory_answer_is_preserved_without_silent_interpretation(self):
        engine = orchestrator()
        session = engine.start(session_label="contradictory", description="Una calle urbana")
        answer = "No veo una iglesia, aunque quizá sí hay una detrás"
        completed = engine.answer(session, answer)
        self.assertEqual(completed["human_answer"]["text"], answer)
        self.assertTrue(completed["human_answer"]["informative"])
        self.assertIn(answer, completed["query_updates"][0]["text"])

    def test_bare_yes_is_bound_to_selected_intent(self):
        engine = orchestrator()
        session = engine.start(session_label="yes", description="Una calle urbana")
        feature = session["selected_question"]["label"]
        completed = engine.answer(session, "Sí")
        self.assertEqual(completed["human_answer"]["text"], "Sí")
        self.assertIn(feature, completed["human_answer"]["validated_clarification"])
        self.assertIn(feature, completed["query_updates"][0]["text"])

    def test_no_discriminative_evidence_abstains(self):
        empty = F3EvidenceIndex(dataset_id="empty", features_by_candidate={}, source_hashes={})
        session = orchestrator(evidence=empty).start(session_label="s4", description="Una calle")
        self.assertEqual(session["status"], "completed")
        self.assertEqual(session["stop_reason"], "no_discriminative_question")
        self.assertIsNone(session["selected_question"])

    def test_qwen_question_validation_and_fallback(self):
        invalid = FakeTextDialogueAdapter(question="¿Confirmas que estás junto a la iglesia de San X?")
        session = orchestrator(text_adapter=invalid).start(session_label="s5", description="Una calle")
        self.assertEqual(session["selected_question"]["source"], "deterministic_template")
        self.assertIsNotNone(session["selected_question"]["fallback_reason"])
        failing = orchestrator(text_adapter=FakeTextDialogueAdapter(fail=True)).start(session_label="s6", description="Una calle")
        self.assertEqual(failing["selected_question"]["source"], "deterministic_template")
        self.assertTrue(failing["selected_question"]["fallback_reason"].startswith("runtime_error:"))

    def test_question_validator_rejects_new_entity_and_suggestion(self):
        intent = QuestionIntent("i", "church", "una iglesia o lugar de culto", ("h1",), ("h2",), ("node/1",), "Sin cambiar de posición, ¿puedes ver una iglesia o lugar de culto? Responde sí, no o no puedo comprobarlo.", (1.0,))
        self.assertEqual(validate_question_redaction(intent.deterministic_question, intent), (True, None))
        self.assertFalse(validate_question_redaction("¿Confirmas que deberías ver una iglesia o lugar de culto? Sí, no o no puedo comprobarlo.", intent)[0])
        self.assertFalse(validate_question_redaction("¿Ves una iglesia o lugar de culto llamada San Ginés? Sí, no o no puedo comprobarlo.", intent)[0])

    def test_rewrite_validation_rejects_invention_and_loss(self):
        self.assertEqual(validate_controlled_rewrite("Veo una plaza", "Hay una iglesia", "Veo una plaza y Hay una iglesia"), (True, None))
        self.assertEqual(validate_controlled_rewrite("Veo una plaza", "Hay una iglesia", "Veo una plaza roja y Hay una iglesia")[1], "invented_content")
        self.assertEqual(validate_controlled_rewrite("Veo una plaza", "Hay una iglesia", "Hay una iglesia")[1], "original_information_lost")
        self.assertEqual(validate_controlled_rewrite("Veo una plaza", "Hay una iglesia", "Veo una plaza sin Hay una iglesia")[1], "invented_content")
        self.assertTrue(literal_query("x", "iglesia").startswith("[ACLARACIÓN VALIDADA]\niglesia"))

    def test_invalid_rewrite_is_recorded_but_not_retrieved(self):
        retriever = FakeRetriever()
        engine = orchestrator(retriever=retriever, text_adapter=FakeTextDialogueAdapter(rewrite="Estoy en Sol junto a una iglesia roja"))
        completed = engine.answer(engine.start(session_label="s7", description="Una calle"), "Veo una iglesia")
        rewrite = next(row for row in completed["query_updates"] if row["variant"] == "controlled_rewrite")
        self.assertEqual(rewrite["status"], "rejected")
        self.assertEqual(len(completed["updated_rankings"]), 1)
        self.assertEqual(len(retriever.calls), 2)

    def test_f3_positive_unknown_boundary_and_ambiguity(self):
        objects = [{"osm_ref": f"node/{index}", "osm_type": "node", "osm_id": index, "geometry_status": "valid", "geometry_role": "point", "tags": {"amenity": "place_of_worship"}} for index in range(1, 7)]
        base = {"contains": False, "within": True, "crosses": False, "touches": False, "overlaps": False, "intersects": True, "center_distance_m": 1.0}
        associations = [{"candidate_id": "a", "osm_ref": "node/1", "boundary_contact_only": False, **base}]
        associations += [{"candidate_id": "ambiguous", "osm_ref": f"node/{index}", "boundary_contact_only": False, **base} for index in range(1, 6)]
        associations += [{"candidate_id": "boundary", "osm_ref": "node/6", "boundary_contact_only": True, **base}]
        index = F3EvidenceIndex.from_documents(dataset_id="f3", objects=objects, associations=associations)
        self.assertEqual(index.features("a")[0].feature, "church")
        self.assertEqual(index.features("missing"), ())
        self.assertEqual(index.features("boundary"), ())
        self.assertTrue(index.features("ambiguous")[0].ambiguous)

    def test_nearby_cells_form_one_hypothesis(self):
        session = orchestrator(radius=75.0).start(session_label="s8", description="Una calle")
        groups = [set(row["candidate_ids"]) for row in session["hypotheses"]]
        self.assertIn({"fake-a", "fake-b"}, groups)

    def test_ranking_comparison_has_no_geographic_claim(self):
        retriever = FakeRetriever()
        first = retriever.retrieve_full(query_id="a", text="calle", language="es")
        second = retriever.retrieve_full(query_id="b", text="iglesia", language="es")
        comparison = compare_rankings(first, second)
        self.assertTrue(comparison["top1_changed"])
        self.assertFalse(comparison["geographic_improvement_evaluated"])

    def test_runtime_failure_does_not_mutate_initial_session(self):
        class FailingRetriever(FakeRetriever):
            def retrieve_full(self, **kwargs):
                if self.calls:
                    raise RuntimeError("ct2l failed")
                return super().retrieve_full(**kwargs)
        engine = orchestrator(retriever=FailingRetriever())
        session = engine.start(session_label="s9", description="Una calle")
        frozen = json.loads(json.dumps(session))
        with self.assertRaises(RuntimeError):
            engine.answer(session, "Veo una iglesia")
        self.assertEqual(session, frozen)

    def test_ground_truth_fields_are_forbidden_and_events_are_tamper_evident(self):
        session = orchestrator().start(session_label="s10", description="Una calle")
        invalid = json.loads(json.dumps(session))
        invalid["ground_truth"] = {"candidate_id": "fake-c"}
        with self.assertRaises(InteractiveDialogueError):
            validate_session(invalid)
        invalid = json.loads(json.dumps(session))
        invalid["events"][0]["payload"]["description"] = "alterada"
        with self.assertRaises(InteractiveDialogueError):
            validate_session(invalid)
        invalid = json.loads(json.dumps(session))
        invalid["events"][0]["recorded_at_utc"] = "2000-01-01T00:00:00Z"
        with self.assertRaises(InteractiveDialogueError):
            validate_session(invalid)
        invalid = json.loads(json.dumps(session))
        invalid["initial_ranking"]["results"].pop()
        invalid["initial_ranking"]["effective_k"] -= 1
        invalid["initial_ranking"]["gallery_count"] -= 1
        with self.assertRaises(InteractiveDialogueError):
            validate_session(invalid)
        invalid = json.loads(json.dumps(session))
        invalid["models"]["gt"] = "forbidden"
        with self.assertRaises(InteractiveDialogueError):
            validate_session(invalid)

    def test_materialized_query_update_cannot_diverge_from_event(self):
        engine = orchestrator()
        session = engine.answer(engine.start(session_label="links", description="Una calle"), "Veo una iglesia")
        session["query_updates"][0]["text"] += " alterado"
        with self.assertRaises(InteractiveDialogueError):
            validate_session(session)

    def test_session_serialization_is_reproducible_and_append_only(self):
        session = orchestrator().start(session_label="s11", description="Una calle")
        with TemporaryDirectory() as directory:
            session_path, events_path = write_session(session, Path(directory) / "run")
            loaded = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, session)
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events, session["events"])

    def test_external_schema_accepts_session_and_rejects_gt(self):
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas/interactive_dialogue_session.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        session = orchestrator().start(session_label="schema", description="Una calle")
        self.assertEqual(list(validator.iter_errors(session)), [])
        session["ground_truth"] = {}
        self.assertNotEqual(list(validator.iter_errors(session)), [])
        del session["ground_truth"]
        session["events"][0]["payload"]["reference_coordinate"] = {}
        self.assertNotEqual(list(validator.iter_errors(session)), [])
        del session["events"][0]["payload"]["reference_coordinate"]
        session["models"]["gt"] = "forbidden"
        self.assertNotEqual(list(validator.iter_errors(session)), [])


if __name__ == "__main__":
    unittest.main()
