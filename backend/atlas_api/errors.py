"""Errores HTTP estables sin exponer detalles internos."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.tfg_phase0.crosstext2loc_runtime import (
    CrossText2LocRuntimeError,
    GalleryNotLoadedError,
    InferenceError,
    ModelCompatibilityError,
    ResourceConfigurationError,
    ResourceIntegrityError,
    RetrievalInputError,
    RuntimeClosedError,
)

from .models import ErrorDetail, ErrorResponse


LOGGER = logging.getLogger("atlas_api")


class ApiServiceUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.public_message = message


class ApiInternalError(RuntimeError):
    pass


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, request_id=_request_id(request)))
    return JSONResponse(status_code=status, content=body.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, error: RequestValidationError):
        return _response(request, 422, "INVALID_REQUEST", "La petición no cumple el contrato requerido.")

    @app.exception_handler(RetrievalInputError)
    async def retrieval_input(request: Request, error: RetrievalInputError):
        return _response(request, 422, "INVALID_RETRIEVAL_INPUT", "La petición de recuperación no es válida.")

    @app.exception_handler(GalleryNotLoadedError)
    async def gallery_missing(request: Request, error: GalleryNotLoadedError):
        return _response(request, 404, "GALLERY_NOT_FOUND", "La galería solicitada no está disponible.")

    @app.exception_handler(RuntimeClosedError)
    async def runtime_closed(request: Request, error: RuntimeClosedError):
        return _response(request, 503, "RUNTIME_CLOSED", "El recuperador no está disponible.")

    @app.exception_handler(InferenceError)
    async def inference_failed(request: Request, error: InferenceError):
        LOGGER.exception("Inference failed; request_id=%s", _request_id(request))
        return _response(request, 503, "INFERENCE_FAILED", "No se pudo completar la inferencia.")

    @app.exception_handler(ResourceIntegrityError)
    @app.exception_handler(ResourceConfigurationError)
    @app.exception_handler(ModelCompatibilityError)
    async def runtime_integrity(request: Request, error: CrossText2LocRuntimeError):
        LOGGER.exception("Runtime integrity error; request_id=%s", _request_id(request))
        return _response(request, 503, "RUNTIME_INTEGRITY_ERROR", "Los recursos del recuperador no están disponibles.")

    @app.exception_handler(ApiServiceUnavailable)
    async def service_unavailable(request: Request, error: ApiServiceUnavailable):
        return _response(request, 503, error.code, error.public_message)

    @app.exception_handler(ApiInternalError)
    async def internal_error(request: Request, error: ApiInternalError):
        LOGGER.exception("Internal endpoint error; request_id=%s", _request_id(request))
        return _response(request, 500, "INTERNAL_ERROR", "Se produjo un error interno.")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception):
        LOGGER.exception("Unexpected API error; request_id=%s", _request_id(request))
        return _response(request, 500, "INTERNAL_ERROR", "Se produjo un error interno.")
