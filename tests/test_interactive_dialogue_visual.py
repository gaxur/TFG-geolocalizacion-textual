import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from jsonschema import Draft202012Validator

from src.tfg_phase0.dialogue_visual_evidence import FakeVisualEvidenceProvider, Qwen3VLDialogueEvidenceAdapter, VisualEvidencePolicy, VisualImageReference, parse_qwen3_vl_dialogue_output, validate_evidence
from src.tfg_phase0.interactive_dialogue import DialoguePolicyConfig, FakeTextDialogueAdapter, InteractiveDialogueError
from src.tfg_phase0.interactive_dialogue_multiturn import MultiTurnConfig, MultiTurnDialogueOrchestrator, validate_multiturn_session
from src.tfg_phase0.interactive_dialogue_visual import VisualMultiTurnConfig, VisualMultiTurnDialogueOrchestrator, validate_visual_session, write_visual_session
from tests.test_interactive_dialogue_multiturn import AdaptiveRetriever, adaptive_evidence


def image(root: Path, *, authorized=True, exists=True, correct_hash=True, provenance=True, relation="observer_view"):
    path = root / "image.bin"
    if exists: path.write_bytes(b"synthetic visual bytes")
    actual = hashlib.sha256(b"synthetic visual bytes").hexdigest()
    return VisualImageReference("image-1", path, actual if correct_hash else "f" * 64, {"source": "synthetic-test", "license": "test-only"} if provenance else {}, authorized, "auth-test" if authorized else None, relation)


def visual_engine(root: Path, *, state="supported", reference=None, mode=None, enabled=True, maximum=3, observed="objeto visible", reason="not_visible_enough", features=("monument", "church", "square", "park", "commercial", "intersection")):
    retriever = AdaptiveRetriever(); policy = DialoguePolicyConfig(reserve_size=6, cluster_radius_m=75, maximum_supported_fraction=.75)
    config = VisualMultiTurnConfig(MultiTurnConfig(max_questions=maximum, policy=policy), VisualEvidencePolicy(enabled=enabled, maximum_calls=3))
    reference = reference or image(root)
    scenarios = {feature: {"state": state, "observed_evidence": observed if state != "unverifiable" else None, "reason": reason if state == "unverifiable" else None, "mode": mode} for feature in features}
    provider = FakeVisualEvidenceProvider(images={feature: reference for feature in features}, scenarios=scenarios)
    engine = VisualMultiTurnDialogueOrchestrator(retriever=retriever, evidence=adaptive_evidence(features), config=config, text_adapter=FakeTextDialogueAdapter(), visual_provider=provider if enabled else None)
    return engine, retriever, provider


class VisualDialogueTests(unittest.TestCase):
    def test_disabled_visual_mode_projects_exactly_to_v2_behavior(self):
        with TemporaryDirectory() as temporary:
            retriever_a=AdaptiveRetriever();retriever_b=AdaptiveRetriever();policy=DialoguePolicyConfig(reserve_size=6,cluster_radius_m=75,maximum_supported_fraction=.75);base_config=MultiTurnConfig(max_questions=1,policy=policy)
            base=MultiTurnDialogueOrchestrator(retriever=retriever_a,evidence=adaptive_evidence(),config=base_config,text_adapter=FakeTextDialogueAdapter())
            visual=VisualMultiTurnDialogueOrchestrator(retriever=retriever_b,evidence=adaptive_evidence(),config=VisualMultiTurnConfig(base_config,VisualEvidencePolicy(enabled=False)),text_adapter=FakeTextDialogueAdapter())
            base_session=base.answer(base.start(session_label="same",description="Una calle"),"Sí");visual_session=visual.answer(visual.start(session_label="same",description="Una calle"),"Sí")
            self.assertEqual(visual_session["initial_ranking"],base_session["initial_ranking"]);self.assertEqual(visual_session["current_ranking"],base_session["current_ranking"]);self.assertEqual(visual_session["claims"],base_session["claims"]);self.assertEqual(visual_session["visual_evidence"],[])

    def test_supported_contradicted_and_unverifiable_are_recorded_without_ranking_change(self):
        for state in ("supported","contradicted","unverifiable"):
            with self.subTest(state=state),TemporaryDirectory() as temporary:
                engine,retriever,_=visual_engine(Path(temporary),state=state);session=engine.start(session_label=state,description="Una calle");self.assertEqual(session["visual_evidence"][0]["state"],state);self.assertEqual(session["current_ranking"],session["initial_ranking"]);self.assertEqual(len(retriever.calls),1);self.assertEqual(session["models"]["vlm"]["ranking_updates"],0)

    def test_authorization_file_hash_and_provenance_fail_closed_before_provider_call(self):
        cases=(image_kwargs for image_kwargs in ({"authorized":False},{"exists":False},{"correct_hash":False},{"provenance":False}))
        reasons=("image_not_authorized","image_missing","image_hash_mismatch","missing_provenance")
        for kwargs,reason in zip(cases,reasons,strict=True):
            with self.subTest(reason=reason),TemporaryDirectory() as temporary:
                root=Path(temporary);engine,_,provider=visual_engine(root,reference=image(root,**kwargs));session=engine.start(session_label=reason,description="Una calle");record=session["visual_evidence"][0];self.assertEqual(record["state"],"unverifiable");self.assertEqual(record["abstention_reason"],reason);self.assertEqual(provider.calls,[])

    def test_unknown_observer_relation_is_image_only_and_abstains(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);engine,_,provider=visual_engine(root,reference=image(root,relation="unknown"));session=engine.start(session_label="relation",description="Una calle");self.assertEqual(session["visual_evidence"][0]["abstention_reason"],"observer_relation_unverified");self.assertEqual(provider.calls,[])

    def test_invalid_output_exception_and_timeout_become_unverifiable(self):
        for mode,reason in (("invalid_output","provider_error:InteractiveDialogueError"),("exception","provider_error:RuntimeError"),("timeout","provider_timeout")):
            with self.subTest(mode=mode),TemporaryDirectory() as temporary:
                engine,_,_=visual_engine(Path(temporary),mode=mode);session=engine.start(session_label=mode,description="Una calle");self.assertEqual(session["visual_evidence"][0]["state"],"unverifiable");self.assertEqual(session["visual_evidence"][0]["abstention_reason"],reason)

    def test_user_vlm_conflict_preserves_human_query_and_ranking(self):
        with TemporaryDirectory() as temporary:
            engine,retriever,_=visual_engine(Path(temporary),state="contradicted",maximum=1);session=engine.start(session_label="conflict",description="Una calle");before=json.loads(json.dumps(session["initial_ranking"]));session=engine.answer(session,"Sí");self.assertEqual(len(session["source_conflicts"]),1);self.assertEqual(session["initial_ranking"],before);self.assertEqual(len(retriever.calls),2);self.assertNotIn("visual",session["turns"][0]["canonical_query"]["text"].casefold());self.assertFalse(session["source_conflicts"][0]["query_changed"])

    def test_f3_support_and_visual_unverifiable_do_not_conflict_or_eliminate(self):
        with TemporaryDirectory() as temporary:
            engine,retriever,_=visual_engine(Path(temporary),state="unverifiable");session=engine.start(session_label="f3",description="Una calle");self.assertTrue(session["turns"][0]["f3_evidence_considered"]);self.assertEqual(session["source_conflicts"],[]);self.assertEqual(len(session["current_ranking"]["results"]),6);self.assertEqual(len(retriever.calls),1)

    def test_visual_evidence_never_triggers_retrieval_and_human_answer_remains_exhaustive(self):
        with TemporaryDirectory() as temporary:
            engine,retriever,_=visual_engine(Path(temporary),state="supported",maximum=1);session=engine.start(session_label="retrieval",description="Una calle");self.assertEqual(len(retriever.calls),1);session=engine.answer(session,"Sí");self.assertEqual(len(retriever.calls),2);self.assertTrue(all(call["k"]==6 for call in retriever.calls));self.assertEqual(session["turns"][0]["posterior_ranking"]["effective_k"],6)

    def test_three_question_limit_unique_families_and_visual_calls(self):
        with TemporaryDirectory() as temporary:
            engine,_,provider=visual_engine(Path(temporary),state="supported");session=engine.start(session_label="three",description="Una calle")
            for answer in ("Sí","No","No puedo comprobarlo"):session=engine.answer(session,answer)
            families=[turn["question"]["feature"] for turn in session["turns"]];self.assertEqual(len(families),3);self.assertEqual(len(set(families)),3);self.assertEqual(session["stop_reason"],"max_questions_reached");self.assertEqual(len(provider.calls),3)

    def test_adapter_without_runtime_abstains_and_never_imports_torch(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);reference=image(root);adapter=Qwen3VLDialogueEvidenceAdapter(images={"monument":reference});self.assertNotIn("torch",sys.modules);self.assertFalse(adapter.metadata["real_model_inference"])
            # Se valida a través del orquestador para cubrir el request completo.
            retriever=AdaptiveRetriever();policy=DialoguePolicyConfig(reserve_size=6,cluster_radius_m=75,maximum_supported_fraction=.75);engine=VisualMultiTurnDialogueOrchestrator(retriever=retriever,evidence=adaptive_evidence(),config=VisualMultiTurnConfig(MultiTurnConfig(max_questions=1,policy=policy),VisualEvidencePolicy(enabled=True)),visual_provider=adapter);session=engine.start(session_label="inert",description="Una calle");self.assertEqual(session["visual_evidence"][0]["abstention_reason"],"runtime_not_initialized");self.assertNotIn("torch",sys.modules)

    def test_real_adapter_requires_timeout_and_observed_pixel_evidence(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);reference=image(root)
            adapter=Qwen3VLDialogueEvidenceAdapter(images={"monument":reference});self.assertEqual(adapter.metadata["runtime_status"],"request_builder_only")
            with self.assertRaises(InteractiveDialogueError):parse_qwen3_vl_dialogue_output(json.dumps({"verdict":"supported","observed_evidence":None,"ocr_text":None,"limitations":[]}))
            valid=parse_qwen3_vl_dialogue_output(json.dumps({"verdict":"supported","observed_evidence":"torre visible","ocr_text":None,"limitations":["none"]}));self.assertEqual(valid["verdict"],"supported")

    def test_correction_of_prior_family_is_not_compared_with_current_visual_claim(self):
        with TemporaryDirectory() as temporary:
            engine,_,_=visual_engine(Path(temporary),state="contradicted");session=engine.start(session_label="correction-family",description="Una calle");first_label=session["turns"][0]["question"]["label"];session=engine.answer(session,"Sí");conflicts_before=len(session["source_conflicts"]);session=engine.answer(session,f"En realidad no hay {first_label}");self.assertEqual(len(session["source_conflicts"]),conflicts_before)

    def test_schema_persistence_hashes_and_gt_rejection(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);engine,_,_=visual_engine(root,maximum=1);session=engine.answer(engine.start(session_label="schema",description="Una calle"),"Sí");validate_visual_session(session)
            schema=json.loads((Path(__file__).resolve().parents[1]/"schemas/interactive_dialogue_session_v3.schema.json").read_text());self.assertEqual(list(Draft202012Validator(schema).iter_errors(session)),[])
            session_path,events_path=write_visual_session(session,root/"out");self.assertEqual(json.loads(session_path.read_text()),session);self.assertEqual(len(events_path.read_text().splitlines()),len(session["events"]))
            invalid=json.loads(json.dumps(session));invalid["ground_truth"]={}
            with self.assertRaises(InteractiveDialogueError):validate_visual_session(invalid)
            self.assertNotEqual(list(Draft202012Validator(schema).iter_errors(invalid)),[])
            invalid=json.loads(json.dumps(session));invalid["visual_evidence"][0]["state"]="contradicted"
            with self.assertRaises(InteractiveDialogueError):validate_visual_session(invalid)
            invalid=json.loads(json.dumps(session));invalid["visual_evidence"][0]["claim"]["value"]["feature"]="church";invalid["visual_evidence"][0]["evidence_id"]="dialogue-visual-evidence-sha256-"+hashlib.sha256(__import__('src.tfg_phase0.dialogue_visual_evidence',fromlist=['canonical_bytes']).canonical_bytes({k:v for k,v in invalid["visual_evidence"][0].items() if k!="evidence_id"})).hexdigest()
            with self.assertRaisesRegex(InteractiveDialogueError,"turno"):validate_visual_session(invalid)
            invalid=json.loads(json.dumps(session));invalid["visual_evidence"][0]["provider"]["revision"]="otra";invalid["visual_evidence"][0]["evidence_id"]="dialogue-visual-evidence-sha256-"+hashlib.sha256(__import__('src.tfg_phase0.dialogue_visual_evidence',fromlist=['canonical_bytes']).canonical_bytes({k:v for k,v in invalid["visual_evidence"][0].items() if k!="evidence_id"})).hexdigest()
            with self.assertRaisesRegex(InteractiveDialogueError,"turno"):validate_visual_session(invalid)

    def test_legacy_v1_and_v2_validators_remain_operational(self):
        from scripts.run_interactive_dialogue import FakeRetriever,fake_evidence
        from src.tfg_phase0.interactive_dialogue import OneTurnDialogueOrchestrator,validate_session
        one=OneTurnDialogueOrchestrator(retriever=FakeRetriever(),evidence=fake_evidence(),config=DialoguePolicyConfig(reserve_size=4),text_adapter=FakeTextDialogueAdapter()).start(session_label="v1",description="Una calle");validate_session(one)
        base=MultiTurnDialogueOrchestrator(retriever=AdaptiveRetriever(),evidence=adaptive_evidence(),config=MultiTurnConfig(max_questions=1,policy=DialoguePolicyConfig(reserve_size=6,maximum_supported_fraction=.75)),text_adapter=FakeTextDialogueAdapter()).start(session_label="v2",description="Una calle");validate_multiturn_session(base)


if __name__=="__main__":unittest.main()
