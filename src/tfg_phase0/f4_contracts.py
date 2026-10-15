"""Constantes y perfil experimental de los contratos visuales F4."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


F4_VISUAL_CONTRACT_VERSION = "f4-visual-dataset-v1"
F4_VISUAL_GENERATOR_VERSION = "phase4-visual-dataset-v1"
F4_EMBEDDING_CONTRACT_VERSION = "f4-image-embeddings-v1"
F4_RETRIEVAL_CONTRACT_VERSION = "f4-exhaustive-retrieval-v1"

F4_EXPERIMENTAL_PROFILE_ID = "crosstext2loc-osm-z18-crop256-resize512-exp-v1"
F4_PROFILE_STATUS = "experimental_unconfirmed"
F4_EMBEDDING_DIMENSION = 768

F4_IMAGE_STATUSES = ("generated", "failed", "insufficient_source")

_EXPERIMENTAL_VISUAL_PROFILE: dict[str, Any] = {
    "profile_id": F4_EXPERIMENTAL_PROFILE_ID,
    "compatibility_status": F4_PROFILE_STATUS,
    "modality": "osm_raster_map",
    "center_source": "f1_candidate_center_wgs84",
    "render_crs": "EPSG:3857",
    "orientation": "north_up",
    "zoom_reference": 18,
    "requested_half_extent_projected_m": 33.6256,
    "crop": {
        "width_px": 256,
        "height_px": 256,
        "anchor": "candidate_projected_pixel",
    },
    "output": {
        "width_px": 512,
        "height_px": 512,
        "color_mode": "RGB",
        "format": "PNG",
        "resize_interpolation": "bicubic",
    },
    "model_preprocessing": {
        "implementation": "openai_clip",
        "model": "ViT-L/14@336px",
        "input_width_px": 336,
        "input_height_px": 336,
        "policy": "official_clip_preprocess",
    },
    "evidence": {
        "upstream_repository_commit": "6910d2747a94fbe985309bde60cd4732bcbbf50f",
        "upstream_script": "external/CVG-Text/download_osm_street.py",
        "decision": "D007",
        "limitation": "upstream_script_saves_img_instead_of_computed_img_crop",
    },
}


def experimental_visual_profile() -> dict[str, Any]:
    """Devuelve una copia del perfil D007 experimental, nunca una referencia mutable."""
    return deepcopy(_EXPERIMENTAL_VISUAL_PROFILE)
