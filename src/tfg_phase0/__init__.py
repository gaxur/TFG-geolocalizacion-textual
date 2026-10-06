"""Contratos y validadores independientes de los modelos del TFG."""

from .config import load_region_config
from .catalog import build_catalog, candidate_id, write_manifest
from .crs import epsg25830_to_wgs84, wgs84_to_epsg25830
from .osm_snapshot import build_overpass_query, snapshot_id, validate_osm_xml
from .validation import SchemaValidationError, validate_document

__all__ = [
    "SchemaValidationError",
    "build_catalog",
    "candidate_id",
    "build_overpass_query",
    "epsg25830_to_wgs84",
    "load_region_config",
    "snapshot_id",
    "validate_document",
    "validate_osm_xml",
    "wgs84_to_epsg25830",
    "write_manifest",
]
