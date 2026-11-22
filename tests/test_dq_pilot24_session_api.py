from pathlib import Path
from fastapi.testclient import TestClient
from backend.atlas_api.dq_iterative_sessions import IterativeDialogueSessionService,POLICY_ID
from backend.atlas_api.main import create_app
from backend.atlas_api.settings import Settings
from research.dq_pilot_iterative_controller_v1 import IterativeDialogueController
from research.dq_pilot_real_adapters_v1 import RealTextInterpreterAdapter,RealCT2LRetrieverAdapter
from tests.test_dq_pilot23_iterative_integration import QwenPort,CT2LPort,Panel,Questioner,Validator,Translator

class FakeRetriever:
 ephemeral=True;gallery_ids=("madrid-50m",)
 def gallery_count(self,gallery_id):return 253
 def close(self):pass

def fixture(tmp_path):
 def factory(session_id,description):
  qwen=QwenPort();ct2l=CT2LPort();interpreter=RealTextInterpreterAdapter(qwen);retriever=RealCT2LRetrieverAdapter(ct2l,query_id=session_id,visual_dataset_id="visual-v1",embedding_dataset_id="embedding-v1");panel=Panel();questioner=Questioner();validator=Validator();translator=Translator();controller=IterativeDialogueController(interpreter=interpreter,retriever=retriever,panel=panel,questioner=questioner,validator=validator,translator=translator,top_n=20);identities={"interpreter":interpreter.identity,"retriever":retriever.identity,"questioner":questioner.identity,"translator":translator.identity};return controller,identities
 service=IterativeDialogueSessionService(session_root=tmp_path/"dq-sessions",controller_factory=factory,enabled=True,real_inference_available=True,translation_available=True,quality_gate_available=True)
 settings=Settings(Path("runtime"),Path("config/madrid.yaml"),"a"*64,"clip",())
 return create_app(settings=settings,retriever_factory=lambda _:FakeRetriever(),transformer_factory=lambda _:None,dq_iterative_service=service),service

def start(operation="dq-start-1"):
 return {"schema_version":"1.0","contract_version":"atlas-dialogue-freetext-start-request-v2","policy_id":POLICY_ID,"description_es":"Estoy junto a una plaza y veo una torre.","client_operation_id":operation}
def answer(question,literal="Respuesta humana literal.",operation="dq-answer-1",stop=False):
 return {"schema_version":"1.0","contract_version":"atlas-dialogue-freetext-answer-request-v2","turn_index":question["turn_index"],"question_id":question["question_id"],"question_sha256":question["question_sha256"],"answer_literal":literal,"human_attested":True,"external_context_used":False,"client_operation_id":operation,"user_requests_stop":stop}

def test_session_api_updates_ranking_binds_answer_and_stops_after_final_retrieval(tmp_path):
 app,service=fixture(tmp_path)
 with TestClient(app) as client:
  catalogue=client.get("/api/v1/dialogue-freetext/policies").json();assert next(row for row in catalogue["policies"] if row["policy_id"]==POLICY_ID)["available"] is True
  response=client.post("/api/v1/dialogue-freetext/sessions",json=start(),headers={"Idempotency-Key":"dq-start-1"});assert response.status_code==200;session_id=response.json()["session_id"]
  session=client.get(f"/api/v1/dialogue-freetext/sessions/{session_id}").json();assert session["status"]=="waiting_user";assert session["stage_snapshots"][0]["candidate_count"]==253 and len(session["stage_snapshots"][0]["results"])==10
  repeated=client.post("/api/v1/dialogue-freetext/sessions",json=start(),headers={"Idempotency-Key":"dq-start-1"});assert repeated.json()["session_id"]==session_id
  stale=answer({**session["current_question"],"question_sha256":"0"*64},operation="dq-stale");assert client.post(f"/api/v1/dialogue-freetext/sessions/{session_id}/answers",json=stale,headers={"Idempotency-Key":"dq-stale"}).status_code==409
  payload=answer(session["current_question"]);accepted=client.post(f"/api/v1/dialogue-freetext/sessions/{session_id}/answers",json=payload,headers={"Idempotency-Key":"dq-answer-1"});assert accepted.status_code==200
  session=client.get(f"/api/v1/dialogue-freetext/sessions/{session_id}").json();assert [row["stage"] for row in session["stage_snapshots"]]==["E0","E1"] and session["turns"][0]["answer_literal"]=="Respuesta humana literal."
  duplicate=client.post(f"/api/v1/dialogue-freetext/sessions/{session_id}/answers",json=payload,headers={"Idempotency-Key":"dq-answer-1"});assert duplicate.status_code==200 and len(duplicate.json()["stage_snapshots"])==2
  stop_payload=answer(session["current_question"],literal="Quiero terminar el diálogo.",operation="dq-stop-2",stop=True);stopped=client.post(f"/api/v1/dialogue-freetext/sessions/{session_id}/stop",json=stop_payload,headers={"Idempotency-Key":"dq-stop-2"});assert stopped.status_code==200
  final=client.get(f"/api/v1/dialogue-freetext/sessions/{session_id}").json();assert final["status"]=="completed" and final["stop_reason"]=="human_requested_stop_after_updated_retrieval";assert [row["stage"] for row in final["stage_snapshots"]]==["E0","E1","E2"] and final["current_question"] is None
  assert not (service._path(session_id)/"run/rounds/round-2/mapillary-panel.json").exists()
  assert all("raw_output" not in str(value) and "think" not in str(value) for value in final.values())

def test_blocked_policy_is_visible_but_cannot_start(tmp_path):
 service=IterativeDialogueSessionService(session_root=tmp_path/"blocked",enabled=True,controller_factory=lambda *_:None,real_inference_available=False,translation_available=False,quality_gate_available=False)
 settings=Settings(Path("runtime"),Path("config/madrid.yaml"),"a"*64,"clip",())
 app=create_app(settings=settings,retriever_factory=lambda _:FakeRetriever(),transformer_factory=lambda _:None,dq_iterative_service=service)
 with TestClient(app) as client:
  policy=next(row for row in client.get("/api/v1/dialogue-freetext/policies").json()["policies"] if row["policy_id"]==POLICY_ID);assert policy["available"] is False and all(policy["blockers"].values())
  response=client.post("/api/v1/dialogue-freetext/sessions",json=start(),headers={"Idempotency-Key":"dq-start-1"});assert response.status_code==503
  prepared=client.post("/api/v1/dialogue-freetext/iterative/preparations",json=start("prepare-only-1"),headers={"Idempotency-Key":"prepare-only-1"});assert prepared.status_code==200;body=prepared.json();assert body["status"]=="waiting_authorization" and body["stage_snapshots"]==[] and body["gpu_used"] is False and body["rankings_available"] is False
  cancelled=client.post(f"/api/v1/dialogue-freetext/sessions/{body['session_id']}/cancel",json={"client_operation_id":"cancel-only-1","reason":"user_cancelled_incomplete_description"});assert cancelled.status_code==200 and cancelled.json()["status"]=="cancelled"
