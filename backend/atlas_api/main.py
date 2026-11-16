"""Factory FastAPI del MVP.1."""

from __future__ import annotations

import json
import os
from pathlib import Path
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
from .routes.freetext import router as freetext_router
from .progress import ProgressHub
from .dialogue_sessions import DialogueSessionService
from .settings import Settings
from .dialogue_freetext_executor import FreeTextRuntimeExecutor
from .dialogue_executor import SequentialDialogueExecutor
from .freetext_operational import OperationalFreeTextSessionService
from .dialogue_sessions import sha256_file
from .model_gate import ModelGate


def create_app(*, settings: Settings | None = None, retriever_factory: Callable | None = None, transformer_factory: Callable | None = None, visual_factory: Callable | None = None, dialogue_executor=None, freetext_service=None, freetext_operational_service=None, operational_retriever_factory: Callable | None = None, operational_transformer_factory: Callable | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    factory = retriever_factory or default_retriever_factory
    qwen_factory = transformer_factory or default_transformer_factory
    from .lifespan import default_visual_factory
    lifespan_kwargs = {}
    if operational_retriever_factory is not None: lifespan_kwargs["operational_retriever_factory"] = operational_retriever_factory
    if operational_transformer_factory is not None: lifespan_kwargs["operational_transformer_factory"] = operational_transformer_factory
    app = FastAPI(title="Geolocalización textual", version="3.0-experimental", lifespan=build_lifespan(settings, factory, qwen_factory, visual_factory or default_visual_factory, **lifespan_kwargs))
    model_gate = ModelGate()
    app.state.model_gate = model_gate
    app.state.inference_gate = model_gate
    app.state.dialogue_gate = model_gate
    app.state.progress_hub = ProgressHub()
    app.state.reject_when_busy = settings.reject_when_busy
    app.state.search_area = {"region_id": "madrid_pilot", "crs": "EPSG:4326", "bbox": settings.region_bbox()}
    if dialogue_executor is None and settings.dialogue_enabled:
        required = ("ATLAS_QWEN_MODEL_PATH", "ATLAS_DIALOGUE_F3_BUNDLE", "ATLAS_OLLAMA_PS_URL")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(f"DialogueVPR requiere: {', '.join(missing)}")
        dialogue_executor = SequentialDialogueExecutor(qwen_model=Path(os.environ["ATLAS_QWEN_MODEL_PATH"]), runtime_config=settings.runtime_config, region_config=settings.region_config, f3_bundle=Path(os.environ["ATLAS_DIALOGUE_F3_BUNDLE"]), clip_weights=Path(settings.clip_weights_path), cvg_utils_sha256=settings.cvg_utils_sha256, ollama_ps_url=os.environ["ATLAS_OLLAMA_PS_URL"])
    app.state.dialogue_service = DialogueSessionService(cohort_path=settings.dialogue_cohort_path,session_root=settings.dialogue_session_root,image_root=settings.dialogue_image_root,executor=dialogue_executor if settings.dialogue_enabled else None,completed_query_ids=settings.dialogue_completed_query_ids,authorization_path=settings.dialogue_authorization_path)
    app.state.freetext_service = freetext_service
    if freetext_operational_service is None and settings.freetext_operational_enabled:
        required = ("ATLAS_QWEN_MODEL_PATH", "ATLAS_DIALOGUE_F3_BUNDLE", "ATLAS_OLLAMA_PS_URL")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(f"FreeText operacional requiere: {', '.join(missing)}")
        executor = FreeTextRuntimeExecutor(qwen_model=Path(os.environ["ATLAS_QWEN_MODEL_PATH"]), runtime_config=settings.runtime_config, region_config=settings.region_config, f3_bundle=Path(os.environ["ATLAS_DIALOGUE_F3_BUNDLE"]), clip_weights=Path(settings.clip_weights_path), cvg_utils_sha256=settings.cvg_utils_sha256, ollama_ps_url=os.environ["ATLAS_OLLAMA_PS_URL"])
        root = Path(__file__).resolve().parents[2]
        operational_policy = root / "config/dialogue_freetext_operational_v1.json"
        core_policy = root / "config/interactive_dialogue_freetext_v1.json"
        freetext_operational_service = OperationalFreeTextSessionService(session_root=settings.freetext_operational_session_root, executor=executor, enabled=True, authorization_root=settings.freetext_operational_authorization_root, execution_id=settings.freetext_operational_execution_id, policy_identity={"operational_policy_id":"dialogue-vpr-freetext-v1-operational","operational_policy_version":"1.0.0","operational_policy_sha256":sha256_file(operational_policy),"core_policy_id":"dialogue-vpr-freetext-v1","core_policy_version":"1.0.0","core_policy_sha256":sha256_file(core_policy)})
    app.state.freetext_operational_service = freetext_operational_service
    app.state.dialogue_variants = json.loads(settings.dialogue_variants_path.read_text()) if settings.dialogue_variants_path and settings.dialogue_variants_path.is_file() else {"schema_version":"1.0","contract_version":"description-length-experiments-v1","status":"not_configured","variant_count":0,"condition_count":0,"variants":[],"conditions":[]}
    if settings.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Request-ID", "Idempotency-Key", "Last-Event-ID"], expose_headers=["X-Request-ID"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_error_handlers(app)

    @app.get("/api/v1/dialogue/variants")
    async def dialogue_variants():
        return app.state.dialogue_variants
    app.include_router(health_router)
    app.include_router(progress_router)
    app.include_router(dialogue_router)
    app.include_router(retrieval_router)
    if freetext_service is not None or freetext_operational_service is not None: app.include_router(freetext_router)
    return app
