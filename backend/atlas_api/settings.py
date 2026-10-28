"""Configuración explícita del servicio HTTP interno."""

from __future__ import annotations

from dataclasses import dataclass
import json
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
    qwen_model_path: Path | None = None
    qwen_model_id: str = "Qwen/Qwen3-8B"
    qwen_model_revision: str = "b968826d9c46dd6066d109eabc6255188de91218"
    qwen_required: bool = False
    visual_promotion_enabled: bool = False
    visual_promotion_policy_path: Path | None = None
    visual_promotion_fallback: str = "baseline"
    visual_promotion_required: bool = False

    def region_bbox(self) -> dict[str, float]:
        try:
            document = json.loads(self.region_config.read_text(encoding="utf-8"))
            bbox = document["region"]["bbox"]
            result = {key: float(bbox[key]) for key in ("north", "south", "east", "west")}
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"configuración regional inválida: {self.region_config}") from error
        if not (-90 <= result["south"] < result["north"] <= 90 and -180 <= result["west"] < result["east"] <= 180):
            raise ValueError(f"bbox regional inválida: {self.region_config}")
        return result

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
        qwen_path = os.environ.get("ATLAS_QWEN_MODEL_PATH")
        qwen_required = os.environ.get("ATLAS_QWEN_REQUIRED", "false").casefold() in {"1", "true", "yes"}
        if qwen_required and not qwen_path:
            raise ValueError("ATLAS_QWEN_MODEL_PATH es obligatorio cuando ATLAS_QWEN_REQUIRED=true")
        visual_enabled = os.environ.get("ATLAS_VISUAL_PROMOTION_ENABLED", "false").casefold() in {"1", "true", "yes"}
        visual_required = os.environ.get("ATLAS_VISUAL_PROMOTION_REQUIRED", "false").casefold() in {"1", "true", "yes"}
        visual_policy = os.environ.get("ATLAS_VISUAL_PROMOTION_POLICY")
        visual_fallback = os.environ.get("ATLAS_VISUAL_PROMOTION_FALLBACK", "baseline")
        if visual_fallback not in {"baseline", "error"}:
            raise ValueError("ATLAS_VISUAL_PROMOTION_FALLBACK inválido")
        if visual_enabled and not visual_policy:
            raise ValueError("ATLAS_VISUAL_PROMOTION_POLICY es obligatorio al habilitar promoción")
        return cls(runtime_config, region_config, cvg_utils_sha256, clip_weights_path, origins, True, Path(qwen_path) if qwen_path else None, os.environ.get("ATLAS_QWEN_MODEL_ID", "Qwen/Qwen3-8B"), os.environ.get("ATLAS_QWEN_MODEL_REVISION", "b968826d9c46dd6066d109eabc6255188de91218"), qwen_required, visual_enabled, Path(visual_policy) if visual_policy else None, visual_fallback, visual_required)
