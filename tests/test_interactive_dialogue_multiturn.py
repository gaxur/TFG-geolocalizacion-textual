import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jsonschema import Draft202012Validator

from src.tfg_phase0.interactive_dialogue import CandidateFeature, DialoguePolicyConfig, F3EvidenceIndex, FakeTextDialogueAdapter, InteractiveDialogueError
from src.tfg_phase0.interactive_dialogue_multiturn import (
    MultiTurnConfig,
    MultiTurnDialogueOrchestrator,
    build_canonical_query,
    validate_multiturn_session,
    write_multiturn_session,
)


class AdaptiveRetriever:
    gallery_id = "fake-adaptive"

    def __init__(self, count=6):
        self.ids = [f"candidate-{index}" for index in range(1, count + 1)]
        self.calls = []

    @property
    def metadata(self):
        return {"adapter": "fake-global-v2", "expected_gallery_count": len(self.ids), "calls": list(self.calls), "gpu_used": False}

    def count_tokens(self, text):
        return len(text.split()) + 2

    def retrieve_full(self, *, query_id, text, language):
        self.calls.append({"query_id": query_id, "text": text, "language": language, "k": len(self.ids)})
        shift = sum(ord(value) for value in text) % len(self.ids)
        ordered = self.ids[shift:] + self.ids[:shift]
        return {
            "gallery_id": self.gallery_id,
            "gallery_count": len(self.ids),
            "requested_k": len(self.ids),
            "effective_k": len(self.ids),
            "ranking_method": "exhaustive_cosine",
            "tie_break": "candidate_id_ascending",
            "results": [
                {"rank": rank, "candidate_id": candidate_id, "latitude": 40.40 + self.ids.index(candidate_id) * .002, "longitude": -3.70, "cosine_similarity": 1 - rank / 100}
                for rank, candidate_id in enumerate(ordered, 1)
            ],
        }


def adaptive_evidence(features=("monument", "church", "square", "park", "commercial", "intersection")):
    labels = {
        "monument": "un monumento o elemento histórico", "church": "una iglesia o lugar de culto",
        "square": "una plaza o espacio peatonal amplio", "park": "un parque o jardín",
        "commercial": "un comercio o equipamiento identificable", "intersection": "una intersección de varias calles",
    }
    rows = {}
    for index, feature in enumerate(features, 1):
        rows[f"candidate-{index}"] = (CandidateFeature(feature, labels[feature], (f"node/{index}",), False),)
    return F3EvidenceIndex(dataset_id="fake-f3-adaptive", features_by_candidate=rows, source_hashes={}, catalog_manifest_id="fake", catalog_manifest_sha256="0" * 64)


def engine(*, maximum=3, features=("monument", "church", "square", "park", "commercial", "intersection"), adapter=None, retriever=None):
    retriever = retriever or AdaptiveRetriever()
    policy = DialoguePolicyConfig(reserve_size=6, cluster_radius_m=75, maximum_supported_fraction=.75)
    return MultiTurnDialogueOrchestrator(retriever=retriever, evidence=adaptive_evidence(features), config=MultiTurnConfig(max_questions=maximum, policy=policy), text_adapter=adapter), retriever


class MultiTurnDialogueTests(unittest.TestCase):
    def test_zero_questions_by_abstention(self):
        orchestrator, retriever = engine(features=())
        session = orchestrator.start(session_label="zero", description="Una calle")
        self.assertEqual(session["status"], "completed")
        self.assertEqual(session["stop_reason"], "no_discriminative_question")
        self.assertEqual(session["questions_asked"], 0)
        self.assertEqual(len(retriever.calls), 1)

    def test_one_question_compatibility_and_global_retrieval(self):
        orchestrator, retriever = engine(maximum=1)
        started = orchestrator.start(session_label="one", description="Una calle")
        initial = json.loads(json.dumps(started["initial_ranking"]))
        completed = orchestrator.answer(started, "Sí")
        self.assertEqual(completed["stop_reason"], "max_questions_reached")
        self.assertEqual(completed["initial_ranking"], initial)
        self.assertEqual(len(retriever.calls), 2)
        self.assertTrue(all(call["k"] == 6 for call in retriever.calls))
        self.assertEqual(len(completed["turns"][0]["posterior_ranking"]["results"]), 6)
        validate_multiturn_session(completed)

    def test_two_questions_are_selected_from_updated_ranking(self):
        orchestrator, retriever = engine(maximum=2)
        session = orchestrator.start(session_label="two", description="Una calle")
        first_input = session["turns"][0]["input_ranking_sha256"]
        session = orchestrator.answer(session, "No")
        self.assertEqual(session["status"], "awaiting_answer")
        self.assertNotEqual(session["turns"][1]["input_ranking_sha256"], first_input)
        self.assertEqual(session["turns"][1]["input_ranking"], session["turns"][0]["posterior_ranking"])
        self.assertNotEqual(session["turns"][0]["input_ranking"]["results"][0]["candidate_id"], session["turns"][1]["input_ranking"]["results"][0]["candidate_id"])
        session = orchestrator.answer(session, "Sí")
        self.assertEqual(session["questions_asked"], 2)
        self.assertEqual(session["stop_reason"], "max_questions_reached")
        self.assertEqual(len(retriever.calls), 3)

    def test_three_questions_have_distinct_semantic_families(self):
        orchestrator, retriever = engine()
        session = orchestrator.start(session_label="three", description="Una calle")
        for answer in ("Sí", "No", "Sí"):
            session = orchestrator.answer(session, answer)
        families = [turn["question"]["intent_family"] for turn in session["turns"]]
        self.assertEqual(len(families), 3)
        self.assertEqual(len(set(families)), 3)
        self.assertEqual(session["stop_reason"], "max_questions_reached")
        self.assertEqual(len(retriever.calls), 4)

    def test_unknown_and_ambiguous_continue_without_retrieval(self):
        orchestrator, retriever = engine()
        session = orchestrator.start(session_label="unknown", description="Una calle")
        session = orchestrator.answer(session, "No puedo comprobarlo")
        self.assertEqual(len(retriever.calls), 1)
        self.assertEqual(session["status"], "awaiting_answer")
        self.assertEqual(session["turns"][0]["answer"]["interpretation"]["kind"], "unobservable")
        first_family = session["turns"][0]["question"]["intent_family"]
        self.assertNotEqual(session["turns"][1]["question"]["intent_family"], first_family)
        session = orchestrator.answer(session, "Sí, aunque quizá no")
        self.assertEqual(len(retriever.calls), 1)
        self.assertEqual(session["turns"][1]["answer"]["interpretation"]["kind"], "ambiguous")

    def test_human_stop_does_not_retrieve(self):
        orchestrator, retriever = engine()
        session = orchestrator.start(session_label="stop", description="Una calle")
        session = orchestrator.answer(session, "Terminar")
        self.assertEqual(session["stop_reason"], "human_requested_stop")
        self.assertEqual(len(retriever.calls), 1)

    def test_explicit_correction_preserves_both_claims_and_supersedes_first(self):
        orchestrator, _ = engine()
        session = orchestrator.start(session_label="correction", description="Una calle")
        first_label = session["turns"][0]["question"]["label"]
        session = orchestrator.answer(session, "Sí")
        session = orchestrator.answer(session, f"En realidad no hay {first_label}")
        self.assertEqual(len(session["claims"]), 2)
        self.assertFalse(session["claims"][0]["active"])
        self.assertEqual(session["claims"][1]["supersedes"], session["claims"][0]["claim_id"])
        self.assertNotIn(session["claims"][0]["clarification"], session["turns"][1]["canonical_query"]["text"])
        self.assertIn(session["claims"][1]["clarification"], session["turns"][1]["canonical_query"]["text"])

    def test_correction_matches_specific_family_with_multiple_claims(self):
        orchestrator, _ = engine()
        session = orchestrator.start(session_label="specific-correction", description="Una calle")
        first_label = session["turns"][0]["question"]["label"]
        session = orchestrator.answer(session, "Sí")
        session = orchestrator.answer(session, "Sí")
        session = orchestrator.answer(session, f"En realidad no hay {first_label}")
        self.assertEqual(session["claims"][-1]["supersedes"], session["claims"][0]["claim_id"])
        self.assertFalse(session["claims"][0]["active"])
        self.assertTrue(session["claims"][1]["active"])

    def test_unresolvable_correction_stops_conservatively(self):
        orchestrator, retriever = engine()
        session = orchestrator.start(session_label="conflict", description="Una calle")
        session = orchestrator.answer(session, "Sí")
        calls = len(retriever.calls)
        session = orchestrator.answer(session, "En realidad quizá era otra cosa")
        self.assertEqual(session["stop_reason"], "unresolvable_contradiction")
        self.assertEqual(len(retriever.calls), calls)

    def test_qwen_failures_are_per_turn_fallbacks(self):
        orchestrator, retriever = engine(adapter=FakeTextDialogueAdapter(fail=True))
        session = orchestrator.start(session_label="qwen-fail", description="Una calle")
        self.assertEqual(session["turns"][0]["question"]["source"], "deterministic_template")
        self.assertIn("runtime_error", session["turns"][0]["question"]["fallback_reason"])
        session = orchestrator.answer(session, "Sí")
        rewrite = next(row for row in session["turns"][0]["query_updates"] if row["variant"] == "controlled_rewrite")
        self.assertEqual(rewrite["status"], "failed")
        self.assertEqual(len(retriever.calls), 2)

    def test_retrieval_failure_stops_without_losing_initial_ranking(self):
        class FailingRetriever(AdaptiveRetriever):
            def retrieve_full(self, **kwargs):
                if self.calls:
                    raise RuntimeError("synthetic failure")
                return super().retrieve_full(**kwargs)
        retriever = FailingRetriever()
        orchestrator, _ = engine(retriever=retriever)
        session = orchestrator.start(session_label="runtime", description="Una calle")
        initial = json.loads(json.dumps(session["initial_ranking"]))
        session = orchestrator.answer(session, "Sí")
        self.assertEqual(session["stop_reason"], "runtime_failure")
        self.assertEqual(session["initial_ranking"], initial)
        self.assertIsNone(session["turns"][0]["posterior_ranking"])

    def test_vlm_provider_cannot_be_enabled(self):
        class ForbiddenVisual:
            metadata = {"model_id": "Qwen/Qwen3-VL-8B-Instruct"}
            def inspect(self, **kwargs):
                raise AssertionError("must not be called")
        retriever = AdaptiveRetriever()
        with self.assertRaisesRegex(InteractiveDialogueError, "VLM"):
            MultiTurnDialogueOrchestrator(retriever=retriever, evidence=adaptive_evidence(), config=MultiTurnConfig(), visual_provider=ForbiddenVisual())

    def test_controlled_rewrite_never_drives_next_turn(self):
        retriever = AdaptiveRetriever()
        adapter = FakeTextDialogueAdapter(rewrite="Una calle y La persona indica que puede ver un monumento o elemento histórico.")
        orchestrator, _ = engine(adapter=adapter, retriever=retriever)
        session = orchestrator.start(session_label="canonical", description="Una calle")
        session = orchestrator.answer(session, "Sí")
        rewrite = next(row for row in session["turns"][0]["query_updates"] if row["variant"] == "controlled_rewrite")
        self.assertFalse(rewrite["canonical_for_next_turn"])
        self.assertEqual(retriever.calls[-1]["text"], session["turns"][0]["canonical_query"]["text"])
        self.assertEqual(len(retriever.calls), 2)

    def test_disabled_controlled_rewrite_makes_no_adapter_call(self):
        class CountingAdapter(FakeTextDialogueAdapter):
            def __init__(self):
                super().__init__(); self.rewrite_calls = 0
            def rewrite_query(self, original, clarification):
                self.rewrite_calls += 1
                return super().rewrite_query(original, clarification)
        adapter = CountingAdapter(); retriever = AdaptiveRetriever()
        policy = DialoguePolicyConfig(reserve_size=6, cluster_radius_m=75, enable_controlled_rewrite=False)
        orchestrator = MultiTurnDialogueOrchestrator(retriever=retriever, evidence=adaptive_evidence(), config=MultiTurnConfig(policy=policy), text_adapter=adapter)
        session = orchestrator.answer(orchestrator.start(session_label="no-rewrite", description="Una calle"), "Sí")
        self.assertEqual(adapter.rewrite_calls, 0)
        self.assertEqual([row["variant"] for row in session["turns"][0]["query_updates"]], ["literal_concatenation"])

    def test_token_budget_is_explicit_and_never_silent(self):
        retriever = AdaptiveRetriever()
        original = " ".join(f"palabra{index}" for index in range(400))
        query = build_canonical_query(original, (), retriever)
        self.assertLessEqual(query["token_count"], 300)
        self.assertFalse(query["is_complete_transcript"])
        self.assertEqual(query["omitted_fragments"][0]["omission"], "original_suffix")
        orchestrator, _ = engine(retriever=retriever)
        session = orchestrator.start(session_label="long", description=original)
        self.assertEqual(session["inputs"]["description"]["text"], original)
        self.assertLessEqual(session["initial_query"]["token_count"], 300)

    def test_rankings_and_literal_answers_are_immutable(self):
        orchestrator, _ = engine(maximum=2)
        session = orchestrator.start(session_label="immutable", description="Una calle")
        first = json.loads(json.dumps(session["turns"][0]["input_ranking"]))
        session = orchestrator.answer(session, "No")
        session = orchestrator.answer(session, "No puedo comprobarlo")
        self.assertEqual(session["turns"][0]["input_ranking"], first)
        self.assertEqual(session["turns"][0]["answer"]["literal"], "No")
        self.assertEqual(session["turns"][1]["answer"]["literal"], "No puedo comprobarlo")

    def test_schema_hash_chain_gt_and_vlm_guards(self):
        orchestrator, _ = engine(maximum=1)
        session = orchestrator.answer(orchestrator.start(session_label="schema", description="Una calle"), "Sí")
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas/interactive_dialogue_session_v2.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(session)), [])
        self.assertEqual(session["models"]["vlm"]["calls"], 0)
        with TemporaryDirectory() as temporary:
            session_path, events_path = write_multiturn_session(session, Path(temporary) / "run")
            self.assertEqual(json.loads(session_path.read_text()), session)
            self.assertEqual(len(events_path.read_text().splitlines()), len(session["events"]))
        invalid = json.loads(json.dumps(session)); invalid["ground_truth"] = {}
        with self.assertRaises(InteractiveDialogueError): validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["events"][0]["payload"]["description"] = "alterada"
        with self.assertRaises(InteractiveDialogueError): validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["turns"][0]["question"]["final_question"] = "¿Pregunta alterada?"
        with self.assertRaisesRegex(InteractiveDialogueError, "pregunta"):
            validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["turns"][0]["answer"]["literal"] = "No"; invalid["turns"][0]["answer"]["sha256"] = __import__("hashlib").sha256(b"No").hexdigest()
        with self.assertRaisesRegex(InteractiveDialogueError, "respuesta"):
            validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["claims"][0]["label"] = "etiqueta alterada"
        with self.assertRaisesRegex(InteractiveDialogueError, "intención"):
            validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["turns"][0]["question"]["qwen_audit"] = {"invented": True}
        with self.assertRaisesRegex(InteractiveDialogueError, "pregunta"):
            validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["events"][-1]["payload"]["reason"] = "runtime_failure"
        with self.assertRaises(InteractiveDialogueError):
            validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["initial_ranking"]["results"][0]["cosine_similarity"] = .123
        with self.assertRaises(InteractiveDialogueError):
            validate_multiturn_session(invalid)
        invalid = json.loads(json.dumps(session)); invalid["models"]["vlm"]["calls"] = 1
        with self.assertRaises(InteractiveDialogueError): validate_multiturn_session(invalid)

    def test_duplicate_semantic_family_is_rejected(self):
        orchestrator, _ = engine(maximum=2)
        session = orchestrator.start(session_label="duplicate", description="Una calle")
        session = orchestrator.answer(session, "No puedo comprobarlo")
        session["turns"][1]["question"]["intent_family"] = session["turns"][0]["question"]["intent_family"]
        with self.assertRaisesRegex(InteractiveDialogueError, "semántica repetida"):
            validate_multiturn_session(session)


if __name__ == "__main__":
    unittest.main()
