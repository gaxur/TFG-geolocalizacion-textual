import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.tfg_phase0.dialogue_en_cartographic import (
    LANGUAGE_POLICY_V1,
    LANGUAGE_POLICY_V2,
    DialogueEnCartographicError,
    FrozenRound,
    audit_clip_tokenization,
    build_prompt,
    camera_metrics,
    compare_rankings,
    compose_query_bundle,
    detect_language_v1,
    detect_language_v2,
    evaluate_e_vs_r,
    load_plan,
    materialize_with_transformer,
    materialize_continuation,
    prepare_continuation_bundle,
    prepare_query_bundle,
    retrieve_query_bundle,
    sha256_text,
    validate_output,
    validate_query_bundle,
)
from src.tfg_phase0.f5_text_transform import TransformResult


ROOT = Path(__file__).resolve().parents[1]
PLAN = PARENT = E0_REVIEW = None
HISTORICAL_E0 = "I am in a plaza surrounded by buildings with balconies."
VALID = {
    "E0": "The observer is in a square surrounded by buildings.",
    "E1": "The observer is in a square surrounded by buildings. A monument is visible from the observer's position.",
    "E2": "The observer is in a square surrounded by buildings. A monument is visible from the observer's position. A church or place of worship is not visible from the observer's position.",
    "E3": "The observer is in a square surrounded by buildings. A monument is visible from the observer's position. A church or place of worship is not visible from the observer's position. A park or garden is not visible from the observer's position.",
}


class Transformer:
    def __init__(self, outputs=None, start=0):self.outputs=outputs or VALID;self.calls=[];self.start=start
    def generate_prompt(self,prompt,config):
        round_id=f"E{self.start+len(self.calls)}";self.calls.append((round_id,prompt,config));text=self.outputs[round_id]
        if isinstance(text,Exception):raise text
        return TransformResult(text,text,1.0)


class TokenTensor:
    def __init__(self,values):self.values=values
    def tolist(self):return self.values


def tokenizer_without_truncation(texts,context_length,truncate):
    values=[]
    for text in texts:
        content=list(range(1,min(20,len(text.split())+1)));row=[49406,*content,49407];row.extend([0]*(context_length-len(row)));values.append(row)
    return TokenTensor(values)


def fixture_inputs(root):
    description="Estoy en una plaza y estoy rodeado de edificios con balcones."
    turns=[
        {"index":1,"answer_literal":"Sí","answer_sha256":sha256_text("Sí"),"claim_id":"claim-001","clarification":"La persona indica que puede ver un monumento o elemento histórico."},
        {"index":2,"answer_literal":"No","answer_sha256":sha256_text("No"),"claim_id":"claim-002","clarification":"La persona indica que no puede ver una iglesia o lugar de culto desde su posición."},
        {"index":3,"answer_literal":"No","answer_sha256":sha256_text("No"),"claim_id":"claim-003","clarification":"La persona indica que no puede ver un parque o jardín desde su posición."},
    ]
    sources=[]
    for index in range(4):
        parts=["[DESCRIPCIÓN ORIGINAL]",description]
        if index:parts.extend(["[ACLARACIONES HUMANAS VALIDADAS]",*[row["clarification"] for row in turns[:index]]])
        text="\n".join(parts);sources.append({"round":f"E{index}","available_turns":list(range(1,index+1)),"text":text,"sha256":sha256_text(text)})
    prompt="Fixture versioned cartographic prompt."
    frozen={"contract_version":"dialogue-v3-en-cartographic-frozen-inputs-v1","status":"FROZEN_BEFORE_NEW_INFERENCE","session_id":"fixture-session","description":{"text":description,"sha256":sha256_text(description)},"turns":turns,"round_sources":sources,"controls":{"answers_reused_literally":True,"questions_regenerated":False,"future_answers_visible_to_earlier_rounds":False,"mapillary_reference_available_to_transformer":False,"rankings_available_to_transformer":False,"vlm_available_to_transformer":False}}
    contract={"contract_version":"dialogue-v3-en-cartographic-query-construction-v1","experiment_prompt_version":"dialogue-en-cartographic-visibility-v1","prompt_text":prompt,"prompt_sha256":sha256_text(prompt),"rounds":[{"round":f"E{i}","required_claims":[f"claim-{j:03d}" for j in range(1,i+1)]} for i in range(4)]}
    plan=root/"plan";plan.mkdir();(plan/"frozen-inputs.json").write_text(json.dumps(frozen));(plan/"query-construction-contract.json").write_text(json.dumps(contract));(plan/"experiment-plan.json").write_text(json.dumps({"fixture":True}))
    prepared=prepare_query_bundle(plan);e0=prepared["rounds"][0];spec=FrozenRound(e0["round"],e0["source_text"],e0["source_sha256"],tuple(e0["available_turns"]),tuple(e0["required_claim_ids"]));e0={**e0,"output_text":HISTORICAL_E0,"output_sha256":sha256_text(HISTORICAL_E0),"automatic_validation":validate_output(spec,HISTORICAL_E0,language_policy=LANGUAGE_POLICY_V1),"review_status":"rejected"};parent={**prepared,"status":"GENERATION_REJECTED","execution":{"automatic_retries":0,"calls":1,"model_loads":1,"real_model_inference":True,"synthetic_fixture":False},"rounds":[e0,*[{**row,"review_status":"not_attempted_after_failure"} for row in prepared["rounds"][1:]]]}
    parent_root=root/"parent";parent_root.mkdir();(parent_root/"queries.json").write_text(json.dumps(parent));(parent_root/"manifest.json").write_text(json.dumps({"status":"committed","files":{"queries.json":hashlib.sha256((parent_root/"queries.json").read_bytes()).hexdigest()}}))
    review={"contract_version":"dialogue-v3-en-cartographic-human-review-v1","review_id":"fixture-review","round":"E0","status":"approved","decision":"APPROVED_WITHOUT_CHANGES","approved_text":HISTORICAL_E0,"approved_text_sha256":sha256_text(HISTORICAL_E0),"text_modified":False}
    review_path=root/"review.json";review_path.write_text(json.dumps(review));return plan,parent_root,review_path


def reviewed_bundle(real=True):
    bundle=prepare_query_bundle(PLAN);rows=[]
    for row in bundle["rounds"]:
        text=VALID[row["round"]];spec=FrozenRound(row["round"],row["source_text"],row["source_sha256"],tuple(row["available_turns"]),tuple(row["required_claim_ids"]))
        rows.append({**row,"output_text":text,"output_sha256":sha256_text(text),"automatic_validation":validate_output(spec,text),"review_status":"reviewed"})
    bundle={**bundle,"status":"REVIEWED_AND_FROZEN","rounds":rows,"execution":{"real_model_inference":real,"synthetic_fixture":not real,"calls":4,"model_loads":1 if real else 0,"automatic_retries":0}}
    return bundle


def ranking(order=None):
    ids=order or [f"fixture-{i:03d}" for i in range(253)]
    return {"gallery_id":"madrid-50m","gallery_count":253,"requested_k":253,"effective_k":253,"ranking_method":"exhaustive_cosine","tie_break":"candidate_id_ascending","results":[{"rank":i+1,"candidate_id":candidate,"latitude":40+i/10000,"longitude":-3.0,"cosine_similarity":1-i/1000} for i,candidate in enumerate(ids)]}


class Retriever:
    gallery_id="madrid-50m";gallery_count=253
    def __init__(self):self.calls=[]
    def retrieve_full(self,**kwargs):self.calls.append(kwargs);return ranking()


class DialogueEnCartographicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global PLAN,PARENT,E0_REVIEW
        cls.fixture=tempfile.TemporaryDirectory();PLAN,PARENT,E0_REVIEW=fixture_inputs(Path(cls.fixture.name))
    @classmethod
    def tearDownClass(cls):cls.fixture.cleanup()
    def test_language_v1_reproduces_historical_rejection(self):
        decision=detect_language_v1(HISTORICAL_E0);self.assertFalse(decision["fail_closed_pass"]);self.assertIn("plaza",[x.casefold() for x in decision["spanish_evidence"]])

    def test_language_v2_accepts_shared_word_in_english_context(self):
        decision=detect_language_v2(HISTORICAL_E0);self.assertEqual(decision["decision"],"en");self.assertTrue(decision["fail_closed_pass"]);self.assertIn("plaza",decision["shared_or_cognate_tokens"])

    def test_language_v2_shared_only_is_indeterminate(self):
        for text in ("plaza","PLAZA","(plaza)","hotel patio metro"):
            decision=detect_language_v2(text);self.assertEqual(decision["decision"],"indeterminate");self.assertFalse(decision["fail_closed_pass"])

    def test_language_v2_rejects_spanish_and_mixed(self):
        cases={"Estoy en una plaza rodeada de edificios.":"es","Estoy in a square surrounded by buildings.":"mixed","The persona puede see a monument.":"mixed"}
        for text,expected in cases.items():self.assertEqual(detect_language_v2(text)["decision"],expected)

    def test_language_v2_unicode_and_empty_are_fail_closed(self):
        import unicodedata
        for text in ("", "123",unicodedata.normalize("NFD","Estoy junto a un jardín."),unicodedata.normalize("NFC","Estoy junto a un jardín.")):
            self.assertFalse(detect_language_v2(text)["fail_closed_pass"])

    def test_language_v2_neutral_name_does_not_hide_spanish(self):
        self.assertEqual(detect_language_v2("Estoy cerca de José Ortega.",neutral_spans=("José Ortega",))["decision"],"es")
        self.assertEqual(detect_language_v2("The observer is near José Ortega.",neutral_spans=("José Ortega",))["decision"],"en")

    def test_toponym_is_separate_from_language(self):
        decision=detect_language_v2("Madrid is surrounded by buildings.");self.assertEqual(decision["decision"],"en")
        _,_,rounds=load_plan(PLAN);self.assertIn("toponym_forbidden",{x["code"] for x in validate_output(rounds[0],"Madrid is a square surrounded by buildings.")["issues"]})

    def test_historical_e0_is_eligible_under_v2_but_not_reviewed(self):
        parent=json.loads((PARENT/"queries.json").read_text());row=parent["rounds"][0];spec=FrozenRound(row["round"],row["source_text"],row["source_sha256"],tuple(row["available_turns"]),tuple(row["required_claim_ids"]));v1=validate_output(spec,row["output_text"],language_policy=LANGUAGE_POLICY_V1);v2=validate_output(spec,row["output_text"],language_policy=LANGUAGE_POLICY_V2);self.assertFalse(v1["automatic_checks_passed"]);self.assertTrue(v2["automatic_checks_passed"]);self.assertTrue(v2["human_review_required"]);self.assertEqual(row["review_status"],"rejected")

    def test_frozen_rounds_are_isolated_and_deterministic(self):
        frozen,contract,rounds=load_plan(PLAN);self.assertEqual([x.available_turns for x in rounds],[(),(1,),(1,2),(1,2,3)])
        self.assertEqual([x.required_claim_ids for x in rounds],[(),("claim-001",),("claim-001","claim-002"),("claim-001","claim-002","claim-003")])
        self.assertEqual(build_prompt(contract["prompt_text"],rounds[0]),build_prompt(contract["prompt_text"],rounds[0]));self.assertNotIn("iglesia",rounds[1].source_text);self.assertNotIn("parque",rounds[2].source_text)

    def test_plan_rejects_future_leak_and_hash_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);frozen=json.loads((PLAN/"frozen-inputs.json").read_text());contract=json.loads((PLAN/"query-construction-contract.json").read_text());frozen["round_sources"][1]["text"]+=" parque";frozen["round_sources"][1]["sha256"]=sha256_text(frozen["round_sources"][1]["text"]);(root/"frozen-inputs.json").write_text(json.dumps(frozen));(root/"query-construction-contract.json").write_text(json.dumps(contract))
            with self.assertRaisesRegex(DialogueEnCartographicError,"aislamiento temporal"):load_plan(root)

    def test_valid_outputs_require_human_review(self):
        _,_,rounds=load_plan(PLAN)
        for spec in rounds:
            result=validate_output(spec,VALID[spec.round_id]);self.assertTrue(result["automatic_checks_passed"]);self.assertTrue(result["human_review_required"]);self.assertTrue(result["eligible_for_human_review"])

    def test_visibility_is_not_object_absence(self):
        _,_,rounds=load_plan(PLAN)
        invalid={
            "E1":"The observer is in a square surrounded by buildings. A monument exists.",
            "E2":"The observer is in a square surrounded by buildings. A monument is visible. There is no church in the area.",
            "E3":"The observer is in a square surrounded by buildings. A monument is visible. A church is not visible from the observer's position. There are no parks nearby.",
        }
        for round_id,text in invalid.items():
            result=validate_output(rounds[int(round_id[1])],text);self.assertFalse(result["automatic_checks_passed"]);self.assertTrue(any(row["code"] in {"monument_visibility_invalid","church_visibility_scope_invalid","park_visibility_scope_invalid","object_absence_invented"} for row in result["issues"]))

    def test_rejects_future_claims_toponyms_coordinates_ids_and_spanish(self):
        _,_,rounds=load_plan(PLAN);cases=[
            (rounds[0],VALID["E0"]+" A park is not visible.","future_claim_leakage"),
            (rounds[0],VALID["E0"]+" This is Madrid.","toponym_forbidden"),
            (rounds[0],VALID["E0"]+" Position 40.415481, -3.707355.","coordinates_forbidden"),
            (rounds[0],VALID["E0"]+" Mapillary 145528217588574.","internal_id_forbidden"),
            (rounds[0],VALID["E0"]+" The Alameda is nearby.","new_proper_name"),
            (rounds[0],"Estoy in a square surrounded by buildings.","language_mismatch"),
        ]
        for spec,text,code in cases:self.assertIn(code,{row["code"] for row in validate_output(spec,text)["issues"]})

    def test_empty_malformed_and_omitted_entities_fail(self):
        _,_,rounds=load_plan(PLAN)
        for value in ("",None,"A square is visible.","Buildings surround the observer."):
            self.assertFalse(validate_output(rounds[0],value)["automatic_checks_passed"])

    def test_materializer_calls_four_times_without_retry(self):
        prepared=prepare_query_bundle(PLAN);transformer=Transformer();result=materialize_with_transformer(prepared,transformer,synthetic_fixture=True);self.assertEqual(len(transformer.calls),4);self.assertEqual(result["execution"]["automatic_retries"],0);self.assertEqual(result["status"],"SYNTHETIC_FIXTURE_COMPLETE");self.assertTrue(all(row["review_status"]=="fixture_only" for row in result["rounds"]))

    def test_materializer_stops_after_failure(self):
        outputs=dict(VALID);outputs["E1"]="There is no church in the area.";transformer=Transformer(outputs);result=materialize_with_transformer(prepare_query_bundle(PLAN),transformer,synthetic_fixture=True);self.assertEqual(len(transformer.calls),2);self.assertEqual(result["status"],"GENERATION_REJECTED");self.assertEqual(result["rounds"][2]["review_status"],"not_attempted_after_failure")

    def test_bundle_hash_and_review_validation(self):
        bundle=reviewed_bundle();validate_query_bundle(bundle,require_reviewed=True,require_real=True);tampered=copy.deepcopy(bundle);tampered["rounds"][0]["output_text"]+=" changed"
        with self.assertRaisesRegex(DialogueEnCartographicError,"hash divergente"):validate_query_bundle(tampered,require_reviewed=True,require_real=True)
        leaked=copy.deepcopy(bundle);leaked["rounds"][0]["ground_truth"]={"candidate_id":"fixture"}
        with self.assertRaisesRegex(DialogueEnCartographicError,"señales de evaluación"):validate_query_bundle(leaked,require_reviewed=True,require_real=True)

    def test_clip_audit_passes_and_detects_truncation(self):
        report=audit_clip_tokenization(reviewed_bundle(),tokenizer_without_truncation);self.assertEqual(report["status"],"PASS_NO_TRUNCATION");self.assertEqual(len(report["rows"]),4)
        def truncating(texts,context_length,truncate):
            tensor=tokenizer_without_truncation(texts,context_length,truncate);tensor.values[0][1]=2 if truncate else 1;return tensor
        with self.assertRaisesRegex(DialogueEnCartographicError,"truncamiento"):audit_clip_tokenization(reviewed_bundle(),truncating)

    def test_clip_audit_rejects_overflow_and_missing_eot(self):
        def overflow(*args,**kwargs):raise RuntimeError("too long")
        with self.assertRaisesRegex(DialogueEnCartographicError,"excede contexto"):audit_clip_tokenization(reviewed_bundle(),overflow)
        def no_eot(texts,context_length,truncate):return TokenTensor([[49406]+[1]*(context_length-1)])
        with self.assertRaisesRegex(DialogueEnCartographicError,"EOT"):audit_clip_tokenization(reviewed_bundle(),no_eot)

    def test_fake_retrieval_is_exhaustive_and_has_no_evaluation_inputs(self):
        bundle=reviewed_bundle(real=False);audit={"status":"PASS_NO_TRUNCATION","rows":[{"round":x} for x in ("E0","E1","E2","E3")]};retriever=Retriever();result=retrieve_query_bundle(bundle,retriever,audit,real_model_inference=False);self.assertEqual(len(retriever.calls),4);self.assertEqual(result["status"],"SYNTHETIC_FIXTURE_ONLY");self.assertFalse(result["scientific_result"]);self.assertFalse(result["provenance"]["ground_truth_used"]);self.assertFalse(result["provenance"]["mapillary_used"]);self.assertFalse(result["provenance"]["literal_metrics_used"])

    def test_retrieval_rejects_fake_bundle_in_real_mode(self):
        audit={"status":"PASS_NO_TRUNCATION","rows":[{"round":x} for x in ("E0","E1","E2","E3")]}
        with self.assertRaisesRegex(DialogueEnCartographicError,"inferencia real"):retrieve_query_bundle(reviewed_bundle(real=False),Retriever(),audit,real_model_inference=True)

    def test_ranking_validation_and_comparison(self):
        left=ranking();right=ranking(list(reversed([f"fixture-{i:03d}" for i in range(253)])));same=compare_rankings(left,left);changed=compare_rankings(left,right);self.assertEqual(same["spearman_footrule"],0);self.assertEqual(same["jaccard"],1);self.assertEqual(changed["changed_candidate_count"],252)

    def test_camera_metrics_are_explicitly_exploratory(self):
        value=camera_metrics(ranking(),40.0,-3.0,"fixture-000");self.assertTrue(value["exploratory_point_assignment_only"]);self.assertFalse(value["official_f54_recall"])

    def test_evaluation_compares_e_and_r_and_requires_committed_real_bundle(self):
        e={"status":"COMMITTED","real_model_inference":True,"rankings":[{"round":f"E{i}","ranking":ranking()} for i in range(4)]};reference={"coordinates":{"geometry_original_declared":{"latitude":40.0,"longitude":-3.0},"computed_geometry_mapillary":{"latitude":40.0,"longitude":-3.0}},"spatial_compatibility":{"original_geometry_assignment":{"candidate_id":"fixture-000"}}};result=evaluate_e_vs_r(e,[ranking() for _ in range(4)],reference);self.assertEqual(result["status"],"EXPLORATORY_MAPILLARY_CAMERA_REFERENCE");self.assertFalse(result["official_f54_ground_truth"]);self.assertEqual(len(result["paired_literal_comparisons"]),4)
        e["status"]="SYNTHETIC_FIXTURE_ONLY"
        with self.assertRaisesRegex(DialogueEnCartographicError,"no congelados"):evaluate_e_vs_r(e,[ranking() for _ in range(4)],reference)

    def test_import_and_help_do_not_import_heavy_modules(self):
        code="import sys;import src.tfg_phase0.dialogue_en_cartographic;print(int(any(x in sys.modules for x in ('torch','transformers','clip'))))";result=subprocess.run([sys.executable,"-I","-c",f"import sys;sys.path.insert(0,{str(ROOT)!r});{code}"],capture_output=True,text=True,check=True);self.assertEqual(result.stdout.strip(),"0")
        for script in ("materialize_dialogue_en_cartographic.py","run_dialogue_en_cartographic_ct2l.py","evaluate_dialogue_en_cartographic.py"):
            result=subprocess.run([sys.executable,str(ROOT/"scripts"/script),"--help"],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)

    def test_prepare_cli_does_not_load_models_and_is_reproducible(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            output=Path(tmp)/"prepared";result=subprocess.run([sys.executable,str(ROOT/"scripts/materialize_dialogue_en_cartographic.py"),"--plan-root",str(PLAN),"--output-root",str(output),"--mode","prepare"],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);preflight=json.loads((output/"preflight.json").read_text());queries=json.loads((output/"queries.json").read_text());self.assertFalse(preflight["models_loaded"]);self.assertFalse(preflight["real_model_inference"]);self.assertEqual(queries["status"],"PREPARED_NO_INFERENCE");self.assertTrue(all(row["output_text"] is None for row in queries["rounds"]))

    def test_continuation_prepares_only_e1_e3_with_lineage(self):
        value=prepare_continuation_bundle(PLAN,PARENT,E0_REVIEW);self.assertEqual([x["round"] for x in value["rounds"]],["E1","E2","E3"]);self.assertFalse(value["parent"]["regenerate_historical_rounds"]);self.assertEqual(value["parent"]["historical_E0_output_sha256"],"3d97a4a1966f36ece2755059f47fc2d946efcbbbbc620420d9b107820627aa11");self.assertEqual(value["parent"]["human_review"]["decision"],"APPROVED_WITHOUT_CHANGES")

    def test_continuation_rejects_incompatible_e0_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"review.json";review=json.loads(E0_REVIEW.read_text());review["approved_text"]+=" changed";path.write_text(json.dumps(review))
            with self.assertRaisesRegex(DialogueEnCartographicError,"revisión humana E0 incompatible"):prepare_continuation_bundle(PLAN,PARENT,path)

    def test_continuation_rejects_tampered_parent_and_duplicate_e_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);root.mkdir(exist_ok=True);(root/"queries.json").write_bytes((PARENT/"queries.json").read_bytes());manifest=json.loads((PARENT/"manifest.json").read_text());manifest["files"]["queries.json"]="0"*64;(root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(DialogueEnCartographicError,"parent manifest"):prepare_continuation_bundle(PLAN,root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);query=json.loads((PARENT/"queries.json").read_text());query["rounds"][1]["output_text"]="duplicate";(root/"queries.json").write_text(json.dumps(query));manifest=json.loads((PARENT/"manifest.json").read_text());manifest["files"]["queries.json"]=hashlib.sha256((root/"queries.json").read_bytes()).hexdigest();(root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(DialogueEnCartographicError,"outputs duplicados"):prepare_continuation_bundle(PLAN,root)

    def test_continuation_calls_exactly_three_and_stops_on_failure(self):
        prepared=prepare_continuation_bundle(PLAN,PARENT,E0_REVIEW);transformer=Transformer({"E1":VALID["E1"],"E2":VALID["E2"],"E3":VALID["E3"]},start=1);result=materialize_continuation(prepared,transformer,synthetic_fixture=True);self.assertEqual(len(transformer.calls),3);self.assertEqual(result["status"],"SYNTHETIC_CONTINUATION_COMPLETE");self.assertEqual(result["execution"]["automatic_retries"],0)
        bad=Transformer({"E1":"There is no church in the area.","E2":VALID["E2"],"E3":VALID["E3"]},start=1);failed=materialize_continuation(prepared,bad,synthetic_fixture=True);self.assertEqual(len(bad.calls),1);self.assertEqual(failed["rounds"][1]["review_status"],"not_attempted_after_failure")

    def test_continuation_can_stop_at_e2(self):
        prepared=prepare_continuation_bundle(PLAN,PARENT,E0_REVIEW);bad=Transformer({"E1":VALID["E1"],"E2":"There is no church in the area.","E3":VALID["E3"]},start=1);failed=materialize_continuation(prepared,bad,synthetic_fixture=True);self.assertEqual(len(bad.calls),2);self.assertEqual(failed["rounds"][2]["review_status"],"not_attempted_after_failure")

    def test_compose_preserves_e0_and_accounts_two_loads(self):
        prepared=prepare_continuation_bundle(PLAN,PARENT,E0_REVIEW);result=materialize_continuation(prepared,Transformer({"E1":VALID["E1"],"E2":VALID["E2"],"E3":VALID["E3"]},start=1),synthetic_fixture=True)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"queries.json").write_text(json.dumps(result));manifest={"status":"committed","files":{"queries.json":hashlib.sha256((root/"queries.json").read_bytes()).hexdigest()}};(root/"manifest.json").write_text(json.dumps(manifest));composed=compose_query_bundle(PARENT,root,E0_REVIEW);self.assertEqual([x["round"] for x in composed["rounds"]],["E0","E1","E2","E3"]);self.assertEqual(composed["rounds"][0]["output_sha256"],"3d97a4a1966f36ece2755059f47fc2d946efcbbbbc620420d9b107820627aa11");self.assertEqual(composed["execution_summary"]["campaign_totals"],{"model_loads":1,"calls":4,"automatic_retries":0,"generations_per_round":1});self.assertFalse(composed["execution_summary"]["single_load_for_all_rounds"]);self.assertEqual(composed["rounds"][0]["review_status"],"reviewed");self.assertEqual(composed["lineage"]["e0_human_review"]["decision"],"APPROVED_WITHOUT_CHANGES")

    def test_compose_rejects_incomplete_or_duplicate_continuation(self):
        prepared=prepare_continuation_bundle(PLAN,PARENT,E0_REVIEW);result=materialize_continuation(prepared,Transformer({"E1":VALID["E1"],"E2":VALID["E2"],"E3":VALID["E3"]},start=1),synthetic_fixture=True)
        for mutate in (lambda rows:rows.pop(),lambda rows:rows.__setitem__(2,{**rows[2],"round":"E2"})):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);value=copy.deepcopy(result);mutate(value["rounds"]);(root/"queries.json").write_text(json.dumps(value));(root/"manifest.json").write_text(json.dumps({"status":"committed","files":{"queries.json":hashlib.sha256((root/"queries.json").read_bytes()).hexdigest()}}))
                with self.assertRaisesRegex(DialogueEnCartographicError,"continuación incompleta"):compose_query_bundle(PARENT,root,E0_REVIEW)

    def test_continuation_cli_rejects_v1_authorization_before_model_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            authorization=Path(tmp)/"authorization.json";authorization.write_text(json.dumps({"contract_version":"dialogue-v3-en-cartographic-qwen-authorization-v1"}));code=f"from pathlib import Path;import scripts.continue_dialogue_en_cartographic as c;c._authorization(Path({str(authorization)!r}),Path({str(PLAN)!r}),Path({str(PARENT)!r}),Path({str(E0_REVIEW)!r}),Path('/tmp/new-output'),Path('/nonexistent-model'))"
            result=subprocess.run([sys.executable,"-c",code],cwd=ROOT,capture_output=True,text=True);self.assertNotEqual(result.returncode,0);self.assertIn("autorización de continuación incompatible",result.stderr)

    def test_continuation_prepare_cli_and_existing_output_guard(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            output=Path(tmp)/"continuation";command=[sys.executable,str(ROOT/"scripts/continue_dialogue_en_cartographic.py"),"prepare","--plan-root",str(PLAN),"--parent-root",str(PARENT),"--e0-review",str(E0_REVIEW),"--output-root",str(output)];first=subprocess.run(command,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stderr);second=subprocess.run(command,capture_output=True,text=True);self.assertNotEqual(second.returncode,0);self.assertIn("output-root ya existe",second.stderr)


if __name__=="__main__":unittest.main()
