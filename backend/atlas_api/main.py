"""Factory FastAPI del MVP.1."""

from __future__ import annotations

import asyncio
import uuid
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .errors import install_error_handlers
from .lifespan import build_lifespan, default_retriever_factory, default_transformer_factory
from .routes.health import router as health_router
from .routes.retrieval import router as retrieval_router
from .settings import Settings


def create_app(*, settings: Settings | None = None, retriever_factory: Callable | None = None, transformer_factory: Callable | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    factory = retriever_factory or default_retriever_factory
    qwen_factory = transformer_factory or default_transformer_factory
    app = FastAPI(title="Geolocalización textual", version="2.0-experimental", lifespan=build_lifespan(settings, factory, qwen_factory))
    app.state.inference_gate = asyncio.Lock()
    app.state.reject_when_busy = settings.reject_when_busy
    app.state.search_area = {"region_id": "madrid_pilot", "crs": "EPSG:4326", "bbox": settings.region_bbox()}
    if settings.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Request-ID"], expose_headers=["X-Request-ID"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(retrieval_router)
    return app
