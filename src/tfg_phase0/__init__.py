"""Contratos y validadores independientes de los modelos del TFG."""

from .config import load_region_config
from .catalog import build_catalog, candidate_id, f1_config_input, write_manifest
from .crs import epsg25830_to_wgs84, wgs84_to_epsg25830
from .f3_inputs import load_verified_f3_inputs
from .f4_contracts import experimental_visual_profile
from .f4_validation import load_verified_f1_50m, validate_visual_manifest
from .osm_snapshot import build_overpass_query, snapshot_id, validate_local_snapshot, validate_osm_xml
from .validation import SchemaValidationError, validate_document

__all__ = [
    "SchemaValidationError",
    "build_catalog",
    "candidate_id",
    "build_overpass_query",
    "epsg25830_to_wgs84",
    "f1_config_input",
    "load_region_config",
    "load_verified_f3_inputs",
    "load_verified_f1_50m",
    "snapshot_id",
    "validate_local_snapshot",
    "validate_document",
    "validate_visual_manifest",
    "validate_osm_xml",
    "wgs84_to_epsg25830",
    "write_manifest",
    "experimental_visual_profile",
]
