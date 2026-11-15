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
    freetext_operational = getattr(request.app.state, "freetext_operational_service", None)
    if retriever is None and not (freetext_operational and freetext_operational.enabled):
        raise ApiServiceUnavailable("RUNTIME_NOT_READY", "El recuperador todavía no está disponible.")
    if retriever is None:
        return {"status": "ready", "runtime": "freetext-sequential-workers", "gallery_ids": ["madrid-50m"], "processing_modes": {"no_llm": False, "with_llm": False}}
    try:
        gallery_ids = list(retriever.gallery_ids)
    except Exception as error:
        raise ApiInternalError("readiness failure") from error
    return {"status": "ready", "runtime": "crosstext2loc", "gallery_ids": gallery_ids, "processing_modes": {"no_llm": True, "with_llm": getattr(request.app.state, "transformer", None) is not None}}


@router.get("/capabilities", responses={500: {"model": ErrorResponse}})
async def capabilities(request: Request):
    retriever = getattr(request.app.state, "retriever", None)
    try:
        galleries = ([{"gallery_id": "madrid-50m", "candidate_count": 253}] if retriever is None and getattr(request.app.state, "freetext_operational_service", None) is not None else [] if retriever is None else [{"gallery_id": gallery_id, "candidate_count": retriever.gallery_count(gallery_id)} for gallery_id in retriever.gallery_ids])
    except Exception as error:
        raise ApiInternalError("capabilities failure") from error
    qwen = getattr(request.app.state, "transformer", None)
    visual = getattr(request.app.state, "visual_promoter", None)
    progress_available = getattr(request.app.state, "progress_hub", None) is not None
    dialogue = getattr(request.app.state, "dialogue_service", None)
    freetext = getattr(request.app.state, "freetext_service", None)
    freetext_operational = getattr(request.app.state, "freetext_operational_service", None)
    freetext_policies = [] if freetext is None else freetext.policies()["policies"]
    if freetext_operational is not None:
        freetext_policies.append(freetext_operational.policy())
    return {
        "schema_version": "1.0",
        "api_version": "v3-experimental",
        "retrievers": [{"id": "crosstext2loc", "available": retriever is not None, "scores_are_probabilities": False}],
        "processing_modes": [
            {"id": "no_llm", "available": retriever is not None, "variant": "es_original"},
            {"id": "with_llm", "available": retriever is not None and qwen is not None, "variant": "en_cartographic", "experimental": True},
        ],
        "postprocessing_capabilities": [
            {"id": "topn_visual_promotion", "available": visual is not None, "enabled": visual is not None, "experimental": True, "source": "precomputed_qwen3_vl" if visual is not None else None, "online_inference": False, "supported_reserve_k": [10, 20, 50, 100, 200, 500, "full"], "output_top_k": 10, "fallback": "baseline"},
            {"id": "visual_contradiction_discard", "available": False, "enabled": False, "experimental": True, "reason": "contradiction_not_independently_validated"},
        ],
        "pipeline_progress": {
            "transport": "sse" if progress_available else "none",
            "endpoint_template": "/api/v1/progress/{query_id}" if progress_available else None,
            "stages": [
                {"id": "llm", "available": qwen is not None, "operation": "optional_en_cartographic_transform"},
                {"id": "crosstext2loc", "available": retriever is not None, "operation": "text_encoding_and_exhaustive_gallery_ranking"},
                {"id": "vlm", "available": visual is not None, "source": "precomputed_qwen3_vl" if visual is not None else None, "online_inference": False},
                {"id": "dialoguevpr", "available": bool(dialogue and dialogue.available), "reason": None if dialogue and dialogue.available else "runtime_or_dataset_not_configured"},
                {"id": "freetext", "available": freetext is not None or freetext_operational is not None, "operation": "literal_dialogue_e0_e3" if freetext is not None or freetext_operational is not None else None},
            ],
        },
        "galleries": galleries,
        "search_area": request.app.state.search_area,
        "supported_languages": {"policy_status": "experimental", "accepted_codes": ["es"]},
        "freetext_policies": freetext_policies,
    }
