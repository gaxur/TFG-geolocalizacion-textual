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
from ..progress import QueryProgress


router = APIRouter(prefix="/api/v1")


ERROR_RESPONSES = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post("/retrievals", response_model=RetrievalResponse, responses=ERROR_RESPONSES)
async def retrieve(payload: RetrievalRequest, request: Request, retriever: CrossText2LocRetriever = Depends(get_retriever)):
    gate: asyncio.Lock = request.app.state.inference_gate
    document = payload.model_dump()
    query = document["query"]
    gallery_id = document["gallery_id"]
    progress: QueryProgress = QueryProgress(request.app.state.progress_hub, query["query_id"])

    async def fail_current_stage() -> None:
        if progress.active_stage is not None:
            await progress.stage(progress.active_stage, "failed", "La etapa activa terminó con un error.")

    try:
        if request.app.state.reject_when_busy and gate.locked():
            await progress.pipeline("failed", "El recuperador está procesando otra consulta.", error_code="RUNTIME_BUSY")
            raise ApiServiceUnavailable("RUNTIME_BUSY", "El recuperador está procesando otra consulta.")
        if gallery_id not in retriever.gallery_ids:
            raise GalleryNotLoadedError(gallery_id)
        if document["top_k"] > retriever.gallery_count(gallery_id):
            raise RetrievalInputError("Top-K supera el tamaño de la galería")

        async with gate:
            await progress.pipeline("running", "Consulta aceptada; comienza el procesamiento.")
            effective_text = query["text"]
            effective_language = query["language"]
            transformation_ms = 0.0
            transformer_metadata = None

            if document["processing_mode"] == "with_llm":
                transformer = getattr(request.app.state, "transformer", None)
                if transformer is None:
                    await progress.stage("llm", "unavailable", "Qwen no está disponible en este arranque.")
                    await progress.stage("crosstext2loc", "skipped", "No se ejecuta CT2L si falla la transformación solicitada.")
                    await progress.stage("vlm", "skipped", "No se ejecuta el postprocesado visual.")
                    await progress.stage("dialoguevpr", "unavailable", "DialogueVPR no está integrado en el endpoint del MVP.")
                    await progress.pipeline("failed", "La etapa LLM no está disponible.", error_code="LLM_NOT_READY")
                    raise ApiServiceUnavailable("LLM_NOT_READY", "El modo Con LLM no está disponible en este arranque.")
                await progress.stage("llm", "running", "Qwen está transformando la descripción a en_cartographic.")
                transform_call = partial(transformer.transform, query["text"], "translate_en_cartographic", [], GenerationConfig())
                try:
                    transformed = await anyio.to_thread.run_sync(transform_call)
                except TextTransformationError as error:
                    await progress.stage("llm", "failed", "Qwen no pudo completar la transformación.")
                    await progress.stage("crosstext2loc", "skipped", "CT2L no se ejecuta tras fallar la transformación.")
                    await progress.stage("vlm", "skipped", "No se ejecuta el postprocesado visual.")
                    await progress.stage("dialoguevpr", "unavailable", "DialogueVPR no está integrado en el endpoint del MVP.")
                    await progress.pipeline("failed", "La transformación textual falló.", error_code="TRANSFORMATION_FAILED")
                    raise ApiServiceUnavailable("TRANSFORMATION_FAILED", "Qwen no pudo transformar la descripción.") from error
                except Exception:
                    await progress.stage("llm", "failed", "La etapa LLM terminó con un error.")
                    await progress.stage("crosstext2loc", "skipped", "CT2L no se ejecuta tras fallar la transformación.")
                    await progress.stage("vlm", "skipped", "No se ejecuta el postprocesado visual.")
                    await progress.stage("dialoguevpr", "unavailable", "DialogueVPR no está integrado en el endpoint del MVP.")
                    await progress.pipeline("failed", "La etapa LLM falló.", error_code="INTERNAL_ERROR")
                    raise ApiInternalError("unexpected retrieval failure")
                validation = validate_transformation(query["text"], transformed.text, "translate_en_cartographic", [], GenerationConfig())
                if not validation["structurally_valid"]:
                    await progress.stage("llm", "failed", "La transformación no superó los controles estructurales.")
                    await progress.stage("crosstext2loc", "skipped", "CT2L no se ejecuta tras rechazar la transformación.")
                    await progress.stage("vlm", "skipped", "No se ejecuta el postprocesado visual.")
                    await progress.stage("dialoguevpr", "unavailable", "DialogueVPR no está integrado en el endpoint del MVP.")
                    await progress.pipeline("failed", "La transformación fue rechazada.", error_code="TRANSFORMATION_REJECTED")
                    raise ApiServiceUnavailable("TRANSFORMATION_REJECTED", "La transformación no superó los controles automáticos.")
                effective_text, effective_language, transformation_ms = transformed.text, "en", transformed.duration_ms
                transformer_metadata = {"model_id": transformer.metadata.model_id, "revision": transformer.metadata.revision, "prompt_version": "f53b-text-transform-v2"}
                await progress.stage("llm", "completed", "La transformación y sus controles estructurales finalizaron.", elapsed_ms=transformation_ms)
            else:
                await progress.stage("llm", "skipped", "Omitido: la consulta usa el texto original en español.")

            visual = getattr(request.app.state, "visual_promoter", None)
            reserve_k = max(document["top_k"], int(getattr(visual, "reserve_k", document["top_k"])))
            await progress.stage("crosstext2loc", "running", "CT2L codifica el texto y ordena exhaustivamente la galería.")
            progress_callback = None
            if await request.app.state.progress_hub.has_subscribers(query["query_id"]):
                def progress_callback(phase: str, phase_state: str, elapsed_ms: float | None, phase_gallery: str | None) -> None:
                    messages = {
                        ("text_encoding", "running"): "Calculando la representación textual CLIP.",
                        ("text_encoding", "completed"): "Representación textual calculada.",
                        ("text_encoding", "failed"): "Falló la codificación textual.",
                        ("ranking", "running"): "Ordenando la galería completa por similitud coseno.",
                        ("ranking", "completed"): "Ranking exhaustivo de la galería calculado.",
                        ("ranking", "failed"): "Falló el ranking exhaustivo.",
                    }
                    operation = partial(
                        progress.subphase,
                        phase,
                        phase_state,
                        messages.get((phase, phase_state), "Subfase CT2L"),
                        elapsed_ms=elapsed_ms,
                        gallery_id=phase_gallery,
                    )
                    try:
                        anyio.from_thread.run(operation)
                    except Exception:
                        # La observabilidad no puede cambiar el cálculo/ranking.
                        return

            retrieve_kwargs = {
                "gallery_ids": (gallery_id,),
                "query_id": query["query_id"],
                "text": effective_text,
                "language": effective_language,
                "k": reserve_k,
            }
            if progress_callback is not None:
                retrieve_kwargs["progress_callback"] = progress_callback
            call = partial(retriever.retrieve_many, **retrieve_kwargs)
            try:
                result = await anyio.to_thread.run_sync(call)
            except Exception as error:
                await progress.stage("crosstext2loc", "failed", "La recuperación CT2L no finalizó.")
                await progress.stage("vlm", "skipped", "No se ejecuta el postprocesado visual.")
                await progress.stage("dialoguevpr", "unavailable", "DialogueVPR no está integrado en el endpoint del MVP.")
                await progress.pipeline("failed", "La recuperación no pudo completarse.", error_code="INFERENCE_FAILED")
                if isinstance(error, (RetrievalInputError, CrossText2LocRuntimeError)):
                    raise
                raise ApiInternalError("unexpected retrieval failure") from error
            retrieval_timings = result["timings_ms"]
            variant = "en_cartographic" if document["processing_mode"] == "with_llm" else "es_original"
            await progress.stage(
                "crosstext2loc", "completed", "La galería completa se ordenó; el Top-10 conserva el ranking CT2L.",
                elapsed_ms=retrieval_timings["total"],
            )

            if visual is None:
                baseline = result["retrievals"][0]["results"]
                visual_result = {"status": "disabled", "source": "none", "request_id": None, "reason": "visual_postprocessor_not_configured", "model": None, "policy_id": None, "baseline_results": baseline, "final_results": baseline, "evidence": []}
                await progress.stage("vlm", "skipped", "Omitido: el postprocesador de evidencia visual está deshabilitado.")
            else:
                await progress.stage("vlm", "running", "Etapa experimental: consultando evidencia Qwen3-VL precalculada; no se ejecuta el VLM en línea.")
                visual_call = partial(visual.apply, query_text=effective_text, processing_variant=variant, retrieval=result["retrievals"][0])
                try:
                    visual_result = await anyio.to_thread.run_sync(visual_call)
                except Exception as error:
                    await progress.stage("vlm", "failed", "Falló la aplicación de evidencia visual precalculada.")
                    await progress.stage("dialoguevpr", "unavailable", "DialogueVPR no está integrado en el endpoint del MVP.")
                    await progress.pipeline("failed", "El postprocesado visual falló.", error_code="INTERNAL_ERROR")
                    raise ApiInternalError("unexpected retrieval failure") from error
                if visual_result["status"] == "applied":
                    await progress.stage("vlm", "completed", "Se aplicó la promoción experimental usando evidencia precalculada.", outcome="applied")
                else:
                    await progress.stage("vlm", "completed", "La etapa experimental no encontró evidencia compatible; se conserva el baseline CT2L.", outcome="fallback_baseline")
            await progress.stage("dialoguevpr", "unavailable", "No disponible: DialogueVPR interactivo no está integrado en el endpoint FastAPI del MVP.")

            public_retrieval = {**result["retrievals"][0], "requested_k": document["top_k"], "effective_k": document["top_k"], "results": result["retrievals"][0]["results"][:document["top_k"]]}
            response_document = {"schema_version": "1.0", "contract_version": "atlas-experimental-retrieval-response-v3", "query": query, "processing": {"mode": document["processing_mode"], "variant": variant, "effective_query": {"query_id": query["query_id"], "text": effective_text, "language": effective_language}, "transformer": transformer_metadata}, "model": result["model"], "retrievals": [public_retrieval], "visual_postprocessing": visual_result, "timings_ms": {"transformation": transformation_ms, "text_encoding": retrieval_timings["text_encoding"], "ranking_by_gallery": retrieval_timings["ranking_by_gallery"], "total": transformation_ms + retrieval_timings["total"]}}
            await progress.pipeline("completed", "El procesamiento síncrono terminó; el Top-10 está disponible.")
            return response_document
    except (RetrievalInputError, CrossText2LocRuntimeError):
        if not progress.terminal:
            await fail_current_stage()
            await progress.pipeline("failed", "La consulta no superó la validación de recuperación.", error_code="INVALID_RETRIEVAL_INPUT")
        raise
    except ApiServiceUnavailable:
        if not progress.terminal:
            await fail_current_stage()
            await progress.pipeline("failed", "El servicio no pudo completar la consulta.", error_code="SERVICE_UNAVAILABLE")
        raise
    except ApiInternalError:
        if not progress.terminal:
            await fail_current_stage()
            await progress.pipeline("failed", "Se produjo un error interno.", error_code="INTERNAL_ERROR")
        raise
    except Exception as error:
        if not progress.terminal:
            await fail_current_stage()
            await progress.pipeline("failed", "Se produjo un error interno.", error_code="INTERNAL_ERROR")
        raise ApiInternalError("unexpected retrieval failure") from error
