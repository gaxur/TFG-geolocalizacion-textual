import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone,timedelta

from fastapi.testclient import TestClient

from backend.atlas_api.freetext_operational import OperationalFreeTextSessionService
from backend.atlas_api.main import create_app
from backend.atlas_api.settings import Settings
from backend.atlas_api.dialogue_sessions import canonical
from src.tfg_phase0.dialogue_freetext_v1 import FreeTextDialogueExecutor, FreeTextQuestion


def ranking(offset=0):
    return {"gallery_id": "madrid-50m", "gallery_count": 253, "requested_k": 253, "effective_k": 253, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "results": [{"rank": index, "candidate_id": f"c{index:03d}", "latitude": 40 + index / 10000, "longitude": -3.0, "cosine_similarity": 1 - index / 1000 - offset / 10000} for index in range(1, 254)]}


class Questions:
    def select(self, **kwargs):
        index = len(kwargs["turns"]) + 1
        return FreeTextQuestion(f"q{index}", f"f{index}", "open_spatial", f"Pregunta {index}", "test", (), (), (), (1,), {}), {"selected_intent_key": f"q{index}"}


class Qwen:
    def __init__(self, owner): self.owner = owner
    def transform(self, **kwargs):
        self.owner.qwen_calls.append(kwargs["stage"]); self.owner.emit(kwargs["stage"], "qwen", "running"); self.owner.emit(kwargs["stage"], "qwen", "completed")
        text = f"EN {kwargs['stage']}"
        return {"text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "model_id": "fake-qwen", "prompt_sha256": hashlib.sha256(kwargs["prompt"].encode()).hexdigest()}


class Retriever:
    def __init__(self, owner): self.owner = owner
    def retrieve(self, **kwargs):
        self.owner.ct2l_calls.append(kwargs["stage"]); self.owner.emit(kwargs["stage"], "crosstext2loc", "running"); self.owner.emit(kwargs["stage"], "crosstext2loc", "completed")
        return ranking(len(self.owner.ct2l_calls))


class Executor:
    identity = {"runtime": "fake", "model": "fake-qwen", "retriever": "fake-ct2l"}
    def __init__(self):
        self.progress_callback = None; self.qwen_calls = []; self.ct2l_calls = []
        self.core = FreeTextDialogueExecutor(qwen=Qwen(self), retriever=Retriever(self), questions=Questions())
    def emit(self, stage, component, status):
        if self.progress_callback: self.progress_callback(stage, component, status)
    def start(self, *, query_id, description, session_root): return self.core.start(query_id=query_id, description=description)
    def answer(self, *, state, answer, answer_kind, session_root): return self.core.answer(state=state, answer_literal=answer)


class FakeRetriever:
    ephemeral = True
    gallery_ids = ("madrid-50m",)
    def gallery_count(self, gallery_id): return 253
    def close(self): pass

POLICY={"operational_policy_id":"dialogue-vpr-freetext-v1-operational","operational_policy_version":"1.0.0","operational_policy_sha256":"a"*64,"core_policy_id":"dialogue-vpr-freetext-v1","core_policy_version":"1.0.0","core_policy_sha256":"b"*64}

def authorize(root,executor,execution_id="exec-1",description="Estoy junto a una plaza y veo una torre a mi derecha."):
    now=datetime.now(timezone.utc);identity=executor.identity;root.mkdir(parents=True,exist_ok=True);document={"schema_version":"1.0","contract_version":"atlas-dialogue-freetext-operational-authorization-v1","authorization_id":"auth-1","execution_id":execution_id,"status":"OPERATOR_AUTHORIZED","approved":True,"approved_at":(now-timedelta(minutes=2)).isoformat().replace('+00:00','Z'),"valid_from":(now-timedelta(minutes=1)).isoformat().replace('+00:00','Z'),"expires_at":(now+timedelta(hours=1)).isoformat().replace('+00:00','Z'),"description_sha256":hashlib.sha256(description.encode()).hexdigest(),**POLICY,"executor_identity":identity,"executor_identity_sha256":hashlib.sha256(canonical(identity)).hexdigest(),"scope":{"session_count":1,"stages":["E0","E1","E2","E3"]},"budgets":{"maximum_qwen_loads":4,"maximum_qwen_calls":4,"maximum_ct2l_loads":4,"maximum_ct2l_calls":4,"maximum_questions":3,"automatic_retries":0},"constraints":{"ground_truth_permitted":False,"vlm_permitted":False,"h38_h61_permitted":False,"references_permitted":False,"network_permitted":False},"reusable_for_other_session":False};(root/f'{execution_id}.json').write_text(json.dumps(document));return root


def app_fixture(tmp_path):
    executor = Executor()
    auth=authorize(tmp_path/'auth',executor)
    service = OperationalFreeTextSessionService(session_root=tmp_path / "sessions", executor=executor, enabled=True, authorization_root=auth, policy_identity=POLICY, execution_id='exec-1')
    settings = Settings(Path("runtime"), Path("config/madrid.yaml"), "a" * 64, "clip", ())
    app = create_app(settings=settings, retriever_factory=lambda _: FakeRetriever(), transformer_factory=lambda _: None, freetext_operational_service=service)
    return app, service, executor


def start_payload(description="Estoy junto a una plaza y veo una torre a mi derecha.", operation="create-1"):
    return {"schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-start-request-v2", "policy_id": "dialogue-vpr-freetext-v1-operational", "description_es": description, "client_operation_id": operation}


def answer_payload(answer, question, operation):
    return {"schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-answer-request-v2", "turn_index": question["turn_index"], "question_id": question["question_id"], "question_sha256": question["question_sha256"], "answer_literal": answer, "human_attested": True, "external_context_used": False, "client_operation_id": operation}


def test_arbitrary_description_idempotency_e0_e3_and_recreate(tmp_path):
    app, service, executor = app_fixture(tmp_path)
    with TestClient(app) as client:
        first = client.post("/api/v1/dialogue-freetext/sessions", json=start_payload(), headers={"Idempotency-Key": "create-1"})
        assert first.status_code == 200; pending = first.json(); session_id = pending["session_id"]; assert pending["status"] in {"pending","waiting_user"}; session=client.get(f"/api/v1/dialogue-freetext/sessions/{session_id}").json()
        repeated = client.post("/api/v1/dialogue-freetext/sessions", json=start_payload(), headers={"Idempotency-Key": "create-1"})
        assert repeated.json()["session_id"] == session_id
        conflict = client.post("/api/v1/dialogue-freetext/sessions", json=start_payload("Otra descripción arbitraria."), headers={"Idempotency-Key": "create-1"})
        assert conflict.status_code == 503
        for index in range(1, 4):
            payload = answer_payload(f"Respuesta {index}", session["current_question"], f"answer-{index}")
            response = client.post(f"/api/v1/dialogue-freetext/sessions/{session_id}/answers", json=payload, headers={"Idempotency-Key": f"answer-{index}"})
            assert response.status_code == 200
            duplicate = client.post(f"/api/v1/dialogue-freetext/sessions/{session_id}/answers", json=payload, headers={"Idempotency-Key": f"answer-{index}"})
            assert duplicate.status_code == 200
            session = client.get(f"/api/v1/dialogue-freetext/sessions/{session_id}").json()
        final = session
        assert final["status"] == "completed" and [row["stage"] for row in final["stage_snapshots"]] == ["E0", "E1", "E2", "E3"] and "stages" not in final
        assert executor.qwen_calls == executor.ct2l_calls == ["E0", "E1", "E2", "E3"]
        recreated = OperationalFreeTextSessionService(session_root=tmp_path / "sessions", executor=executor, enabled=True, authorization_root=tmp_path/'auth', policy_identity=POLICY, execution_id='exec-1')
        assert recreated.load(session_id)["status"] == "completed"


def test_event_contract_history_sse_replay_and_capabilities(tmp_path):
    app, service, _ = app_fixture(tmp_path)
    with TestClient(app) as client:
        pending = client.post("/api/v1/dialogue-freetext/sessions", json=start_payload(operation="events"), headers={"Idempotency-Key": "events"}).json(); session=client.get(f"/api/v1/dialogue-freetext/sessions/{pending['session_id']}").json()
        history = client.get(f"/api/v1/dialogue-freetext/sessions/{session['session_id']}/events").json()["events"]
        assert history and all(set(row) == {"session_id", "event_id", "stage", "status", "timestamp", "message", "error"} for row in history)
        assert {row["status"] for row in history} <= {"pending", "running", "waiting_user", "completed", "failed", "unknown"}
        replay = client.get(f"/api/v1/dialogue-freetext/sessions/{session['session_id']}/events/stream?follow=false", headers={"Last-Event-ID": "2"})
        assert replay.status_code == 200 and "id: 1\n" not in replay.text and "event: session" in replay.text
        policies = client.get("/api/v1/dialogue-freetext/pilots").json()["policies"]
        assert any(row["policy_id"] == "dialogue-vpr-freetext-v1-operational" and row["requires_image"] is False for row in policies)
        capabilities = client.get("/api/v1/capabilities").json()
        assert any(row["policy_id"] == "dialogue-vpr-freetext-v1-operational" for row in capabilities["freetext_policies"])


def test_startup_reconciliation_marks_running_unknown_without_execution(tmp_path):
    service = OperationalFreeTextSessionService(session_root=tmp_path / "sessions", executor=Executor(), enabled=True)
    session_id = "freetext-operational-00000000-0000-0000-0000-000000000001"
    document = {"schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-operational-session-v1", "session_id": session_id, "policy_id": "dialogue-vpr-freetext-v1-operational", "description_es": "Descripción", "description_sha256": hashlib.sha256(b"Descripci\xc3\xb3n").hexdigest(), "status": "running", "stop_reason": None, "state": {"status": "running", "turns": [], "stages": []}, "events": [], "latency_ms": {"transitions": [], "total": 0.0}, "executor_identity": {}, "created_at": "2026-01-01T00:00:00Z", "expires_at": "2099-01-01T00:00:00Z"}
    service._persist(document)
    executor = Executor(); recreated = OperationalFreeTextSessionService(session_root=tmp_path / "sessions", executor=executor, enabled=True)
    reconciled = recreated.load(session_id)
    assert reconciled["status"] == "unknown" and reconciled["events"][-1]["status"] == "unknown"
    assert executor.qwen_calls == executor.ct2l_calls == []

def test_prepare_returns_pending_before_executor_and_run_advances_once(tmp_path):
    description='Descripción libre de una plaza.';executor=Executor();auth=authorize(tmp_path/'auth',executor,description=description);service=OperationalFreeTextSessionService(session_root=tmp_path/'sessions',executor=executor,enabled=True,authorization_root=auth,policy_identity=POLICY,execution_id='exec-1');document,execute=service.prepare_start(description,'prepare-1','prepare-1');assert execute is True and document['status']=='pending';assert executor.qwen_calls==executor.ct2l_calls==[];finished=service.run_start(document['session_id']);assert finished['status']=='waiting_user';assert executor.qwen_calls==executor.ct2l_calls==['E0'];same,execute=service.prepare_start(description,'prepare-1','prepare-1');assert execute is False and same['session_id']==document['session_id'];assert executor.qwen_calls==['E0']

def test_operational_mode_readiness_uses_sequential_workers_without_resident_retriever(tmp_path):
    executor=Executor();auth=authorize(tmp_path/'auth',executor);service=OperationalFreeTextSessionService(session_root=tmp_path/'sessions',executor=executor,enabled=True,authorization_root=auth,policy_identity=POLICY,execution_id='exec-1');settings=Settings(Path('runtime'),Path('config/madrid.yaml'),'a'*64,'clip',(),freetext_operational_enabled=True,freetext_operational_session_root=tmp_path/'sessions',freetext_operational_authorization_root=auth,freetext_operational_execution_id='exec-1');calls=[]
    app=create_app(settings=settings,retriever_factory=lambda _:(calls.append('resident-retriever') or FakeRetriever()),transformer_factory=lambda _:(calls.append('resident-qwen') or None),freetext_operational_service=service,operational_retriever_factory=lambda _:(calls.append('ephemeral-retriever') or FakeRetriever()),operational_transformer_factory=lambda _:(calls.append('ephemeral-qwen') or None))
    with TestClient(app) as client:
        ready=client.get('/api/v1/health/ready');assert ready.status_code==200;assert ready.json()['runtime']=='ephemeral-sequential-workers';capabilities=client.get('/api/v1/capabilities').json();assert capabilities['retrievers'][0]['available'] is True;assert capabilities['galleries']==[{'gallery_id':'madrid-50m','candidate_count':253}];assert any(row['policy_id']=='dialogue-vpr-freetext-v1-operational' and row['available'] for row in capabilities['freetext_policies'])
    assert calls==['ephemeral-retriever','ephemeral-qwen']

def test_expired_session_returns_410_without_execution(tmp_path):
    description='Descripción que expira.';executor=Executor();auth=authorize(tmp_path/'auth',executor,description=description);service=OperationalFreeTextSessionService(session_root=tmp_path/'sessions',executor=executor,enabled=True,authorization_root=auth,policy_identity=POLICY,execution_id='exec-1');settings=Settings(Path('runtime'),Path('config/madrid.yaml'),'a'*64,'clip',());app=create_app(settings=settings,retriever_factory=lambda _:FakeRetriever(),transformer_factory=lambda _:None,freetext_operational_service=service);document,_=service.prepare_start(description,'expire-1','expire-1');stored=service.load(document['session_id']);stored['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat().replace('+00:00','Z');service._persist(stored)
    with TestClient(app) as client:
        response=client.get(f"/api/v1/dialogue-freetext/sessions/{document['session_id']}");assert response.status_code==410;assert response.json()['detail']['code']=='FREETEXT_EXPIRED'
    assert executor.qwen_calls==executor.ct2l_calls==[]

def test_unified_app_serves_description_variants(tmp_path):
    manifest=tmp_path/'variants.json';manifest.write_text(json.dumps({'schema_version':'1.0','contract_version':'description-length-experiments-v1','variant_count':1,'condition_count':0,'variants':[{'variant_id':'H27-medium'}],'conditions':[]}));settings=Settings(Path('runtime'),Path('config/madrid.yaml'),'a'*64,'clip',(),dialogue_variants_path=manifest);app=create_app(settings=settings,retriever_factory=lambda _:FakeRetriever(),transformer_factory=lambda _:None)
    with TestClient(app) as client:response=client.get('/api/v1/dialogue/variants');assert response.status_code==200;assert response.json()['variants'][0]['variant_id']=='H27-medium'

def test_operational_service_without_authorization_fails_before_any_activity(tmp_path):
    executor=Executor();service=OperationalFreeTextSessionService(session_root=tmp_path/'sessions',executor=executor,enabled=True);settings=Settings(Path('runtime'),Path('config/madrid.yaml'),'a'*64,'clip',());app=create_app(settings=settings,retriever_factory=lambda _:FakeRetriever(),transformer_factory=lambda _:None,freetext_operational_service=service)
    with TestClient(app) as client:
        response=client.post('/api/v1/dialogue-freetext/sessions',json=start_payload(),headers={'Idempotency-Key':'unauthorized'})
    assert response.status_code==503;assert executor.qwen_calls==executor.ct2l_calls==[];assert not (tmp_path/'sessions'/'.idempotency').exists();assert not (tmp_path/'sessions'/'.authorization-receipts').exists();assert not list((tmp_path/'sessions').glob('freetext-operational-*'))

def test_retrieval_and_freetext_share_one_model_gate(tmp_path):
    app,_,_=app_fixture(tmp_path);assert app.state.inference_gate is app.state.dialogue_gate is app.state.model_gate
    with TestClient(app) as client:
        client.portal.call(app.state.model_gate.acquire)
        try:
            retrieval=client.post('/api/v1/retrievals',json={'schema_version':'1.0','contract_version':'atlas-experimental-retrieval-request-v2','query':{'query_id':'gate-test','text':'Una plaza','language':'es'},'gallery_id':'madrid-50m','top_k':10,'processing_mode':'no_llm'})
            dialogue=client.post('/api/v1/dialogue-freetext/sessions',json=start_payload(),headers={'Idempotency-Key':'gate-test'})
        finally:client.portal.call(app.state.model_gate.release)
    assert retrieval.status_code==503 and retrieval.json()['error']['code']=='RUNTIME_BUSY';assert dialogue.status_code==409 and dialogue.json()['detail']['code']=='FREETEXT_BUSY'

def test_operational_description_accepts_2400_and_rejects_2401_before_execution(tmp_path):
    accepted_path=tmp_path/'accepted';description='x'*2400;executor=Executor();auth=authorize(accepted_path/'auth',executor,description=description);service=OperationalFreeTextSessionService(session_root=accepted_path/'sessions',executor=executor,enabled=True,authorization_root=auth,policy_identity=POLICY,execution_id='exec-1');settings=Settings(Path('runtime'),Path('config/madrid.yaml'),'a'*64,'clip',());app=create_app(settings=settings,retriever_factory=lambda _:FakeRetriever(),transformer_factory=lambda _:None,freetext_operational_service=service)
    with TestClient(app) as client:accepted=client.post('/api/v1/dialogue-freetext/sessions',json=start_payload('x'*2400,'length-2400'),headers={'Idempotency-Key':'length-2400'})
    assert accepted.status_code==200;assert executor.qwen_calls==['E0']
    rejected_path=tmp_path/'rejected';app,_,executor=app_fixture(rejected_path);payload=start_payload('x'*2401);payload['client_operation_id']='length-2401'
    with TestClient(app) as client:rejected=client.post('/api/v1/dialogue-freetext/sessions',json=payload,headers={'Idempotency-Key':'length-2401'})
    assert rejected.status_code==422;assert executor.qwen_calls==executor.ct2l_calls==[];assert not (rejected_path/'sessions'/'.idempotency').exists();assert not (rejected_path/'sessions'/'.authorization-receipts').exists()
