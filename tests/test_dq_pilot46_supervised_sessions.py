"""Workers y observaciones explícitamente simulados; las transiciones FastAPI son reales."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import validate
from fastapi.testclient import TestClient

from backend.atlas_api import dq_iterative_sessions as sessions
from research.dq_pilot_supervised_v1 import (
    POLICY_B_SHA256, POLICY_B_VERSION, QWEN_IDENTITY, REGISTRATION, ContractError,
    from_ct2l_postflight, from_qwen_postflight, operation,
)
from tests.test_dq_pilot23_iterative_integration import CT2LPort, QwenPort
from tests.test_dq_pilot24_session_api import start
from tests.test_dq_pilot45_session_flow import build_app


PUBLIC = "/api/v1/dialogue-freetext"
PRIVATE = "/internal/dq-supervised/sessions"
DESCRIPTION = "Veo una plaza amplia y una torre de ladrillo."


def fixture_app(tmp, *, cpu=True, host_lease_receipts=None):
    service = sessions.IterativeDialogueSessionService(session_root=tmp / "sessions", enabled=True,
        fixture_mode=cpu, supervised_inbox=tmp / "inbox", host_lease_receipts=host_lease_receipts)
    return build_app(service), service


def client_for(app, **kwargs):
    return TestClient(app, client=("127.0.0.1", 50000), **kwargs)


def registration_for(session):
    return dict(contract_version=REGISTRATION, mode="cpu_fixture", session_id=session["session_id"],
        session_sha256=session["session_sha256"], description_sha256=sha256(session["description_es"].encode()).hexdigest(),
        operation_id=str(uuid4()), qwen=dict(configuration_sha256="a" * 64, policy_sha256=POLICY_B_SHA256),
        crosstext2loc=dict(configuration_sha256="b" * 64, policy_sha256="c" * 64),
        candidate_set_sha256=sessions.digest([f"c{i:03d}" for i in range(1, 254)]),
        visual_dataset_id="visual-v1", embedding_dataset_id="embedding-v1")


def prepare(client, tmp, key):
    response = client.post(f"{PUBLIC}/iterative/preparations", json={**start(key), "description_es": DESCRIPTION},
        headers={"Idempotency-Key": key})
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["status"] == "waiting_authorization"
    registration = registration_for(session)
    sid = session["session_id"]
    sessions.atomic(tmp / "inbox" / "registrations" / f"{sid}.json", registration)
    return sid, registration


def register(client, sid):
    response = client.post(f"{PRIVATE}/{sid}/register-e0")
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True
    return expected(client, sid)


def expected(client, sid):
    response = client.get(f"{PRIVATE}/{sid}/expected")
    assert response.status_code == 200, response.text
    return response.json()


def qwen_terminal(operation, *, status="SUCCEEDED", released=True, warning=False, latched=False):
    succeed = status == "SUCCEEDED"
    inp = operation["input"]
    output = QwenPort().transform(stage=operation["stage"], transcript=inp["transcript"], prompt=inp["prompt"])
    output.update(session_id=operation["session_id"], description_sha256=inp["description_sha256"],
        session_sha256=inp["session_sha256"], model=QWEN_IDENTITY)
    payload = sessions.canonical(output) + b"\n" if succeed else None
    native_status = ("COMPLETED_WITH_MEMORY_WARNING" if warning else "COMPLETED") if succeed else "FAILED"
    postflight = dict(contract_version="dq-pilot37-postflight-b-v1", memory_policy_version=POLICY_B_VERSION,
        status=native_status, errors=[] if succeed else ["gate PSI"], container_id="container-fixture",
        state=dict(Running=False, Restarting=False, Pid=0, ExitCode=0 if succeed else 137, OOMKilled=False),
        host=dict(cuda_pids=[]), container_termination_verified=True, cuda_release_observed=True,
        worker_release_verified=released, resource_release_verified=released, policy_compliant=succeed,
        operation_succeeded=succeed, verified=succeed and released,
        memory_policy=dict(version=POLICY_B_VERSION, stopped={"reason": "gate PSI"} if latched or not succeed else None,
                           has_memory_warning=warning))
    release = dict(allocated_bytes=0, reserved_bytes=0) if released else None
    commit = dict(session_id=operation["session_id"], attempt_id=operation["operation_id"],
        plan_sha256=operation["configuration_sha256"], operation_sha256=sessions.digest(operation), status=native_status,
        failure=None if succeed else "stop: fixture", postflight_sha256=sessions.digest(postflight),
        worker_release_sha256=sessions.digest(release) if release else None,
        result_sha256=sha256(payload).hexdigest() if payload else None)
    return from_qwen_postflight(operation, commit=commit, postflight=postflight, worker_release=release,
        output_bytes=payload, failure_status=status if not succeed else "FAILED")


def ct2l_terminal(operation, *, edit=lambda _: None, status="SUCCEEDED", released=True):
    inp = operation["input"]
    native = CT2LPort().retrieve(stage=operation["stage"], query_id=inp["query_id"], text=inp["text"])
    native["schema_version"] = "1.0"
    edit(native)
    payload = sessions.canonical(native) + b"\n" if status == "SUCCEEDED" else None
    postflight = dict(contract_version="atlas-dq-ct2l-postflight-v1", policy_sha256=operation["policy_sha256"],
        process=dict(execution_id="proc-fixture", terminated=True, running=False, restarting=False,
                     pid=0, exit_code=0 if payload else 1, oom_killed=False),
        resource_release_verified=released, policy_compliant=bool(payload),
        cuda_pids=[] if released else [99], worker_close_verified=released)
    commit = {**{key: operation[key] for key in ("session_id", "operation_id", "configuration_sha256")},
        "operation_sha256": sessions.digest(operation), "postflight_sha256": sessions.digest(postflight), "status": status,
        "result_sha256": sha256(payload).hexdigest() if payload else None}
    return from_ct2l_postflight(operation, commit=commit, postflight=postflight, output_bytes=payload)


def publish(tmp, terminal, *, op_id=None):
    path = tmp / "inbox" / "terminals" / f"{op_id or terminal['operation_id']}.json"
    sessions.atomic(path, terminal)
    return path


def consume(client, sid, terminal):
    return client.post(f"{PRIVATE}/{sid}/terminals/{terminal['operation_id']}")


def test_real_admission_requires_host_receipt_for_qwen_and_ct2l(tmp_path):
    # Terminales y recibos sintéticos explícitos: se verifica admisión HTTP, no inferencia.
    schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/dq-stage-lease-receipt.schema.json').read_text())
    root = tmp_path / 'lease'
    app, _ = fixture_app(tmp_path, cpu=False, host_lease_receipts=root)
    with client_for(app) as client:
        sid, reg = prepare(client, tmp_path, 'DQ46-host-admission')
        sessions.atomic(tmp_path / 'inbox' / 'registrations' / f'{sid}.json', {**reg, 'mode': 'real'})
        op = register(client, sid)
        for component, adapter in (('qwen', qwen_terminal), ('crosstext2loc', ct2l_terminal)):
            assert op['component'] == component
            terminal = adapter(op)
            publish(tmp_path, terminal)
            assert consume(client, sid, terminal).status_code == 409
            assert expected(client, sid) == op
            sha = sessions.digest(op)
            receipt = dict(lease=dict(contract_version='atlas-dq-exclusive-stage-lease-v1',
                operation_sha256=sha, **{key: op[key] for key in ('session_id', 'operation_id', 'component', 'mode')}),
                postflight_sha256=terminal['evidence']['postflight_sha256'], execution_id=terminal['process']['execution_id'],
                terminal_sha256=sessions.digest(terminal), cgroup_state='empty')
            validate(receipt, schema)
            path = root / f'{sha}.release.json'
            sessions.atomic(path, {**receipt, 'cgroup_state': 'running'})
            assert consume(client, sid, terminal).status_code == 409
            sessions.atomic(path, {**receipt, 'terminal_sha256': 'f'*64})
            assert consume(client, sid, terminal).status_code == 409
            sessions.atomic(path, receipt)
            assert consume(client, sid, terminal).json()['applied'] is True
            if component == 'qwen':
                op = expected(client, sid)
                assert op['input']['qwen_terminal_sha256'] == sessions.digest(terminal)


def test_round_restart_duplicate_sse_and_top10(tmp_path):
    app, service = fixture_app(tmp_path)
    with client_for(app) as client:
        sid, registration = prepare(client, tmp_path, "first")
        url = f"{PUBLIC}/sessions/{sid}"
        initial = client.get(f"{url}/events").json()["events"][-1]["event_id"]
        assert client.get(f"{PRIVATE}/{sid}/expected").status_code == 409
        qwen = register(client, sid)
        assert qwen["operation_id"] == registration["operation_id"] and qwen["stage"] == "E0"
        assert client.post(f"{PRIVATE}/{sid}/register-e0").json()["applied"] is False
        terminal = qwen_terminal(qwen)
        assert consume(client, sid, terminal).status_code == 503  # Nada publicado.
        source = publish(tmp_path, terminal)
        assert consume(client, sid, terminal).json()["applied"] is True
        assert consume(client, sid, terminal).json()["applied"] is False
        ct = expected(client, sid)
        assert ct["input"]["qwen_terminal_sha256"] == sessions.digest(terminal)
        assert ct["input"]["text"] == terminal["result"]["text"]
        assert client.get(url).json()["stage_snapshots"] == []
    restarted, new_service = fixture_app(tmp_path)
    with client_for(restarted) as client:
        assert expected(client, sid) == ct
        source.unlink()  # Conservación del recibo tras archivar el buzón.
        assert consume(client, sid, terminal).json()["applied"] is False
        publish(tmp_path, {**terminal, "input_sha256": "0" * 64})
        assert consume(client, sid, terminal).status_code == 409
        ranking = ct2l_terminal(ct)
        publish(tmp_path, ranking)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: consume(client, sid, ranking).json()["applied"], range(2)))
        assert sorted(results) == [False, True]
        live = client.get(url).json()
        assert live["status"] == "waiting_review" and live["current_question"] is None
        assert live["controller_state"] == "AWAITING_DQ_AUTHORIZATION"
        assert live["supervised"] is True and live["execution_mode"] == "cpu_fixture" and live["gpu_used"] is False
        assert live["description_es"] == live["accumulated_description_es"] == DESCRIPTION
        meta = new_service.load(sid)["supervised"]
        full = meta["artifacts"]["rounds/round-0/ct2l-ranking.json"]
        reserve = meta["artifacts"]["rounds/round-0/top-n-reserve.json"]
        assert len(full["results"]) == 253 and reserve["results"] == full["results"][:20]
        assert live["stage_snapshots"][0]["results"] == full["results"][:10]
        assert live["stage_snapshots"][0]["ranking_sha256"] == reserve["source_ranking_sha256"] == sessions.digest(full)
        assert "raw_output" not in live and "receipts" not in live and meta["expected"] is None
        assert meta["artifacts"]["rounds/round-0/llm-interpretation.json"]["model"]["real_model_inference"] is False
        events = client.get(f"{url}/events").json()["events"]
        raw = client.get(f"{url}/events/stream?follow=true", headers={"Last-Event-ID": initial})
        assert [line[4:] for line in raw.text.splitlines() if line.startswith("id: ")] == [row["event_id"] for row in events[1:]]
        assert sum(row["stage"] == "E0_ranking" for row in events) == 1 and events[-1]["state"] == live["status"]
        assert service.load(sid) == new_service.load(sid)


@pytest.mark.parametrize("status", ["STOPPED_MEMORY", "TIMED_OUT", "FAILED"])
def test_qwen_anomalous_close_without_ct2l(tmp_path, status):
    app, service = fixture_app(tmp_path)
    with client_for(app) as client:
        sid, _ = prepare(client, tmp_path, "failure")
        op = register(client, sid)
        failed = qwen_terminal(op, status=status, released=False)
        forged = {**failed, "result": {"partial": True}, "output_sha256": "f" * 64}
        publish(tmp_path, forged)
        assert consume(client, sid, forged).status_code == 409
        publish(tmp_path, failed)
        response = consume(client, sid, failed).json()
        assert response["applied"] and response["session"]["status"] == "failed"
        assert response["session"]["stage_snapshots"] == [] and status == service.events(sid)[-1]["error_code"]
        assert client.get(f"{PRIVATE}/{sid}/expected").status_code == 409


def test_cross_session_tampering_partial_and_private_channel(tmp_path):
    app, service = fixture_app(tmp_path)
    with client_for(app) as client:
        sid, _ = prepare(client, tmp_path, "a")
        other, _ = prepare(client, tmp_path, "b")
        op = register(client, sid)
        op2 = register(client, other)
        qwen = qwen_terminal(op)
        publish(tmp_path, qwen, op_id=op2["operation_id"])
        assert client.post(f"{PRIVATE}/{other}/terminals/{op2['operation_id']}").status_code == 409
        assert consume(client, other, qwen).status_code == 409
        assert expected(client, other) == op2
        original = service.load(sid)
        for changes in ({"stage": "E1"}, {"model_revision": "wrong"}, {"input_sha256": "5" * 64},
                        {"output_sha256": "6" * 64}, {"configuration_sha256": "7" * 64},
                        {"status": "RUNNING"}, {"ground_truth_used": True}, {"process": {**qwen["process"], "exit_code": 1}}):
            publish(tmp_path, {**qwen, **changes})
            assert consume(client, sid, qwen).status_code == 409
        publish(tmp_path, qwen_terminal(op, released=False))
        assert consume(client, sid, qwen).status_code == 409
        assert service.load(sid) == original
        url = f"{PRIVATE}/{sid}/terminals/{qwen['operation_id']}"
        for key in ("Origin", "Sec-Fetch-Site", "X-Atlas-App-Loopback", "X-Forwarded-For"):
            assert client.post(url, headers={key: "127.0.0.1"}).status_code == 404
        with TestClient(app) as outside:
            assert outside.post(url).status_code == 404
        publish(tmp_path, qwen)
        assert consume(client, sid, qwen).status_code == 200
        ct = expected(client, sid)
        for edit in (lambda data: data["retrievals"][0]["results"].pop(),
                     lambda data: data["query"].update(text="The wrong text."),
                     lambda data: data["retrievals"][0]["results"][-1].update(candidate_id="another-candidate")):
            invalid = ct2l_terminal(ct, edit=edit)
            publish(tmp_path, invalid)
            assert consume(client, sid, invalid).status_code == 409
        invalid = ct2l_terminal(ct, released=False)
        publish(tmp_path, invalid)
        assert consume(client, sid, invalid).status_code == 409
        assert expected(client, sid) == ct
        failure = ct2l_terminal(ct, status="FAILED", released=False)
        publish(tmp_path, failure)
        assert consume(client, sid, failure).json()["session"]["current_question"] is None
        assert not service.load(sid)["rankings_available"]
        # Una salida exitosa tardía no reemplaza el terminal fallido ya aceptado.
        publish(tmp_path, ct2l_terminal(ct))
        assert consume(client, sid, failure).status_code == 409


def test_persistence_failure_leaves_sse_and_session_unchanged(tmp_path, monkeypatch):
    app, service = fixture_app(tmp_path)
    with client_for(app, raise_server_exceptions=False) as client:
        sid, _ = prepare(client, tmp_path, "disk")
        op = register(client, sid)
        qwen = qwen_terminal(op)
        path = publish(tmp_path, qwen)
        initial = service.load(sid), deepcopy(service.events(sid))
        replace = sessions.os.replace
        def fail(src, dst):
            if dst == service._metadata(sid):
                raise OSError("Fallo de disco simulado")
            return replace(src, dst)
        with monkeypatch.context() as mp:
            mp.setattr(sessions.os, "replace", fail)
            assert consume(client, sid, qwen).status_code == 500
        assert (service.load(sid), service.events(sid)) == initial and path.is_file()
        assert consume(client, sid, qwen).json()["applied"] is True


def test_real_configuration_refuses_cpu_fixture_registration(tmp_path):
    app, _ = fixture_app(tmp_path, cpu=False)
    with client_for(app) as client:
        sid, _ = prepare(client, tmp_path, "only-explicit-fixtures")
        assert client.post(f"{PRIVATE}/{sid}/register-e0").status_code == 409
        assert client.get(f"{PUBLIC}/sessions/{sid}").json()["status"] == "waiting_authorization"


def test_terminal_from_e0_cannot_overwrite_a_later_expected_stage(tmp_path):
    app, service = fixture_app(tmp_path)
    with client_for(app) as client:
        sid, registration = prepare(client, tmp_path, "later-stage")
        qwen = qwen_terminal(register(client, sid))
        publish(tmp_path, qwen)
        assert consume(client, sid, qwen).json()["applied"] is True
        ct2l = ct2l_terminal(expected(client, sid))
        publish(tmp_path, ct2l)
        assert consume(client, sid, ct2l).json()["applied"] is True

        # Estado posterior simulado explícitamente: Gate C aún no registra E1.
        meta = service.load(sid)
        bridge = meta["supervised"]
        state = bridge["state"]
        question, answer = "¿Ves un reloj?", "Sí, está en la torre."
        state.update(round_index=1, controller_state="LLM_INTERPRETATION", accumulated_description=f"{DESCRIPTION}\nRespuesta 1: {answer}",
            turns=[dict(index=1, question_original="Can you see a clock?", question_es=question,
                        question_es_sha256=sessions.digest_text(question), answer={"literal": answer})])
        op = operation(registration, state, "qwen", str(uuid4()))
        bridge["expected"] = op
        service._persist_meta({**meta, "status": "pending", "current_stage": "QWEN_E1"})
        before = service.load(sid)
        assert before["supervised"]["expected"]["stage"] == "E1"
        assert consume(client, sid, qwen).status_code == consume(client, sid, ct2l).status_code == 409
        assert service.load(sid) == before and expected(client, sid) == op


def test_qwen_verified_warning_is_distinct_from_latched_memory_stop(tmp_path):
    app, _ = fixture_app(tmp_path)
    with client_for(app) as client:
        sid, _ = prepare(client, tmp_path, "memory-warning")
        op = register(client, sid)
        with pytest.raises(ContractError):
            qwen_terminal(op, warning=True, latched=True)
        assert expected(client, sid) == op
        warning = qwen_terminal(op, warning=True)
        publish(tmp_path, warning)
        assert consume(client, sid, warning).json()["applied"] is True
        assert expected(client, sid)["component"] == "crosstext2loc"
