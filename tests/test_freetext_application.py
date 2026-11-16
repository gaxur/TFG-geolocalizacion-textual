from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.atlas_api.dialogue_sessions import canonical
from backend.atlas_api.freetext_application import ApplicationFreeTextSessionService
from backend.atlas_api.freetext_sessions import FreeTextConflict, FreeTextUnavailable
from backend.atlas_api.freetext_operational import utcnow
from backend.atlas_api.main import create_app
from backend.atlas_api.settings import Settings


POLICY = {
    "application_policy_id": "dialogue-vpr-freetext-v1-application",
    "application_policy_version": "1.0.0",
    "application_policy_sha256": "a" * 64,
    "core_policy_id": "dialogue-vpr-freetext-v1",
    "core_policy_version": "1.0.0",
    "core_policy_sha256": "b" * 64,
}


def z(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class Executor:
    def __init__(self):
        self._identity = {"runtime_sha256": "c" * 64, "model_sha256": "d" * 64}
        self.calls = []
        self.progress_callback = None

    @property
    def identity(self):
        return dict(self._identity)

    def start(self, **kwargs):
        self.calls.append("E0")
        return {"status": "awaiting_answer", "turns": [{"index": 1, "question": {"intent_key": "q1", "literal": "Pregunta 1", "sha256": "1" * 64}, "answer": None}], "stages": [], "candidate_universe": []}

    def answer(self, **kwargs):
        state = json.loads(json.dumps(kwargs["state"]))
        stage = f"E{len(state['turns'])}"
        self.calls.append(stage)
        state["turns"][-1]["answer"] = {"literal": kwargs["answer"], "sha256": hashlib.sha256(kwargs["answer"].encode()).hexdigest()}
        if stage == "E3":
            state.update(status="completed", final_stage="E3")
            return state
        index = len(state["turns"]) + 1
        state["status"] = "awaiting_answer"
        state["turns"].append({"index": index, "question": {"intent_key": f"q{index}", "literal": f"Pregunta {index}", "sha256": str(index) * 64}, "answer": None})
        return state


def write_profile(path: Path, executor: Executor, *, total=4, opened=2, **changes):
    now = datetime.now(timezone.utc)
    identity = executor.identity
    document = {
        "schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-application-profile-v1",
        "profile_id": "local-approved-v1", "profile_version": "1.0.0", "status": "APPROVED", "approved": True,
        "approved_at": z(now - timedelta(minutes=2)), "valid_from": z(now - timedelta(minutes=1)), "expires_at": z(now + timedelta(hours=1)),
        **POLICY, "executor_identity": identity, "executor_identity_sha256": hashlib.sha256(canonical(identity)).hexdigest(),
        "max_sessions_total": total, "max_open_sessions": opened,
        "global_quotas": {"maximum_qwen_units": total*4, "maximum_ct2l_units": total*4, "maximum_questions": total*3},
        "per_session_quotas": {"maximum_qwen_loads": 4, "maximum_qwen_calls": 4, "maximum_ct2l_loads": 4, "maximum_ct2l_calls": 4, "maximum_questions": 3, "automatic_retries": 0},
        "constraints": {"access_mode": "loopback", "network_permitted": False, "ground_truth_permitted": False, "references_permitted": False, "vlm_permitted": False, "h38_h61_permitted": False},
    }
    document.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def service(tmp_path: Path, *, total=4, opened=2, enabled=True):
    executor = Executor()
    profile = tmp_path / "profile.json"
    write_profile(profile, executor, total=total, opened=opened)
    instance = ApplicationFreeTextSessionService(session_root=tmp_path / "sessions", state_root=tmp_path / "state", profile_path=profile, executor=executor, enabled=enabled, policy_identity=POLICY)
    return instance, executor, profile


@pytest.mark.parametrize("change", [
    {"status": "PENDING_APPROVAL", "approved": False},
    {"application_policy_sha256": "0" * 64},
    {"expires_at": "2000-01-01T00:00:00Z"},
])
def test_disabled_pending_mismatch_and_expiry_fail_before_ledger_admission(tmp_path, change):
    instance, executor, profile = service(tmp_path)
    document = json.loads(profile.read_text())
    document.update(change)
    profile.write_text(json.dumps(document))
    assert instance.policy()["available"] is False
    with pytest.raises(FreeTextUnavailable):
        instance.prepare_start("Descripción arbitraria", "key", "key")
    with sqlite3.connect(instance.ledger_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert executor.calls == []


def test_disabled_mode_is_unavailable(tmp_path):
    instance, executor, _ = service(tmp_path, enabled=False)
    with pytest.raises(FreeTextUnavailable):
        instance.prepare_start("Descripción arbitraria", "key", "key")
    assert executor.calls == []


def test_direct_service_enforces_description_bounds(tmp_path):
    instance, executor, _ = service(tmp_path)
    for description in ("xx", "x" * 2401):
        with pytest.raises(FreeTextConflict, match="3 y 2400"):
            instance.prepare_start(description, "key", "key")
    assert executor.calls == []


def test_total_quota_open_limit_and_concurrent_admission_are_transactional(tmp_path):
    instance, _, _ = service(tmp_path, total=2, opened=1)

    def create(key):
        try:
            return instance.prepare_start(f"Descripción {key}", key, key)
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ("one", "two")))
    accepted = [result for result in results if isinstance(result, tuple)]
    assert len(accepted) == 1
    first, _ = accepted[0]
    first["status"] = "completed"
    instance._persist(first)
    second, execute = instance.prepare_start("Descripción final", "three", "three")
    assert execute is True and second["session_id"] != first["session_id"]
    second["status"] = "completed"
    instance._persist(second)
    with pytest.raises(FreeTextUnavailable, match="total"):
        instance.prepare_start("Descripción excedente", "four", "four")


def test_restart_idempotency_exact_replay_and_body_conflict(tmp_path):
    instance, executor, profile = service(tmp_path)
    first, execute = instance.prepare_start("Una plaza con una torre", "same", "same")
    assert execute is True
    restarted = ApplicationFreeTextSessionService(session_root=tmp_path / "sessions", state_root=tmp_path / "state", profile_path=profile, executor=executor, enabled=True, policy_identity=POLICY)
    replay, execute = restarted.prepare_start("Una plaza con una torre", "same", "same")
    assert replay["session_id"] == first["session_id"] and execute is False
    with pytest.raises(FreeTextConflict):
        restarted.prepare_start("Otro cuerpo", "same", "same")


def test_restart_marks_ledger_session_without_artifact_unknown_and_releases_open_slot(tmp_path):
    instance, executor, profile = service(tmp_path, total=2, opened=1)
    with instance._connect() as connection:
        connection.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", ("freetext-application-00000000-0000-0000-0000-000000000001", "local-approved-v1", "x", "pending", z(datetime.now(timezone.utc))))
    restarted=ApplicationFreeTextSessionService(session_root=tmp_path/'sessions',state_root=tmp_path/'state',profile_path=profile,executor=executor,enabled=True,policy_identity=POLICY)
    with restarted._connect() as connection:assert connection.execute("SELECT status FROM sessions WHERE session_id LIKE 'freetext-application-%'").fetchone()[0]=='unknown'
    document,execute=restarted.prepare_start('Descripción posterior','next','next');assert execute is True and document['status']=='pending'


def test_persistence_failure_marks_ledger_unknown_without_refund(tmp_path,monkeypatch):
    instance,_,_=service(tmp_path,total=2,opened=1);original=instance._persist;calls=0
    def fail_once(document):
        nonlocal calls;calls+=1
        if calls==1:raise OSError('disk failure')
        return original(document)
    monkeypatch.setattr(instance,'_persist',fail_once)
    with pytest.raises(OSError):instance.prepare_start('Descripción válida','persist-fail','persist-fail')
    with instance._connect() as connection:
        row=connection.execute('SELECT status FROM sessions').fetchone();assert row[0]=='unknown';assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==1


def test_e0_e3_exact_quotas_no_refunds_and_answer_idempotency(tmp_path):
    instance, executor, _ = service(tmp_path)
    document, _ = instance.prepare_start("Una descripción suficientemente larga", "start", "start")
    document = instance.run_start(document["session_id"])
    for index in range(1, 4):
        question = document["state"]["turns"][-1]["question"]
        args = (document["session_id"], f"Respuesta {index}", index, question["intent_key"], question["sha256"], f"answer-{index}", f"answer-{index}")
        prepared, execute = instance.prepare_answer(*args)
        assert execute is True
        replay, execute = instance.prepare_answer(*args)
        assert replay["session_id"] == document["session_id"] and execute is False
        document = instance.run_answer(document["session_id"])
    assert document["status"] == "completed" and executor.calls == ["E0", "E1", "E2", "E3"]
    assert document["budget_reservations"] == {"qwen_loads": 4, "qwen_calls": 4, "ct2l_loads": 4, "ct2l_calls": 4, "questions": 3, "retries": 0, "stages": ["E0", "E1", "E2", "E3"]}
    with sqlite3.connect(instance.ledger_path) as connection:
        assert connection.execute("SELECT COUNT(*), SUM(qwen_calls), SUM(ct2l_calls), SUM(questions) FROM reservations").fetchone() == (4, 4, 4, 3)


def test_profile_identity_change_blocks_existing_session_without_refund(tmp_path):
    instance, executor, profile = service(tmp_path)
    document, _ = instance.prepare_start("Descripción válida", "start", "start")
    executor._identity["runtime_sha256"] = "9" * 64
    with pytest.raises(FreeTextUnavailable):
        instance.run_start(document["session_id"])
    with sqlite3.connect(instance.ledger_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0
    assert profile.is_file()


class Retriever:
    gallery_ids = ("madrid-50m",)
    ephemeral = True
    def gallery_count(self, gallery_id): return 253
    def close(self): pass


def test_application_api_contract_metadata_and_shared_gate(tmp_path):
    instance, executor, _ = service(tmp_path)
    settings = Settings(Path("runtime"), Path("config/madrid.yaml"), "a" * 64, "clip", ())
    app = create_app(settings=settings, retriever_factory=lambda _: Retriever(), transformer_factory=lambda _: None, freetext_application_service=instance)
    payload = {"schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-start-request-v2", "policy_id": "dialogue-vpr-freetext-v1-application", "description_es": "Una descripción libre de la plaza", "client_operation_id": "api-start"}
    with TestClient(app) as client:
        policies = client.get("/api/v1/dialogue-freetext/policies").json()["policies"]
        public = next(row for row in policies if row["policy_id"] == "dialogue-vpr-freetext-v1-application")
        assert public["available"] is True and public["profile"]["access_mode"] == "loopback"
        assert "executor_identity" not in json.dumps(public) and "sha256" not in json.dumps(public["profile"])
        response = client.post("/api/v1/dialogue-freetext/sessions", json=payload, headers={"Idempotency-Key": "api-start"})
        assert response.status_code == 200 and response.json()["policy_id"] == "dialogue-vpr-freetext-v1-application"
        lookup=client.get('/api/v1/dialogue-freetext/application/operations/api-start');assert lookup.status_code==200 and lookup.json()['session_id']==response.json()['session_id']
        assert app.state.model_gate is app.state.inference_gate is app.state.dialogue_gate
    assert executor.calls == ["E0"]


def test_application_mode_does_not_register_scientific_or_raw_routes(tmp_path):
    instance,_,profile=service(tmp_path);settings=Settings(Path('runtime'),Path('config/madrid.yaml'),'a'*64,'clip',(),freetext_application_enabled=True,freetext_application_profile=profile,freetext_application_state_root=tmp_path/'state',freetext_application_session_root=tmp_path/'sessions');app=create_app(settings=settings,retriever_factory=lambda _:Retriever(),transformer_factory=lambda _:None,freetext_application_service=instance,operational_retriever_factory=lambda _:Retriever(),operational_transformer_factory=lambda _:None)
    with TestClient(app) as client:
        assert client.post('/api/v1/retrievals',json={}).status_code==404
        assert client.get('/api/v1/dialogue/queries').status_code==404
        assert client.get('/api/v1/progress/example').status_code==404
        assert client.get('/api/v1/dialogue/variants').status_code==404


def test_answer_ledger_running_with_stale_waiting_document_reconciles_unknown(tmp_path):
    instance,executor,profile=service(tmp_path);document,_=instance.prepare_start('Descripción válida','start','start');document=instance.run_start(document['session_id']);question=document['state']['turns'][-1]['question'];body={"turn_index":1,"question_id":question['intent_key'],"question_sha256":question['sha256'],"answer_literal":"Respuesta","human_attested":True,"external_context_used":False,"client_operation_id":"answer"}
    with instance._connect() as connection:
        connection.execute("BEGIN IMMEDIATE");connection.execute("INSERT INTO reservations VALUES (?,?,?,?,?,?,?,?)",(document['session_id'],'E1',1,1,1,1,1,utcnow()));connection.execute("INSERT INTO idempotency VALUES (?,?,?,?,?)",('answer',document['session_id'],hashlib.sha256(b'answer').hexdigest(),instance._body_sha(body),document['session_id']));connection.execute("UPDATE sessions SET status='running' WHERE session_id=?",(document['session_id'],));connection.commit()
    restarted=ApplicationFreeTextSessionService(session_root=tmp_path/'sessions',state_root=tmp_path/'state',profile_path=profile,executor=executor,enabled=True,policy_identity=POLICY);stored=json.loads(restarted._path(document['session_id']).read_text());assert stored['status']=='unknown'


def test_answer_persist_failure_keeps_durable_unknown_on_load_and_restart(tmp_path, monkeypatch):
    instance,executor,profile=service(tmp_path);document,_=instance.prepare_start('Descripción válida','start','start');document=instance.run_start(document['session_id']);question=document['state']['turns'][-1]['question'];original=instance._persist
    monkeypatch.setattr(instance,'_persist',lambda _document: (_ for _ in ()).throw(OSError('fallo inyectado')))
    with pytest.raises(OSError,match='fallo inyectado'):
        instance.prepare_answer(document['session_id'],'Respuesta',1,question['intent_key'],question['sha256'],'answer','answer')
    monkeypatch.setattr(instance,'_persist',original)
    assert instance.load(document['session_id'])['status']=='unknown'
    restarted=ApplicationFreeTextSessionService(session_root=tmp_path/'sessions',state_root=tmp_path/'state',profile_path=profile,executor=executor,enabled=True,policy_identity=POLICY)
    assert restarted.load(document['session_id'])['status']=='unknown'


def test_application_and_scientific_operational_services_are_exclusive(tmp_path):
    instance, _, _ = service(tmp_path)
    settings = Settings(Path("runtime"), Path("config/madrid.yaml"), "a" * 64, "clip", ())
    with pytest.raises(ValueError, match="mutuamente exclusivos"):
        create_app(settings=settings, retriever_factory=lambda _: Retriever(), transformer_factory=lambda _: None, freetext_application_service=instance, freetext_operational_service=object())


def test_pending_application_profile_makes_startup_readiness_unavailable(tmp_path):
    instance, executor, profile = service(tmp_path)
    document = json.loads(profile.read_text())
    document.update(status="PENDING_APPROVAL", approved=False)
    profile.write_text(json.dumps(document))
    settings = Settings(Path("runtime"), Path("config/madrid.yaml"), "a" * 64, "clip", ())
    app = create_app(settings=settings, retriever_factory=lambda _: Retriever(), transformer_factory=lambda _: None, freetext_application_service=instance)
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503 and response.json()["error"]["code"] == "APPLICATION_PROFILE_NOT_APPROVED"
    assert executor.calls == []


def test_application_environment_requires_paths_and_excludes_scientific_mode(monkeypatch):
    monkeypatch.setenv("ATLAS_CVG_UTILS_SHA256", "a" * 64)
    monkeypatch.setenv("CLIP_WEIGHTS_PATH", "clip.pt")
    monkeypatch.setenv("ATLAS_FREETEXT_APPLICATION_ENABLED", "true")
    with pytest.raises(ValueError, match="profile, state root y session root"):
        Settings.from_env()
    monkeypatch.setenv("ATLAS_FREETEXT_APPLICATION_PROFILE", "profile.json")
    monkeypatch.setenv("ATLAS_FREETEXT_APPLICATION_STATE_ROOT", "state")
    monkeypatch.setenv("ATLAS_FREETEXT_APPLICATION_SESSION_ROOT", "sessions")
    parsed = Settings.from_env()
    assert parsed.freetext_application_enabled and parsed.freetext_application_profile == Path("profile.json")
    monkeypatch.setenv("ATLAS_FREETEXT_OPERATIONAL_ENABLED", "true")
    monkeypatch.setenv("ATLAS_FREETEXT_OPERATIONAL_SESSION_ROOT", "scientific-sessions")
    monkeypatch.setenv("ATLAS_FREETEXT_OPERATIONAL_AUTHORIZATION_ROOT", "authorizations")
    monkeypatch.setenv("ATLAS_FREETEXT_OPERATIONAL_EXECUTION_ID", "execution-1")
    with pytest.raises(ValueError, match="mutuamente exclusivos"):
        Settings.from_env()
