from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
from pathlib import Path

import pytest

from backend.atlas_api.dialogue_sessions import canonical
from backend.atlas_api.freetext_operational import OperationalFreeTextSessionService
from backend.atlas_api.freetext_sessions import FreeTextConflict, FreeTextUnavailable


POLICY = {
    "operational_policy_id": "dialogue-vpr-freetext-v1-operational",
    "operational_policy_version": "1.0.0",
    "operational_policy_sha256": "a" * 64,
    "core_policy_id": "dialogue-vpr-freetext-v1",
    "core_policy_version": "1.0.0",
    "core_policy_sha256": "b" * 64,
}


def z(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class Executor:
    def __init__(self):
        self._identity = {
            "runtime_sha256": "c" * 64,
            "model_artifact_sha256": "d" * 64,
            "worker_sha256": "e" * 64,
        }
        self.calls = []
        self.progress_callback = None

    @property
    def identity(self):
        return dict(self._identity)

    def start(self, **kwargs):
        self.calls.append("E0")
        return {"status": "awaiting_answer", "turns": [{"index": 1, "question": {"intent_key": "q1", "literal": "Pregunta", "sha256": "f" * 64}, "answer": None}], "stages": [], "candidate_universe": []}

    def answer(self, **kwargs):
        state=json.loads(json.dumps(kwargs["state"]));stage=f"E{len(state.get('turns',[]))}";self.calls.append(stage);turn=state['turns'][-1];turn['answer']={'literal':kwargs['answer'],'sha256':hashlib.sha256(kwargs['answer'].encode()).hexdigest()};
        if stage=='E3':state['status']='completed';state['final_stage']='E3';return state
        index=len(state['turns'])+1;state['status']='awaiting_answer';state['turns'].append({'index':index,'question':{'intent_key':f'q{index}','literal':f'Pregunta {index}','sha256':str(index)*64},'answer':None});return state


def authorization(root: Path, executor: Executor, execution_id="exec-1", **changes):
    now = datetime.now(timezone.utc)
    identity = executor.identity
    document = {
        "schema_version": "1.0",
        "contract_version": "atlas-dialogue-freetext-operational-authorization-v1",
        "authorization_id": "auth-1",
        "execution_id": execution_id,
        "status": "OPERATOR_AUTHORIZED",
        "approved": True,
        "approved_at": z(now - timedelta(minutes=2)),
        "valid_from": z(now - timedelta(minutes=1)),
        "expires_at": z(now + timedelta(hours=1)),
        **POLICY,
        "executor_identity": identity,
        "executor_identity_sha256": hashlib.sha256(canonical(identity)).hexdigest(),
        "scope": {"session_count": 1, "stages": ["E0", "E1", "E2", "E3"]},
        "budgets": {"maximum_qwen_loads": 4, "maximum_qwen_calls": 4, "maximum_ct2l_loads": 4, "maximum_ct2l_calls": 4, "maximum_questions": 3, "automatic_retries": 0},
        "constraints": {"ground_truth_permitted": False, "vlm_permitted": False, "h38_h61_permitted": False, "references_permitted": False, "network_permitted": False},
        "reusable_for_other_session": False,
    }
    document.update(changes)
    root.mkdir(parents=True)
    (root / f"{execution_id}.json").write_text(json.dumps(document), encoding="utf-8")
    return document


def fixture(tmp_path: Path):
    executor = Executor()
    auth_root = tmp_path / "auth"
    authorization(auth_root, executor)
    sessions = tmp_path / "sessions"
    service = OperationalFreeTextSessionService(session_root=sessions, executor=executor, enabled=True, authorization_root=auth_root, policy_identity=POLICY, execution_id="exec-1")
    return service, executor, auth_root, sessions


def test_negative_authorization_has_no_executor_idempotency_or_session_activity(tmp_path):
    service, executor, auth_root, sessions = fixture(tmp_path)
    document = json.loads((auth_root / "exec-1.json").read_text())
    document["constraints"]["network_permitted"] = True
    (auth_root / "exec-1.json").write_text(json.dumps(document))
    with pytest.raises(FreeTextUnavailable):
        service.prepare_start("Descripción válida", "key", "key")
    assert executor.calls == []
    assert not (sessions / ".idempotency").exists()
    assert not list(sessions.glob("freetext-operational-*"))
    assert not (sessions / ".authorization-receipts").exists()


def test_exact_budget_and_policy_hash_mismatch_fail_before_consumption(tmp_path):
    for field, mutate in (
        ("budget", lambda document: document["budgets"].update(maximum_qwen_calls=5)),
        ("hash", lambda document: document.update(core_policy_sha256="0" * 64)),
    ):
        root = tmp_path / field
        service, executor, auth_root, sessions = fixture(root)
        document = json.loads((auth_root / "exec-1.json").read_text())
        mutate(document)
        (auth_root / "exec-1.json").write_text(json.dumps(document))
        with pytest.raises(FreeTextUnavailable):
            service.prepare_start("Descripción válida", "key", "key")
        assert executor.calls == [] and not list(sessions.glob("freetext-operational-*"))


def test_exact_replay_and_one_authorization_one_session_across_instances(tmp_path):
    service, executor, auth_root, sessions = fixture(tmp_path)
    other = OperationalFreeTextSessionService(session_root=sessions, executor=executor, enabled=True, authorization_root=auth_root, policy_identity=POLICY, execution_id="exec-1")

    def create(candidate, key):
        try:
            return candidate.prepare_start("Descripción válida", key, key)
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda args: create(*args), [(service, "same"), (other, "other")]))
    successes = [value for value in outcomes if isinstance(value, tuple)]
    assert len(successes) == 1
    session, execute = successes[0]
    assert execute is True
    winning_key = "same" if isinstance(outcomes[0], tuple) else "other"
    replay, execute = service.prepare_start("Descripción válida", winning_key, winning_key)
    assert replay["session_id"] == session["session_id"] and execute is False
    assert len(list((sessions / ".authorization-receipts").glob("*.json"))) == 1
    assert service.policy()["available"] is False and "authorization_status" not in service.policy()


def test_restart_receipt_tamper_expiry_identity_and_missing_session_fail_closed(tmp_path):
    service, executor, auth_root, sessions = fixture(tmp_path)
    document, _ = service.prepare_start("Descripción válida", "key", "key")
    recreated = OperationalFreeTextSessionService(session_root=sessions, executor=executor, enabled=True, authorization_root=auth_root, policy_identity=POLICY, execution_id="exec-1")
    assert recreated.prepare_start("Descripción válida", "key", "key")[0]["session_id"] == document["session_id"]

    executor._identity["runtime_sha256"] = "9" * 64
    with pytest.raises(FreeTextUnavailable):
        recreated.run_start(document["session_id"])
    executor._identity["runtime_sha256"] = "c" * 64

    auth = json.loads((auth_root / "exec-1.json").read_text())
    auth["expires_at"] = z(datetime.now(timezone.utc) - timedelta(seconds=1))
    (auth_root / "exec-1.json").write_text(json.dumps(auth))
    with pytest.raises(FreeTextUnavailable):
        recreated.run_start(document["session_id"])

    auth["expires_at"] = z(datetime.now(timezone.utc) + timedelta(hours=1))
    (auth_root / "exec-1.json").write_text(json.dumps(auth))
    receipt = next((sessions / ".authorization-receipts").glob("*.json"))
    receipt.write_text(receipt.read_text().replace("auth-1", "auth-X"))
    with pytest.raises(FreeTextUnavailable):
        recreated.run_start(document["session_id"])

    session_path = sessions / document["session_id"] / "session.json"
    session_path.unlink()
    with pytest.raises(FreeTextConflict, match="incierto"):
        recreated.prepare_start("Descripción válida", "key", "key")
    assert executor.calls == []


def test_stage_budget_is_durable_and_transition_lock_is_nonblocking(tmp_path):
    service, executor, _, sessions = fixture(tmp_path)
    document, _ = service.prepare_start("Descripción válida", "key", "key")
    lock_path = sessions / document["session_id"] / ".transition.lock"
    with lock_path.open("a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(FreeTextConflict, match="curso"):
            service.run_start(document["session_id"])
    assert service.load(document["session_id"])["budget_reservations"]["qwen_calls"] == 0
    service.run_start(document["session_id"])
    stored = service.load(document["session_id"])
    assert stored["budget_reservations"] == {"qwen_loads": 1, "qwen_calls": 1, "ct2l_loads": 1, "ct2l_calls": 1, "questions": 1, "retries": 0, "stages": ["E0"]}
    service.prepare_answer(document["session_id"], "Respuesta", 1, "q1", "f" * 64, "answer-key", "answer-key")
    stored = service.load(document["session_id"])
    assert stored["budget_reservations"] == {"qwen_loads": 2, "qwen_calls": 2, "ct2l_loads": 2, "ct2l_calls": 2, "questions": 2, "retries": 0, "stages": ["E0", "E1"]}
    public = service.public(stored)
    assert not ({"authorization_binding", "budget_reservations", "executor_identity", "execution_id"} & public.keys())


def test_one_authorization_covers_exactly_e0_e3_and_four_model_units(tmp_path):
    service,executor,_,_=fixture(tmp_path);document,_=service.prepare_start('Descripción válida','start-key','start-key');document=service.run_start(document['session_id'])
    for index in range(1,4):
        question=document['state']['turns'][-1]['question'];document,_=service.prepare_answer(document['session_id'],f'Respuesta {index}',index,question['intent_key'],question['sha256'],f'answer-{index}',f'answer-{index}');document=service.run_answer(document['session_id'])
    assert document['status']=='completed';assert executor.calls==['E0','E1','E2','E3'];assert document['budget_reservations']=={'qwen_loads':4,'qwen_calls':4,'ct2l_loads':4,'ct2l_calls':4,'questions':3,'retries':0,'stages':['E0','E1','E2','E3']}
    with pytest.raises(FreeTextConflict):service.prepare_answer(document['session_id'],'extra',3,'q3','3'*64,'extra','extra-key')


def test_expiry_or_authorization_replacement_between_turns_blocks_before_reservation(tmp_path):
    service,executor,auth_root,_=fixture(tmp_path);document,_=service.prepare_start('Descripción válida','start-key','start-key');document=service.run_start(document['session_id']);before=dict(document['budget_reservations']);auth=json.loads((auth_root/'exec-1.json').read_text());auth['expires_at']=z(datetime.now(timezone.utc)-timedelta(seconds=1));(auth_root/'exec-1.json').write_text(json.dumps(auth));question=document['state']['turns'][-1]['question']
    with pytest.raises(FreeTextUnavailable):service.prepare_answer(document['session_id'],'Respuesta',1,question['intent_key'],question['sha256'],'answer','answer')
    raw=json.loads((service._path(document['session_id'])).read_text());assert raw['budget_reservations']==before;assert executor.calls==['E0']


def test_idempotency_header_and_body_must_match_before_consumption(tmp_path):
    service,executor,_,sessions=fixture(tmp_path)
    with pytest.raises(FreeTextConflict,match='coincidir'):service.prepare_start('Descripción válida','body-id','header-id')
    assert executor.calls==[];assert not (sessions/'.authorization-receipts').exists();assert not (sessions/'.idempotency').exists()


def test_reserved_receipt_recovers_pre_session_crash_but_bound_missing_session_is_uncertain(tmp_path):
    service,executor,_,sessions=fixture(tmp_path);validated=service.authorization.validate('exec-1',executor);body={'policy_id':'dialogue-vpr-freetext-v1-operational','execution_id':'exec-1','description_es':'Descripción válida','client_operation_id':'recover-key'};receipt,_=service.authorization.create_receipt(validated,session_id='freetext-operational-00000000-0000-0000-0000-000000000099',body_sha256=hashlib.sha256(canonical(body)).hexdigest(),idempotency_key_sha256=hashlib.sha256(b'recover-key').hexdigest(),created_at=z(datetime.now(timezone.utc)));document,execute=service.prepare_start('Descripción válida','recover-key','recover-key');assert execute is True and document['session_id']==receipt['session_id'];assert service.authorization.verify_receipt(validated,service.load(document['session_id']))['state']=='bound'
    service._path(document['session_id']).unlink()
    with pytest.raises(FreeTextConflict,match='incierto'):service.prepare_start('Descripción válida','recover-key','recover-key')


def test_completed_idempotency_with_reserved_receipt_repairs_before_replay(tmp_path):
    service,executor,_,_=fixture(tmp_path);document,_=service.prepare_start('Descripción válida','repair-key','repair-key');validated=service.authorization.validate('exec-1',executor);receipt_path=service.authorization.receipt_path('auth-1');receipt=json.loads(receipt_path.read_text());receipt['state']='reserved';receipt.pop('bound_at',None);receipt['receipt_sha256']=hashlib.sha256(canonical({key:value for key,value in receipt.items() if key!='receipt_sha256'})).hexdigest();receipt_path.write_text(json.dumps(receipt));document['authorization_binding']['receipt_sha256']=receipt['receipt_sha256'];service._persist(document);replayed,execute=service.prepare_start('Descripción válida','repair-key','repair-key');assert execute is False;assert service.authorization.verify_receipt(validated,replayed)['state']=='bound'
