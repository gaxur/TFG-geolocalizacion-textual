"""Transporte HTTP fino sobre CrossText2LocRetriever."""

import asyncio
from functools import partial

import anyio
from fastapi import APIRouter, Depends, Request

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, CrossText2LocRuntimeError, RetrievalInputError, validate_retrieval_request

from ..dependencies import get_retriever
from ..errors import ApiInternalError, ApiServiceUnavailable
from ..models import ErrorResponse, RetrievalRequest, RetrievalResponse


router = APIRouter(prefix="/api/v1")


ERROR_RESPONSES = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post("/retrievals", response_model=RetrievalResponse, responses=ERROR_RESPONSES)
async def retrieve(payload: RetrievalRequest, request: Request, retriever: CrossText2LocRetriever = Depends(get_retriever)):
    gate: asyncio.Lock = request.app.state.inference_gate
    if request.app.state.reject_when_busy and gate.locked():
        raise ApiServiceUnavailable("RUNTIME_BUSY", "El recuperador está procesando otra consulta.")
    document = payload.model_dump()
    validate_retrieval_request(document, retriever.gallery_ids)
    query = document["query"]
    async with gate:
        call = partial(retriever.retrieve_many, gallery_ids=document["gallery_ids"], query_id=query["query_id"], text=query["text"], language=query["language"], k=document["top_k"])
        try:
            return await anyio.to_thread.run_sync(call)
        except (RetrievalInputError, CrossText2LocRuntimeError):
            raise
        except Exception as error:
            raise ApiInternalError("unexpected retrieval failure") from error
