"""API de sesiones DialogueVPR persistentes y cegadas."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
import anyio
from ..dialogue_sessions import DialogueConflict, DialogueUnavailable
from ..models import DialogueAnswerRequest, DialogueStartRequest

router=APIRouter(prefix="/api/v1/dialogue")

def service(request: Request): return request.app.state.dialogue_service
def fail(error: Exception):
    status=503 if isinstance(error,DialogueUnavailable) else 409
    raise HTTPException(status_code=status,detail={"code":"DIALOGUE_NOT_READY" if status==503 else "DIALOGUE_CONFLICT","message":str(error)})

@router.get("/queries")
async def queries(request:Request): return service(request).catalogue()

@router.get("/queries/{query_id}/image")
async def image(query_id:str,request:Request):
    try:path=service(request).image_path(query_id)
    except (DialogueConflict,DialogueUnavailable) as error:fail(error)
    return FileResponse(path,media_type="image/jpeg",headers={"Cache-Control":"private, no-store"})

@router.post("/sessions")
async def start(payload:DialogueStartRequest,request:Request):
    gate=getattr(request.app.state,'dialogue_gate',None)
    if gate is not None and gate.locked():raise HTTPException(status_code=409,detail={"code":"DIALOGUE_BUSY","message":"Otra transición DialogueVPR está en curso."})
    try:
        if gate is None:document=await anyio.to_thread.run_sync(lambda:service(request).start(mode=payload.mode,query_id=payload.query_id,description=payload.description_es))
        else:
            async with gate:document=await anyio.to_thread.run_sync(lambda:service(request).start(mode=payload.mode,query_id=payload.query_id,description=payload.description_es))
    except (DialogueConflict,DialogueUnavailable) as error:fail(error)
    return service(request).public(document)

@router.get("/sessions/{session_id}")
async def get_session(session_id:str,request:Request):
    try:return service(request).public(service(request).load(session_id))
    except (DialogueConflict,DialogueUnavailable) as error:fail(error)

@router.post("/sessions/{session_id}/answers")
async def answer(session_id:str,payload:DialogueAnswerRequest,request:Request):
    gate=getattr(request.app.state,'dialogue_gate',None)
    if gate is not None and gate.locked():raise HTTPException(status_code=409,detail={"code":"DIALOGUE_BUSY","message":"Otra transición DialogueVPR está en curso."})
    try:
        if gate is None:document=await anyio.to_thread.run_sync(lambda:service(request).answer(session_id=session_id,answer=payload.answer_literal,answer_kind=payload.answer_kind))
        else:
            async with gate:document=await anyio.to_thread.run_sync(lambda:service(request).answer(session_id=session_id,answer=payload.answer_literal,answer_kind=payload.answer_kind))
    except (DialogueConflict,DialogueUnavailable) as error:fail(error)
    return service(request).public(document)
