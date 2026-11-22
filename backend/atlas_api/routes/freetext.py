"""API unificada para pilotos y sesiones FreeText-v1."""
from __future__ import annotations

import asyncio
import ipaddress
import json
from functools import partial

import anyio
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel,ConfigDict,Field

from backend.atlas_api.freetext_operational import OperationalFreeTextExpired
from backend.atlas_api.freetext_sessions import FreeTextConflict, FreeTextUnavailable
from backend.atlas_api.models import (
    FreeTextAnswerRequest,
    ApplicationFreeTextStartRequest,
    DQIterativeStartRequest,
    FreeTextPolicyStartRequest,
    FreeTextStartRequest,
    OperationalFreeTextAnswerRequest,
    DQIterativeAnswerRequest,
    DQIterativeStopRequest,
    OperationalFreeTextStartRequest,
)
from backend.atlas_api.progress import QueryProgress

router = APIRouter(prefix="/api/v1/dialogue-freetext")
supervisor_router = APIRouter(prefix="/internal/dq-supervised", include_in_schema=False)
class IterativeReview(BaseModel):
    model_config=ConfigDict(extra="forbid")
    approved:bool;review:dict;client_operation_id:str
class PilotTranslationDecision(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:str;review:dict;client_operation_id:str
class IterativeCancellation(BaseModel):
    model_config=ConfigDict(extra="forbid")
    client_operation_id:str
    reason:str="user_cancelled_incomplete_description"

class ReplayStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_operation_id: str = Field(pattern=r'^dq-replay-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

class ReplayTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_operation_id: str = Field(min_length=1, max_length=200)
    source_question_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    translated_question_es: str = Field(min_length=3, max_length=500)


class ManualVisualTranslation(ReplayTranslation):
    generation_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    author: str = Field(min_length=1, max_length=150)


def historical(request: Request):
    return getattr(request.app.state, "freetext_service", None)


def operational(request: Request):
    return getattr(request.app.state, "freetext_operational_service", None)


def application(request: Request):
    return getattr(request.app.state, "freetext_application_service", None)
def iterative(request:Request):return getattr(request.app.state,"dq_iterative_service",None)


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        allowed = ipaddress.ip_address(host).is_loopback
    except ValueError:
        allowed = host in {"localhost", "testclient"}
    proxy_marked = request.headers.get("X-Atlas-App-Loopback") == "1"
    try:
        proxy_private = ipaddress.ip_address(host).is_private
    except ValueError:
        proxy_private = False
    if not allowed and not (proxy_marked and proxy_private):
        raise HTTPException(status_code=403, detail={"code": "FREETEXT_LOOPBACK_ONLY", "message": "FreeText application solo admite acceso loopback."})


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


def supervised(request):
    service = iterative(request)
    # No aceptar el marcador de proxy de la API pública ni peticiones de navegador.
    if (service is None or service.supervisor is None or request.client is None
            or request.client.host not in {"127.0.0.1", "::1"}
            or any(key in request.headers for key in ("origin", "sec-fetch-site", "x-atlas-app-loopback", "x-forwarded-for"))):
        raise HTTPException(status_code=404)
    return service


@supervisor_router.post("/sessions/{session_id}/register-e0")
async def register_supervised(session_id: str, request: Request):
    service = supervised(request)
    try:
        meta, applied = await anyio.to_thread.run_sync(service.supervisor.register_e0, session_id)
        return {"applied": applied, "session": service.public(meta)}
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@supervisor_router.get("/sessions/{session_id}/expected")
async def expected_supervised(session_id: str, request: Request):
    service = supervised(request)
    try:
        return await anyio.to_thread.run_sync(service.supervisor.expected, session_id)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@supervisor_router.post("/sessions/{session_id}/terminals/{operation_id}")
async def consume_supervised(session_id: str, operation_id: str, request: Request):
    service = supervised(request)
    try:
        meta, applied = await anyio.to_thread.run_sync(service.supervisor.consume, session_id, operation_id)
        return {"applied": applied, "session": service.public(meta)}
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@supervisor_router.get('/sessions/{session_id}/visual-context')
async def visual_context(session_id: str, request: Request):
    service = supervised(request)
    try:
        return await anyio.to_thread.run_sync(service.supervisor.visual_context, session_id)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@supervisor_router.get('/sessions/{session_id}/final-visual/context')
async def final_visual_context(session_id: str, request: Request):
    service = supervised(request)
    try:
        return await anyio.to_thread.run_sync(service.supervisor.final_visual_context, session_id)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@supervisor_router.post('/sessions/{session_id}/final-visual')
async def consume_final_visual(session_id: str, request: Request):
    service = supervised(request)
    try:
        meta, applied = await anyio.to_thread.run_sync(service.supervisor.consume_final_visual, session_id)
        return {'applied': applied, 'session': service.public(meta)}
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@supervisor_router.post('/sessions/{session_id}/panels/{stage}')
async def receive_visual_panel(session_id: str, stage: str, request: Request):
    service = supervised(request)
    try:
        meta, applied = await anyio.to_thread.run_sync(service.supervisor.receive_panel, session_id, stage)
        return {'applied': applied, 'session': service.public(meta)}
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@supervisor_router.post('/sessions/{session_id}/translation-operations/{stage}/{question_sha256}')
async def prepare_visual_translation(session_id: str, stage: str, question_sha256: str, request: Request):
    service = supervised(request)
    try:
        meta, applied = await anyio.to_thread.run_sync(service.supervisor.prepare_translation, session_id, stage, question_sha256)
        return {'applied': applied, 'session': service.public(meta)}
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


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
    application_service = application(request)
    if application_service is not None:
        catalogue["policies"].append(application_service.policy())
    iterative_service=iterative(request)
    if iterative_service is not None:
        catalogue["policies"].append({**iterative_service.policy(),
                                      "historical_replay_available": iterative_service.historical is not None})
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


@router.get("/application/operations/{client_operation_id}")
async def application_operation(client_operation_id: str, request: Request):
    require_loopback(request)
    service = application(request)
    if service is None:
        raise HTTPException(status_code=404, detail={"code":"NOT_FOUND","message":"Modo application no configurado."})
    try:
        return service.public(service.session_for_create_operation(client_operation_id))
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)

@router.get("/iterative/operations/{client_operation_id}")
async def iterative_operation(client_operation_id:str,request:Request):
    require_loopback(request);service=iterative(request)
    if service is None:raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"DQ iterativo no configurado."})
    try:return service.public(service.session_for_create_operation(client_operation_id))
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)


@router.post('/iterative/historical-replays')
async def start_replay(payload: ReplayStart, request: Request,
                       idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    require_loopback(request)
    service = iterative(request)
    if service is None or service.historical is None:
        raise HTTPException(status_code=404, detail='Reproducción histórica no configurada')
    try:
        return service.public(await anyio.to_thread.run_sync(service.historical.start, service, payload.client_operation_id, idempotency_key))
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@router.post('/sessions/{session_id}/historical-translation')
async def replay_translation(session_id: str, payload: ReplayTranslation, request: Request):
    from backend.atlas_api.dq_historical_replay import record_translation
    require_loopback(request)
    service = iterative(request)
    if service is None or service.historical is None:
        raise HTTPException(status_code=404, detail='Reproducción histórica no configurada')
    try:
        return service.public(await anyio.to_thread.run_sync(partial(record_translation, service, session_id,
            text=payload.translated_question_es, source_hash=payload.source_question_sha256, operation_id=payload.client_operation_id)))
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)


@router.get('/sessions/{session_id}/historical-media/{ref}')
async def replay_media(session_id: str, ref: str, request: Request):
    require_loopback(request)
    service = iterative(request)
    if service is None or service.historical is None:
        raise HTTPException(status_code=404)
    try:
        meta = await anyio.to_thread.run_sync(service.load, session_id)
    except FreeTextConflict:
        raise HTTPException(status_code=404) from None
    if (meta.get('execution_mode') != 'historical_replay' or ref not in service.historical.media
            or meta['historical']['provenance'] != service.historical.provenance):
        raise HTTPException(status_code=404)
    return Response(service.historical.media[ref], media_type='image/jpeg', headers={
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Cross-Origin-Resource-Policy': 'same-origin'})


@router.get('/sessions/{session_id}/visual-media/{ref}')
async def supervised_visual_media(session_id: str, ref: str, request: Request):
    require_loopback(request)
    service = iterative(request)
    if service is None or service.supervisor is None:
        raise HTTPException(status_code=404)
    try:
        blob = await anyio.to_thread.run_sync(service.supervisor.media, session_id, ref)
    except FreeTextConflict:
        raise HTTPException(status_code=404) from None
    return Response(blob, media_type='image/jpeg', headers={
        'Cache-Control':'private, no-store', 'X-Content-Type-Options':'nosniff', 'Cross-Origin-Resource-Policy':'same-origin'})


@router.post('/sessions/{session_id}/visual-translation')
async def manual_visual_translation(session_id: str, payload: ManualVisualTranslation, request: Request):
    require_loopback(request)
    service = iterative(request)
    if service is None or service.supervisor is None:
        raise HTTPException(status_code=404)
    try:
        meta = await anyio.to_thread.run_sync(partial(service.supervisor.manual_translation, session_id,
            text=payload.translated_question_es, source_hash=payload.source_question_sha256, generation_sha=payload.generation_sha256,
            author=payload.author, operation_id=payload.client_operation_id))
        return service.public(meta)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)

@router.post("/iterative/preparations")
async def prepare_iterative(payload:DQIterativeStartRequest,request:Request,idempotency_key:str|None=Header(default=None,alias="Idempotency-Key")):
    require_loopback(request);service=iterative(request)
    if service is None:raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"DQ iterativo no configurado."})
    try:
        document,_=await anyio.to_thread.run_sync(service.prepare_waiting_authorization,payload.description_es,payload.client_operation_id,idempotency_key or "")
        return service.public(document)
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)


@router.post("/sessions")
async def start(
    payload: FreeTextStartRequest | FreeTextPolicyStartRequest | OperationalFreeTextStartRequest | ApplicationFreeTextStartRequest | DQIterativeStartRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    gate = request.app.state.dialogue_gate
    try:
        if isinstance(payload,DQIterativeStartRequest):
            require_loopback(request);service=iterative(request)
            if service is None:raise FreeTextUnavailable("servicio DQ iterativo no configurado")
            if not gate.try_acquire():raise HTTPException(status_code=409,detail={"code":"FREETEXT_BUSY","message":"Otra transición está en curso."})
            try:document,execute=await anyio.to_thread.run_sync(service.prepare_start,payload.description_es,payload.client_operation_id,idempotency_key or "")
            except Exception:gate.release();raise
            async def run_iterative_start():
                try:await anyio.to_thread.run_sync(service.run_start,document["session_id"])
                finally:gate.release()
            if execute:background_tasks.add_task(run_iterative_start)
            else:gate.release()
            return service.public(document)
        if isinstance(payload, ApplicationFreeTextStartRequest):
            require_loopback(request)
            service = application(request)
            if service is None:
                raise FreeTextUnavailable("servicio FreeText application no configurado")
            if not gate.try_acquire():
                raise HTTPException(status_code=409, detail={"code": "FREETEXT_BUSY", "message": "Otra transición está en curso."})
            try:
                document, execute = await anyio.to_thread.run_sync(service.prepare_start, payload.description_es, payload.client_operation_id, idempotency_key or "")
            except Exception:
                gate.release()
                raise

            async def run_application_start():
                try:
                    await anyio.to_thread.run_sync(service.run_start, document["session_id"])
                finally:
                    gate.release()

            if execute:
                background_tasks.add_task(run_application_start)
            else:
                gate.release()
            return service.public(document)
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
        if session_id.startswith("freetext-application-"):
            require_loopback(request)
            service = application(request)
            if service is None:
                raise FreeTextUnavailable("servicio FreeText application no configurado")
            return service.public(service.load(session_id))
        if session_id.startswith("dq-iterative-"):
            require_loopback(request);service=iterative(request)
            if service is None:raise FreeTextUnavailable("servicio DQ iterativo no configurado")
            return service.public(service.load(session_id))
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
    payload: FreeTextAnswerRequest | OperationalFreeTextAnswerRequest | DQIterativeAnswerRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    gate = request.app.state.dialogue_gate
    try:
        if session_id.startswith("dq-iterative-"):
            require_loopback(request);service=iterative(request)
            if service is None:raise FreeTextUnavailable("servicio DQ iterativo no configurado")
            if not isinstance(payload,DQIterativeAnswerRequest):raise FreeTextConflict("contrato de respuesta DQ iterativa requerido")
            if not gate.try_acquire():raise HTTPException(status_code=409,detail={"code":"FREETEXT_BUSY","message":"Otra transición está en curso."})
            try:document,execute=await anyio.to_thread.run_sync(partial(service.prepare_answer,session_id,answer=payload.answer_literal,turn_index=payload.turn_index,question_id=payload.question_id,question_sha256=payload.question_sha256,client_operation_id=payload.client_operation_id,idempotency_key=idempotency_key or "",user_requests_stop=payload.user_requests_stop))
            except Exception:gate.release();raise
            async def run_iterative_answer():
                try:await anyio.to_thread.run_sync(service.run_answer,session_id)
                finally:gate.release()
            if execute:background_tasks.add_task(run_iterative_answer)
            else:gate.release()
            return service.public(document)
        if session_id.startswith("freetext-application-"):
            require_loopback(request)
            service = application(request)
            if service is None:
                raise FreeTextUnavailable("servicio FreeText application no configurado")
            if not isinstance(payload, OperationalFreeTextAnswerRequest):
                raise FreeTextConflict("contrato de respuesta application requerido")
            if not gate.try_acquire():
                raise HTTPException(status_code=409, detail={"code": "FREETEXT_BUSY", "message": "Otra transición está en curso."})
            try:
                document, execute = await anyio.to_thread.run_sync(service.prepare_answer, session_id, payload.answer_literal, payload.turn_index, payload.question_id, payload.question_sha256, payload.client_operation_id, idempotency_key or "")
            except Exception:
                gate.release()
                raise

            async def run_application_answer():
                try:
                    await anyio.to_thread.run_sync(service.run_answer, session_id)
                finally:
                    gate.release()

            if execute:
                background_tasks.add_task(run_application_answer)
            else:
                gate.release()
            return service.public(document)
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

@router.post("/sessions/{session_id}/stop")
async def stop_iterative(session_id:str,payload:DQIterativeStopRequest,request:Request,background_tasks:BackgroundTasks,idempotency_key:str|None=Header(default=None,alias="Idempotency-Key")):
    require_loopback(request);service=iterative(request);gate=request.app.state.dialogue_gate
    if service is None or not session_id.startswith("dq-iterative-"):raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"Sesión DQ iterativa no encontrada."})
    try:
        if not gate.try_acquire():raise HTTPException(status_code=409,detail={"code":"FREETEXT_BUSY","message":"Otra transición está en curso."})
        try:document,execute=await anyio.to_thread.run_sync(partial(service.prepare_answer,session_id,answer=payload.answer_literal,turn_index=payload.turn_index,question_id=payload.question_id,question_sha256=payload.question_sha256,client_operation_id=payload.client_operation_id,idempotency_key=idempotency_key or "",user_requests_stop=True))
        except Exception:gate.release();raise
        async def run_stop():
            try:await anyio.to_thread.run_sync(service.run_answer,session_id)
            finally:gate.release()
        if execute:background_tasks.add_task(run_stop)
        else:gate.release()
        return service.public(document)
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)

@router.post("/sessions/{session_id}/cancel")
async def cancel_iterative(session_id:str,payload:IterativeCancellation,request:Request):
    require_loopback(request);service=iterative(request)
    if service is None or not session_id.startswith("dq-iterative-"):raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"Sesión DQ iterativa no encontrada."})
    try:return service.public(await anyio.to_thread.run_sync(partial(service.cancel_waiting_authorization,session_id,operation_id=payload.client_operation_id,reason=payload.reason)))
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)

@router.post("/sessions/{session_id}/panel-reviews")
async def panel_review(session_id:str,payload:IterativeReview,request:Request):
    require_loopback(request);service=iterative(request)
    if service is None:raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"DQ iterativo no configurado."})
    try:return service.public(await anyio.to_thread.run_sync(partial(service.review_panel,session_id,approved=payload.approved,review=payload.review,operation_id=payload.client_operation_id)))
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)
@router.post("/sessions/{session_id}/question-reviews")
async def question_review(session_id:str,payload:IterativeReview,request:Request):
    require_loopback(request);service=iterative(request)
    if service is None:raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"DQ iterativo no configurado."})
    try:return service.public(await anyio.to_thread.run_sync(partial(service.review_question,session_id,approved=payload.approved,review=payload.review,operation_id=payload.client_operation_id)))
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)
@router.post("/sessions/{session_id}/translation-reviews")
async def translation_review(session_id:str,payload:IterativeReview,request:Request):
    require_loopback(request);service=iterative(request)
    if service is None:raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"DQ iterativo no configurado."})
    try:return service.public(await anyio.to_thread.run_sync(partial(service.review_translation,session_id,approved=payload.approved,review=payload.review,operation_id=payload.client_operation_id)))
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)
@router.post("/sessions/{session_id}/pilot-translation-decisions")
async def pilot_translation_decision(session_id:str,payload:PilotTranslationDecision,request:Request):
    require_loopback(request);service=iterative(request)
    if service is None:raise HTTPException(status_code=404,detail={"code":"NOT_FOUND","message":"DQ iterativo no configurado."})
    try:return service.public(await anyio.to_thread.run_sync(partial(service.decide_pilot_translation,session_id,decision=payload.decision,review=payload.review,operation_id=payload.client_operation_id)))
    except (FreeTextConflict,FreeTextUnavailable) as error:fail(error)


@router.get("/sessions/{session_id}/events")
async def event_history(session_id: str, request: Request):
    try:
        service = iterative(request) if session_id.startswith("dq-iterative-") else application(request) if session_id.startswith("freetext-application-") else operational(request)
        if session_id.startswith(("freetext-application-","dq-iterative-")):
            require_loopback(request)
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
        service = iterative(request) if session_id.startswith("dq-iterative-") else application(request) if session_id.startswith("freetext-application-") else operational(request)
        if session_id.startswith(("freetext-application-","dq-iterative-")):
            require_loopback(request)
        if service is None:
            raise FreeTextUnavailable("servicio FreeText operacional no configurado")
        events = await anyio.to_thread.run_sync(service.events, session_id, last_event_id)
    except (FreeTextConflict, FreeTextUnavailable) as error:
        fail(error)

    async def replay():
        cursor = last_event_id
        pending = list(events)
        while not await request.is_disconnected():
            if not pending:
                document = await anyio.to_thread.run_sync(service.load, session_id)
                pending = await anyio.to_thread.run_sync(service.events, session_id, cursor)
                if not pending:
                    waiting_supervisor = (session_id.startswith('dq-iterative-') and any(service.public(document).get(k) for k in
                        ('waiting_supervised_panel', 'waiting_supervised_translation'))) if document['status'] == 'waiting_review' else False
                    if not follow or (not waiting_supervisor and document["status"] in {"completed", "failed", "unknown", "waiting_review", "cancelled"}):
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
