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
from .routes.dialogue import router as dialogue_router
from .routes.progress import router as progress_router
from .routes.retrieval import router as retrieval_router
from .progress import ProgressHub
from .dialogue_sessions import DialogueSessionService
from .settings import Settings


def create_app(*, settings: Settings | None = None, retriever_factory: Callable | None = None, transformer_factory: Callable | None = None, visual_factory: Callable | None = None, dialogue_executor=None) -> FastAPI:
    settings = settings or Settings.from_env()
    factory = retriever_factory or default_retriever_factory
    qwen_factory = transformer_factory or default_transformer_factory
    from .lifespan import default_visual_factory
    app = FastAPI(title="Geolocalización textual", version="3.0-experimental", lifespan=build_lifespan(settings, factory, qwen_factory, visual_factory or default_visual_factory))
    app.state.inference_gate = asyncio.Lock()
    app.state.progress_hub = ProgressHub()
    app.state.reject_when_busy = settings.reject_when_busy
    app.state.search_area = {"region_id": "madrid_pilot", "crs": "EPSG:4326", "bbox": settings.region_bbox()}
    app.state.dialogue_service = DialogueSessionService(cohort_path=settings.dialogue_cohort_path,session_root=settings.dialogue_session_root,image_root=settings.dialogue_image_root,executor=dialogue_executor if settings.dialogue_enabled else None,completed_query_ids=settings.dialogue_completed_query_ids,authorization_path=settings.dialogue_authorization_path)
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
    app.include_router(progress_router)
    app.include_router(dialogue_router)
    app.include_router(retrieval_router)
    return app
