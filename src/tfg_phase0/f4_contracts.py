"""Constantes y perfil experimental de los contratos visuales F4."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


F4_VISUAL_CONTRACT_VERSION = "f4-visual-dataset-v2"
F4_VISUAL_GENERATOR_VERSION = "phase4-visual-dataset-v2"
F4_SOURCE_CONTRACT_VERSION = "f4-osm-source-v1"
F4_RENDERER_CONTRACT_VERSION = "f4-renderer-provenance-v1"
F4_SELECTION_VERSION = "f4-nine-candidates-v1"
F4_SELECTION_SHA256 = "40cd0cf8e684aea65f6c782971bae8b8152824587e8a009fbce072e4706ffa6e"
F4_EMBEDDING_CONTRACT_VERSION = "f4-image-embeddings-v1"
F4_RETRIEVAL_CONTRACT_VERSION = "f4-exhaustive-retrieval-v1"

F4_EXPERIMENTAL_PROFILE_ID = "crosstext2loc-osm-z18-crop256-resize512-exp-v2"
F4_PROFILE_STATUS = "experimental_unconfirmed"
F4_EMBEDDING_DIMENSION = 768
F4_IMAGE_STATUSES = ("generated", "failed", "insufficient_source")
F4_ERROR_CODES = (
    "source_does_not_cover_output_bbox",
    "renderer_failed",
    "invalid_rendered_mosaic",
)

F4_SELECTED_CANDIDATES = (
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0001_C0001", "edge_southwest"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0004_C0008", "interior_south"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0004_C0016", "edge_east"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0008_C0001", "edge_west"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0008_C0004", "interior_west"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0008_C0008", "interior_center"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0008_C0012", "interior_east"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0013_C0008", "interior_north"),
    ("MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0016_C0008", "edge_north"),
)

_EXPERIMENTAL_VISUAL_PROFILE: dict[str, Any] = {
    "profile_id": F4_EXPERIMENTAL_PROFILE_ID,
    "compatibility_status": F4_PROFILE_STATUS,
    "modality": "osm_raster_map",
    "center_source": "f1_candidate_center_wgs84",
    "render_crs": "EPSG:3857",
    "orientation": "north_up",
    "zoom": 18,
    "tile_size_px": 256,
    "upstream_requested_half_extent_projected_m": 33.6256,
    "native_crop_width_px": 256,
    "native_crop_height_px": 256,
    "crop_anchor": "candidate_global_pixel_subpixel",
    "output_width_px": 512,
    "output_height_px": 512,
    "output_color_mode": "RGB",
    "output_format": "PNG",
    "resize_interpolation": "bicubic",
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
        "interpretation": "experimental_native_z18_crop_not_confirmed_training_profile",
    },
}


def experimental_visual_profile() -> dict[str, Any]:
    """Devuelve una copia del perfil D007 experimental, nunca una referencia mutable."""
    return deepcopy(_EXPERIMENTAL_VISUAL_PROFILE)
