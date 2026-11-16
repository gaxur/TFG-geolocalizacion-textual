"""API unificada para pilotos y sesiones FreeText-v1."""
from __future__ import annotations

import asyncio
import json

import anyio
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from backend.atlas_api.freetext_operational import OperationalFreeTextExpired
from backend.atlas_api.freetext_sessions import FreeTextConflict, FreeTextUnavailable
from backend.atlas_api.models import (
    FreeTextAnswerRequest,
    FreeTextPolicyStartRequest,
    FreeTextStartRequest,
    OperationalFreeTextAnswerRequest,
    OperationalFreeTextStartRequest,
)
from backend.atlas_api.progress import QueryProgress

router = APIRouter(prefix="/api/v1/dialogue-freetext")


def historical(request: Request):
    return getattr(request.app.state, "freetext_service", None)


def operational(request: Request):
    return getattr(request.app.state, "freetext_operational_service", None)


def fail(error):
    if isinstance(error, OperationalFreeTextExpired):
        raise HTTPException(status_code=410, detail={"code":"FREETEXT_EXPIRED","message":str(error)})
    conflict = isinstance(error, FreeTextConflict)
    raise HTTPException(
        status_code=409 if conflict else 503,
        detail={
            "code": "FREETEXT_CONFLICT" if conflict else "FREETEXT_NOT_AUTHORIZED",
            "message": str(error),
        },
    )


async def transition(request: Request, query_id: str, operation):
    service = historical(request)
    progress = QueryProgress(request.app.state.progress_hub, query_id)
    loop = asyncio.get_running_loop()
    executor = getattr(service, "executor", None)

    def callback(stage, component, state):
        asyncio.run_coroutine_threadsafe(
            progress.stage(f"{stage}_{component}", state, f"{component} {stage}: {state}"), loop
        )

    if executor is not None:
        executor.progress_callback = callback
    await progress.pipeline("running", "Transición FreeText aceptada.")
    try:
        result = await anyio.to_thread.run_sync(operation)
        await progress.pipeline("completed", "Transición FreeText persistida.")
        return result
    except Exception:
        if not progress.terminal:
            await progress.pipeline("failed", "La transición FreeText falló.", error_code="FREETEXT_TRANSITION_FAILED")
        raise
    finally:
        if executor is not None:
            executor.progress_callback = None


@router.get("/pilot")
async def pilot(request: Request):
    service = historical(request)
    if service is None:
        return {
            "schema_version": "1.0",
            "contract_version": "atlas-dialogue-freetext-pilot-public-v1",
            "available": False,
            "policy_id": "dialogue-vpr-freetext-v1",
            "authorization_status": "not_configured",
        }
    return service.pilot()


@router.get("/pilots")
@router.get("/policies")
async def pilots(request: Request):
    service = historical(request)
    catalogue = service.policies() if service is not None else {
        "schema_version": "1.0",
        "contract_version": "atlas-dialogue-freetext-policy-catalogue-v1",
        "policies": [],
    }
    operational_service = operational(request)
    if operational_service is not None:
        catalogue["policies"].append(operational_service.policy())
    return catalogue


@router.get("/pilot/image")
async def image(request: Request):
    try:
        service = historical(request)
        if service is None:
            raise FreeTextUnavailable("piloto histórico no configurado")
        path = service.image()
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/sessions")
async def start(
    payload: FreeTextStartRequest | FreeTextPolicyStartRequest | OperationalFreeTextStartRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    gate = request.app.state.dialogue_gate
    try:
        if isinstance(payload, OperationalFreeTextStartRequest):
            service = operational(request)
            if service is None:
                raise FreeTextUnavailable("servicio FreeText operacional no configurado")
            if not gate.try_acquire():
                raise HTTPException(status_code=409, detail={"code": "FREETEXT_BUSY", "message": "Otra transición está en curso."})
            try:
                document, execute = await anyio.to_thread.run_sync(
                    service.prepare_start, payload.description_es, payload.client_operation_id, idempotency_key or ""
                )
            except Exception:
                gate.release()
                raise

            async def run_start():
                try:
                    await anyio.to_thread.run_sync(service.run_start, document["session_id"])
                finally:
                    gate.release()

            if execute:
                background_tasks.add_task(run_start)
            else:
                gate.release()
            return service.public(document)

        service = historical(request)
        if service is None:
            raise FreeTextUnavailable("servicio FreeText histórico no configurado")
        if not gate.try_acquire():
            raise HTTPException(status_code=409, detail={"code": "FREETEXT_BUSY", "message": "Otra transición está en curso."})
        if isinstance(payload, FreeTextPolicyStartRequest):
            async with gate:
                document = await transition(
                    request,
                    payload.variant_id,
                    lambda: service.start_policy(payload.policy_id, payload.variant_id),
                )
        else:
            async with gate:
                document = await transition(
                    request,
                    payload.experimental_query_id,
                    lambda: service.start(payload.experimental_query_id, payload.description_es),
                )
        return service.public(document)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@router.get("/sessions/{session_id}")
async def get(session_id: str, request: Request):
    try:
        if session_id.startswith("freetext-operational-"):
            service = operational(request)
            if service is None:
                raise FreeTextUnavailable("servicio FreeText operacional no configurado")
            return service.public(service.load(session_id))
        service = historical(request)
        if service is None:
            raise FreeTextUnavailable("servicio FreeText histórico no configurado")
        return service.public(service.load(session_id))
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@router.post("/sessions/{session_id}/answers")
async def answer(
    session_id: str,
    payload: FreeTextAnswerRequest | OperationalFreeTextAnswerRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    gate = request.app.state.dialogue_gate
    try:
        if session_id.startswith("freetext-operational-"):
            service = operational(request)
            if service is None:
                raise FreeTextUnavailable("servicio FreeText operacional no configurado")
            if not isinstance(payload, OperationalFreeTextAnswerRequest):
                raise FreeTextConflict("contrato de respuesta operacional requerido")
            if not gate.try_acquire():
                raise HTTPException(status_code=409, detail={"code": "FREETEXT_BUSY", "message": "Otra transición está en curso."})
            try:
                document, execute = await anyio.to_thread.run_sync(
                    service.prepare_answer,
                    session_id,
                    payload.answer_literal,
                    payload.turn_index,
                    payload.question_id,
                    payload.question_sha256,
                    payload.client_operation_id,
                    idempotency_key or "",
                )
            except Exception:
                gate.release()
                raise

            async def run_answer():
                try:
                    await anyio.to_thread.run_sync(service.run_answer, session_id)
                finally:
                    gate.release()

            if execute:
                background_tasks.add_task(run_answer)
            else:
                gate.release()
            return service.public(document)

        service = historical(request)
        if service is None:
            raise FreeTextUnavailable("servicio FreeText histórico no configurado")
        if not gate.try_acquire():
            raise HTTPException(status_code=409, detail={"code": "FREETEXT_BUSY", "message": "Otra transición está en curso."})
        document = service.load(session_id)
        async with gate:
            updated = await transition(
                request,
                document["experimental_query_id"],
                lambda: service.answer(session_id, payload.answer_literal),
            )
        return service.public(updated)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@router.get("/sessions/{session_id}/events")
async def event_history(session_id: str, request: Request):
    try:
        service = operational(request)
        if service is None:
            raise FreeTextUnavailable("servicio FreeText operacional no configurado")
        return {
            "schema_version": "1.0",
            "contract_version": "atlas-dialogue-freetext-event-history-v1",
            "session_id": session_id,
            "events": service.events(session_id),
        }
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@router.get("/sessions/{session_id}/events/stream")
async def event_stream(
    session_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    follow: bool = False,
    after: str | None = None,
):
    if after is not None:
        last_event_id = after
    try:
        service = operational(request)
        if service is None:
            raise FreeTextUnavailable("servicio FreeText operacional no configurado")
        events = service.events(session_id, last_event_id)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)

    async def replay():
        cursor = last_event_id
        pending = list(events)
        while not await request.is_disconnected():
            if not pending:
                document = service.load(session_id)
                pending = service.events(session_id, cursor)
                if not pending:
                    if not follow or document["status"] in {"completed", "failed", "unknown"}:
                        break
                    yield ": keep-alive\n\n"
                    await asyncio.sleep(1)
                    continue
            for event in pending:
                cursor = event["event_id"]
                yield f"id: {event['event_id']}\nevent: session\ndata: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"
            pending = []
            if not follow:
                break

    return StreamingResponse(
        replay(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
