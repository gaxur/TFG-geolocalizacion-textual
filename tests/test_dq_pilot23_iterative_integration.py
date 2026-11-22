import hashlib,json
from pathlib import Path
import pytest
from research.dq_pilot_iterative_controller_v1 import IterativeDialogueController,IterativeRunStore,digest
from research.dq_pilot_real_adapters_v1 import RealTextInterpreterAdapter,RealCT2LRetrieverAdapter
from research.dq_pilot23_integration_v1 import build_iterative_pipeline,prepare_iterative_run

class QwenPort:
 def __init__(self):self.calls=[]
 def transform(self,*,stage,transcript,prompt):
  self.calls.append((stage,transcript,prompt));text=f"English accumulated cartographic description {stage}."
  return {"schema_version":"1.0","contract_version":"atlas-dialogue-freetext-en-v1","stage":stage,"transcript_sha256":hashlib.sha256(transcript.encode()).hexdigest(),"prompt_version":"dialogue-vpr-freetext-qwen-v1","prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),"text":text,"raw_output":text,"text_sha256":hashlib.sha256(text.encode()).hexdigest(),"duration_ms":1,"model":{"model_id":"Qwen/Qwen3-8B","revision":"b968826d9c46dd6066d109eabc6255188de91218","artifact_manifest_sha256":"d95b2ee5a666c88adcb53094740c1002718f28e0dcabad56a508a9c66dce1570","real_model_inference":True}}
class CT2LPort:
 def __init__(self):self.calls=[]
 def retrieve(self,*,stage,query_id,text):
  self.calls.append((stage,query_id,text));round_index=int(stage[1:]);order=list(range(1,254));order=order[round_index:]+order[:round_index];results=[{"rank":rank,"candidate_id":f"c{candidate:03d}","latitude":40+candidate/100000,"longitude":-3.7,"cosine_similarity":1-rank/1000-round_index/10000} for rank,candidate in enumerate(order,1)];ranking={"gallery_id":"madrid-50m","gallery_count":253,"requested_k":253,"effective_k":253,"ranking_method":"exhaustive_cosine","tie_break":"candidate_id_ascending","visual_dataset_id":"visual-v1","embedding_dataset_id":"embedding-v1","results":results};return {"contract_version":"crosstext2loc-retrieval-response-v1","query":{"query_id":query_id,"text":text,"language":"en"},"model":{"name":"CLIP-L/14@336","checkpoint_sha256":"d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d"},"retrievals":[ranking],"timings_ms":{"total":1}}
class Panel:
 def __init__(self):self.calls=[]
 def build(self,*,round_index,ranking,reserve):
  ids=[row["candidate_id"] for row in reserve[:4]];self.calls.append((round_index,ids));return {"contract_version":"fixture-dynamic-real-panel-v1","status":"ready","review_required":False,"round_index":round_index,"source_ranking_sha256":digest(ranking),"candidate_ids":ids,"candidates":[{"candidate_ref":f"C{i}","candidate_id":cid} for i,cid in enumerate(ids,1)],"images":[{"candidate_ref":f"C{i}","image_ref":f"I{i}","image_id":f"round-{round_index}-image-{i}","sha256":hashlib.sha256(f"round-{round_index}-image-{i}".encode()).hexdigest(),"size_bytes":10} for i in range(1,5)],"ground_truth_used":False}
class Questioner:
 identity={"adapter_id":"fixture-private-questioner-v1"}
 def __init__(self,reject_round=None):self.calls=[];self.reject_round=reject_round
 def generate(self,*,round_index,panel,**kwargs):
  self.calls.append((round_index,list(panel["candidate_ids"])))
  if round_index==self.reject_round:return {"contract_version":"dq-pilot14-public-generation-v1","status":"host_rejected","question":None,"request_sha256":"a"*64,"panel_sha256":digest(panel),"source_ranking_sha256":panel["source_ranking_sha256"],"private_output_retained":True,"reasoning_public":False,"host_validation":{"status":"rejected","reason_codes":["question:internal_reference"]},"host_decision_sha256":"b"*64,"terminal_commit_sha256":"c"*64,"ground_truth_used":False}
  question=f"Is stable feature {round_index+1} visible?";return {"contract_version":"dq-pilot14-public-generation-v1","status":"generated","question":question,"request_sha256":"a"*64,"panel_sha256":digest(panel),"source_ranking_sha256":panel["source_ranking_sha256"],"raw_output_sha256":hashlib.sha256(question.encode()).hexdigest(),"private_output_retained":True,"private_output_sha256":"d"*64,"reasoning_public":False,"host_validation":{"format":True,"text_safety":True,"exact_redundancy":True},"telemetry_sha256":"e"*64,"ground_truth_used":False}
class Validator:
 identity={"adapter_id":"fixture-host-validator-v1"}
 def validate(self,*,panel,generation,**kwargs):
  return {"contract_version":"fixture-validation-v1","status":"invalid" if generation["status"]=="host_rejected" else "valid","question":generation.get("question"),"generation_sha256":digest(generation),"panel_sha256":digest(panel),"automatic_approval":False,"ground_truth_used":False}
class Translator:
 identity={"translator_id":"fixture-en-es","version":"1.0","artifact_manifest_sha256":"f"*64,"runtime":"cpu-fixture","local":True,"cpu_fixture_auto_review":True}
 def __init__(self,reject_round=None):self.calls=[];self.reject_round=reject_round
 def translate(self,*,round_index,question):
  self.calls.append(round_index)
  if round_index==self.reject_round:return {"schema_version":"1.0","contract_version":"dq-pilot-translation-result-v1","status":"rejected","round_index":round_index}
  translated=f"¿Está visible el rasgo estable {round_index+1}?";return {"schema_version":"1.0","contract_version":"dq-pilot-translation-result-v1","status":"translated_pending_human_review","round_index":round_index,"source_language":"en","target_language":"es","source_question":question,"source_question_sha256":hashlib.sha256(question.encode()).hexdigest(),"translated_question":translated,"translated_question_sha256":hashlib.sha256(translated.encode()).hexdigest(),"translator":dict(self.identity),"semantic_repair_performed":False,"automatic_retries":0,"fallback_used":False,"network_used":False,"validation":{"structural":"passed","semantic":"pending_human_review","source_question_preserved":True,"human_review_required":True}}
def setup(tmp_path,*,reject_question_round=None,reject_translation_round=None):
 qwen=QwenPort();ct=CT2LPort();interpreter=RealTextInterpreterAdapter(qwen);retriever=RealCT2LRetrieverAdapter(ct,query_id="TECH-ITERATIVE",visual_dataset_id="visual-v1",embedding_dataset_id="embedding-v1");panel=Panel();questioner=Questioner(reject_question_round);validator=Validator();translator=Translator(reject_translation_round);controller=IterativeDialogueController(interpreter=interpreter,retriever=retriever,panel=panel,questioner=questioner,validator=validator,translator=translator,top_n=20);store=IterativeRunStore.prepare(tmp_path/"run",session_id="cpu-integration",query_id="TECH-ITERATIVE",original_description="Descripción original literal.",top_n=20,identities={"interpreter":interpreter.identity,"retriever":retriever.identity,"questioner":questioner.identity,"translator":translator.identity});return controller,store,(qwen,ct,panel,questioner,translator)
def test_three_questions_four_full_retrievals_dynamic_panels_and_final_no_panel(tmp_path):
 controller,store,ports=setup(tmp_path);state=controller.start(store);assert state["controller_state"]=="AWAITING_USER"
 for answer in ("Respuesta ficticia de software uno.","Respuesta ficticia de software dos.","Respuesta ficticia de software tres."):state=controller.answer(store,answer_literal=answer)
 assert state["controller_state"]=="COMPLETED" and state["questions_asked"]==3 and [x["round_index"] for x in state["rounds"]]==[0,1,2,3]
 assert len(ports[0].calls)==len(ports[1].calls)==4 and len(ports[2].calls)==len(ports[3].calls)==3 and len(ports[4].calls)==3
 assert len({tuple(ids) for _,ids in ports[2].calls})==3 and not (store.root/"rounds/round-3/mapillary-panel.json").exists()
 for index in range(4):
  ranking=json.loads((store.root/f"rounds/round-{index}/ct2l-ranking.json").read_text());reserve=json.loads((store.root/f"rounds/round-{index}/top-n-reserve.json").read_text());assert len(ranking["results"])==253 and len(reserve["results"])==20 and reserve["source_ranking_sha256"]==digest(ranking)
 assert [line.split(":",1)[0] for line in state["accumulated_description"].splitlines() if line.startswith("Respuesta ")]==["Respuesta 1","Respuesta 2","Respuesta 3"] and all(turn["answer"]["synthetic"] is False for turn in state["turns"])
def test_host_rejection_stops_with_latest_ranking_and_no_translation(tmp_path):
 controller,store,ports=setup(tmp_path,reject_question_round=1);controller.start(store);state=controller.answer(store,answer_literal="Respuesta ficticia software.");assert state["controller_state"]=="COMPLETED" and state["stop_reason"]=="question_invalid_or_abstained" and state["rounds"][-1]["round_index"]==1 and ports[4].calls==[0]
 generation=json.loads((store.root/"rounds/round-1/dq-generation.json").read_text());assert "raw_output" not in generation and generation["reasoning_public"] is False
def test_translation_rejection_stops_before_user_and_preserves_ranking(tmp_path):
 controller,store,ports=setup(tmp_path,reject_translation_round=0);state=controller.start(store);assert state["controller_state"]=="COMPLETED" and state["stop_reason"]=="translation_rejected_before_user_presentation" and state["questions_asked"]==0 and state["turns"]==[] and state["rounds"][-1]["round_index"]==0
def test_human_stop_executes_second_full_retrieval_without_panel(tmp_path):
 controller,store,ports=setup(tmp_path);controller.start(store);state=controller.answer(store,answer_literal="Respuesta ficticia: terminar.",user_requests_stop=True);assert state["controller_state"]=="COMPLETED" and state["stop_reason"]=="human_requested_stop_after_updated_retrieval" and len(ports[1].calls)==2 and len(ports[2].calls)==1 and not (store.root/"rounds/round-1/mapillary-panel.json").exists()
def test_resume_at_awaiting_user_repeats_nothing(tmp_path):
 controller,store,ports=setup(tmp_path);controller.start(store);before=tuple(len(port.calls) for port in ports);controller.resume(store);assert tuple(len(port.calls) for port in ports)==before
def test_controller_rejects_public_generation_with_think(tmp_path):
 controller,store,ports=setup(tmp_path)
 def leaking(**kwargs):
  panel=kwargs["panel"];return {"status":"generated","question":"Q?","raw_output":"<think>secret</think>","panel_sha256":digest(panel),"source_ranking_sha256":panel["source_ranking_sha256"],"private_output_retained":False,"reasoning_public":True}
 controller.questioner.generate=leaking
 with pytest.raises(Exception,match="raw/think"):controller.start(store)
def test_real_factory_defaults_to_unavailable_translation_and_reuses_one_retriever(tmp_path):
 controller,identities=build_iterative_pipeline(qwen_port=QwenPort(),retrieval_port=CT2LPort(),query_id="TECH-FACTORY",visual_dataset_id="visual-v1",embedding_dataset_id="embedding-v1",catalog={"candidates":[]},inventory={"images":[]},cache_root=tmp_path,original_description="Original",session_id="factory",outcome_schema={"type":"object"})
 assert identities["translator"]["status"]=="TRANSLATION_UNAVAILABLE" and identities["retriever"]["candidate_count"]==253
 store=prepare_iterative_run(tmp_path/"factory-run",controller=controller,identities=identities,session_id="factory",query_id="TECH-FACTORY",original_description="Original");configuration=json.loads((store.root/"configuration.json").read_text());assert configuration["identities"]==identities and configuration["ground_truth_permitted"] is False
