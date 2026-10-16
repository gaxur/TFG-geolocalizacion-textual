"""Configuración explícita del servicio HTTP interno."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    runtime_config: Path
    region_config: Path
    cvg_utils_sha256: str
    clip_weights_path: str
    allowed_origins: tuple[str, ...]
    reject_when_busy: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        runtime_config = Path(os.environ.get("ATLAS_RUNTIME_CONFIG", ROOT / "config/madrid_f46_retriever.json"))
        region_config = Path(os.environ.get("ATLAS_REGION_CONFIG", ROOT / "config/madrid.yaml"))
        try:
            cvg_utils_sha256 = os.environ["ATLAS_CVG_UTILS_SHA256"]
            clip_weights_path = os.environ["CLIP_WEIGHTS_PATH"]
        except KeyError as error:
            raise ValueError(f"variable obligatoria ausente: {error.args[0]}") from error
        origins = tuple(value.strip() for value in os.environ.get("ATLAS_ALLOWED_ORIGINS", "").split(",") if value.strip())
        return cls(runtime_config, region_config, cvg_utils_sha256, clip_weights_path, origins)
