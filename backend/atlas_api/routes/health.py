"""Liveness, readiness y capacidades reales."""

from fastapi import APIRouter, Request

from ..models import ErrorResponse
from ..errors import ApiInternalError
from ..errors import ApiServiceUnavailable


router = APIRouter(prefix="/api/v1")


@router.get("/health/live")
async def live():
    return {"status": "ok", "service": "atlas-api", "api_version": "v1"}


@router.get("/health/ready", responses={500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def ready(request: Request):
    retriever = getattr(request.app.state, "retriever", None)
    if retriever is None:
        raise ApiServiceUnavailable("RUNTIME_NOT_READY", "El recuperador todavía no está disponible.")
    try:
        gallery_ids = list(retriever.gallery_ids)
    except Exception as error:
        raise ApiInternalError("readiness failure") from error
    return {"status": "ready", "runtime": "crosstext2loc", "gallery_ids": gallery_ids, "processing_modes": {"no_llm": True, "with_llm": getattr(request.app.state, "transformer", None) is not None}}


@router.get("/capabilities", responses={500: {"model": ErrorResponse}})
async def capabilities(request: Request):
    retriever = getattr(request.app.state, "retriever", None)
    try:
        galleries = [] if retriever is None else [{"gallery_id": gallery_id, "candidate_count": retriever.gallery_count(gallery_id)} for gallery_id in retriever.gallery_ids]
    except Exception as error:
        raise ApiInternalError("capabilities failure") from error
    qwen = getattr(request.app.state, "transformer", None)
    visual = getattr(request.app.state, "visual_promoter", None)
    return {"schema_version": "1.0", "api_version": "v3-experimental", "retrievers": [{"id": "crosstext2loc", "available": retriever is not None, "scores_are_probabilities": False}], "processing_modes": [{"id": "no_llm", "available": retriever is not None, "variant": "es_original"}, {"id": "with_llm", "available": retriever is not None and qwen is not None, "variant": "en_cartographic", "experimental": True}], "postprocessing_capabilities": [{"id": "topn_visual_promotion", "available": visual is not None, "enabled": visual is not None, "experimental": True, "source": "precomputed_qwen3_vl" if visual is not None else None, "supported_reserve_k": [10, 20, 50, 100, 200, 500, "full"], "output_top_k": 10, "fallback": "baseline"}, {"id": "visual_contradiction_discard", "available": False, "enabled": False, "experimental": True, "reason": "contradiction_not_independently_validated"}], "galleries": galleries, "search_area": request.app.state.search_area, "supported_languages": {"policy_status": "experimental", "accepted_codes": ["es"]}}
