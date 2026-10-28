"""Carga y cierre explícitos de CrossText2Loc y Qwen opcional residente."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

import anyio
from fastapi import FastAPI

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, load_runtime_config
from src.tfg_phase0.f5_text_transform import QwenTransformersAdapter

from .settings import ROOT, Settings


def default_retriever_factory(settings: Settings) -> CrossText2LocRetriever:
    model, galleries = load_runtime_config(settings.runtime_config, project_root=ROOT, cvg_utils_sha256=settings.cvg_utils_sha256, clip_weights_path=Path(settings.clip_weights_path))
    return CrossText2LocRetriever.load(model_config=model, gallery_configs=galleries, region_config=settings.region_config, deep_validate_visual_assets=False)


def default_transformer_factory(settings: Settings):
    if settings.qwen_model_path is None:
        return None
    return QwenTransformersAdapter(settings.qwen_model_path, model_id=settings.qwen_model_id, revision=settings.qwen_model_revision)


def build_lifespan(settings: Settings, retriever_factory: Callable[[Settings], object], transformer_factory: Callable[[Settings], object | None]):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.retriever = None
        app.state.transformer = None
        app.state.visual_promoter = None
        app.state.retriever = await anyio.to_thread.run_sync(retriever_factory, settings)
        try:
            app.state.transformer = await anyio.to_thread.run_sync(transformer_factory, settings)
            if settings.qwen_required and app.state.transformer is None:
                raise RuntimeError("Qwen requerido no disponible")
            if settings.visual_promotion_enabled:
                raise RuntimeError("promoción visual configurada pero no activada en el MVP")
        except Exception:
            await anyio.to_thread.run_sync(app.state.retriever.close)
            app.state.retriever = None
            raise
        try:
            yield
        finally:
            transformer = app.state.transformer
            if transformer is not None:
                await anyio.to_thread.run_sync(transformer.close)
                app.state.transformer = None
            retriever = app.state.retriever
            if retriever is not None:
                await anyio.to_thread.run_sync(retriever.close)
                app.state.retriever = None
    return lifespan
