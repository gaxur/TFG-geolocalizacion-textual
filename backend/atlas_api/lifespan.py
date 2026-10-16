"""Carga y cierre explícitos del runtime CrossText2Loc."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

import anyio
from fastapi import FastAPI

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, load_runtime_config

from .settings import ROOT, Settings


def default_retriever_factory(settings: Settings) -> CrossText2LocRetriever:
    model, galleries = load_runtime_config(settings.runtime_config, project_root=ROOT, cvg_utils_sha256=settings.cvg_utils_sha256, clip_weights_path=Path(settings.clip_weights_path))
    return CrossText2LocRetriever.load(model_config=model, gallery_configs=galleries, region_config=settings.region_config, deep_validate_visual_assets=False)


def build_lifespan(settings: Settings, retriever_factory: Callable[[Settings], object]):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.retriever = None
        app.state.retriever = await anyio.to_thread.run_sync(retriever_factory, settings)
        try:
            yield
        finally:
            retriever = app.state.retriever
            if retriever is not None:
                await anyio.to_thread.run_sync(retriever.close)
                app.state.retriever = None
    return lifespan
