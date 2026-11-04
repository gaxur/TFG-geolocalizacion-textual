"""Pipeline HTTP experimental con una galería y transformación Qwen opcional."""

import asyncio
from functools import partial

import anyio
from fastapi import APIRouter, Depends, Request

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, CrossText2LocRuntimeError, GalleryNotLoadedError, RetrievalInputError
from src.tfg_phase0.f5_text_transform import GenerationConfig, TextTransformationError, validate_transformation

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
    document = payload.model_dump(); query = document["query"]
    gallery_id = document["gallery_id"]
    if gallery_id not in retriever.gallery_ids:
        raise GalleryNotLoadedError(gallery_id)
    if document["top_k"] > retriever.gallery_count(gallery_id):
        raise RetrievalInputError("Top-K supera el tamaño de la galería")
    async with gate:
        try:
            effective_text, effective_language, transformation_ms = query["text"], query["language"], 0.0
            transformer_metadata = None
            if document["processing_mode"] == "with_llm":
                transformer = getattr(request.app.state, "transformer", None)
                if transformer is None:
                    raise ApiServiceUnavailable("LLM_NOT_READY", "El modo Con LLM no está disponible en este arranque.")
                transform_call = partial(transformer.transform, query["text"], "translate_en_cartographic", [], GenerationConfig())
                try:
                    transformed = await anyio.to_thread.run_sync(transform_call)
                except TextTransformationError as error:
                    raise ApiServiceUnavailable("TRANSFORMATION_FAILED", "Qwen no pudo transformar la descripción.") from error
                validation = validate_transformation(query["text"], transformed.text, "translate_en_cartographic", [], GenerationConfig())
                if not validation["structurally_valid"]:
                    raise ApiServiceUnavailable("TRANSFORMATION_REJECTED", "La transformación no superó los controles automáticos.")
                effective_text, effective_language, transformation_ms = transformed.text, "en", transformed.duration_ms
                transformer_metadata = {"model_id": transformer.metadata.model_id, "revision": transformer.metadata.revision, "prompt_version": "f53b-text-transform-v2"}
            visual = getattr(request.app.state, "visual_promoter", None)
            reserve_k = max(document["top_k"], int(getattr(visual, "reserve_k", document["top_k"])))
            call = partial(retriever.retrieve_many, gallery_ids=(gallery_id,), query_id=query["query_id"], text=effective_text, language=effective_language, k=reserve_k)
            result = await anyio.to_thread.run_sync(call)
            retrieval_timings = result["timings_ms"]
            variant = "en_cartographic" if document["processing_mode"] == "with_llm" else "es_original"
            if visual is None:
                baseline = result["retrievals"][0]["results"]
                visual_result = {"status": "disabled", "source": "none", "request_id": None, "reason": "visual_postprocessor_not_configured", "model": None, "policy_id": None, "baseline_results": baseline, "final_results": baseline, "evidence": []}
            else:
                visual_call = partial(visual.apply, query_text=effective_text, processing_variant=variant, retrieval=result["retrievals"][0])
                visual_result = await anyio.to_thread.run_sync(visual_call)
            public_retrieval = {**result["retrievals"][0], "requested_k": document["top_k"], "effective_k": document["top_k"], "results": result["retrievals"][0]["results"][:document["top_k"]]}
            return {"schema_version": "1.0", "contract_version": "atlas-experimental-retrieval-response-v3", "query": query, "processing": {"mode": document["processing_mode"], "variant": variant, "effective_query": {"query_id": query["query_id"], "text": effective_text, "language": effective_language}, "transformer": transformer_metadata}, "model": result["model"], "retrievals": [public_retrieval], "visual_postprocessing": visual_result, "timings_ms": {"transformation": transformation_ms, "text_encoding": retrieval_timings["text_encoding"], "ranking_by_gallery": retrieval_timings["ranking_by_gallery"], "total": transformation_ms + retrieval_timings["total"]}}
        except (RetrievalInputError, CrossText2LocRuntimeError):
            raise
        except ApiServiceUnavailable:
            raise
        except Exception as error:
            raise ApiInternalError("unexpected retrieval failure") from error
