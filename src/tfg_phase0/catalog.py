"""Generación determinista del catálogo geométrico de Madrid."""

from __future__ import annotations

from collections.abc import Iterator
import json
import math
import re
from pathlib import Path
from typing import Any

from .crs import epsg25830_to_wgs84, wgs84_to_epsg25830
from .provenance import build_provenance, canonical_json, sha256_json
from .validation import SchemaValidationError, validate_document


ARTIFACT_FIELDS = (
    "osm_image", "osm_embedding", "satellite_image", "satellite_embedding",
    "scene_id", "scene_graph", "scene_embedding",
)
GRID_GENERATOR_VERSION = "phase1-grid-v1"
MANIFEST_GENERATOR_VERSION = "phase1-manifest-v2"


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} debe ser un entero positivo")
    return value


def candidate_id(prefix: str, catalog_version: str, grid_hash: str, spacing_m: int, cell_size_m: int, row: int, column: int) -> str:
    """Construye un ID estable a partir de la identidad del grid y de la celda."""
    normalized_version = re.sub(r"[^A-Z0-9]+", "_", catalog_version.upper()).strip("_")
    if not re.fullmatch(r"[A-Z][A-Z0-9]*", prefix) or not normalized_version:
        raise ValueError("candidate_id_prefix o catalog_version no son válidos")
    if not re.fullmatch(r"[0-9a-f]{12}", grid_hash):
        raise ValueError("grid_hash debe contener 12 caracteres hexadecimales")
    return f"{prefix}_{normalized_version}_G{grid_hash.upper()}_S{spacing_m:03d}_L{cell_size_m:03d}_R{row:04d}_C{column:04d}"


def _inside_bbox(latitude: float, longitude: float, bbox: dict[str, float], tolerance: float = 1e-10) -> bool:
    return (
        bbox["south"] - tolerance <= latitude <= bbox["north"] + tolerance
        and bbox["west"] - tolerance <= longitude <= bbox["east"] + tolerance
    )


def catalog_grid_identity(
    config: dict[str, Any], *, spacing_m: int, cell_size_m: int
) -> dict[str, Any]:
    """Devuelve los parámetros que determinan la identidad de la cuadrícula."""
    return {
        "catalog_version": config["catalog"]["catalog_version"],
        "region_id": config["region"]["name"],
        "bbox": config["region"]["bbox"],
        "source_crs": config["region"]["crs"],
        "projected_crs": config["catalog"]["projected_crs"],
        "spacing_m": spacing_m,
        "cell_size_m": cell_size_m,
        "border_policy": config["catalog"]["border_policy"],
        "generator_version": GRID_GENERATOR_VERSION,
    }


def f1_config_input(config: dict[str, Any]) -> dict[str, Any]:
    """Extrae la configuración efectiva de F1 para su provenance."""
    region = config["region"]
    catalog = config["catalog"]
    return {
        "schema_version": config["schema_version"],
        "region": {
            "name": region["name"],
            "bbox": {
                "north": region["bbox"]["north"],
                "south": region["bbox"]["south"],
                "east": region["bbox"]["east"],
                "west": region["bbox"]["west"],
            },
            "crs": region["crs"],
        },
        "catalog": {
            "projected_crs": catalog["projected_crs"],
            "catalog_version": catalog["catalog_version"],
            "candidate_id_prefix": catalog["candidate_id_prefix"],
            "candidate_generation": catalog["candidate_generation"],
            "border_policy": catalog["border_policy"],
        },
    }


def catalog_projected_bounds(bbox: dict[str, float]) -> tuple[float, float, float, float]:
    """Calcula el sobre métrico usado como origen determinista de la cuadrícula."""
    corners_wgs84 = (
        (bbox["south"], bbox["west"]), (bbox["south"], bbox["east"]),
        (bbox["north"], bbox["west"]), (bbox["north"], bbox["east"]),
    )
    projected = [wgs84_to_epsg25830(lat, lon) for lat, lon in corners_wgs84]
    return (
        min(point[0] for point in projected),
        max(point[0] for point in projected),
        min(point[1] for point in projected),
        max(point[1] for point in projected),
    )


def build_candidate_entry(
    config: dict[str, Any], *, spacing_m: int, cell_size_m: int,
    grid_hash: str, row: int, column: int,
) -> dict[str, Any] | None:
    """Construye una celda F1 concreta con las reglas y redondeos canónicos."""
    bbox = config["region"]["bbox"]
    min_easting, max_easting, min_northing, max_northing = catalog_projected_bounds(bbox)
    columns = max(0, math.floor((max_easting - min_easting - cell_size_m) / spacing_m) + 1)
    rows = max(0, math.floor((max_northing - min_northing - cell_size_m) / spacing_m) + 1)
    if row < 0 or column < 0 or row >= rows or column >= columns:
        return None
    half = cell_size_m / 2
    easting = min_easting + half + column * spacing_m
    northing = min_northing + half + row * spacing_m
    projected_ring = [
        (easting - half, northing - half),
        (easting + half, northing - half),
        (easting + half, northing + half),
        (easting - half, northing + half),
        (easting - half, northing - half),
    ]
    ring_wgs84 = [epsg25830_to_wgs84(x, y) for x, y in projected_ring]
    center_latitude, center_longitude = epsg25830_to_wgs84(easting, northing)
    if not _inside_bbox(center_latitude, center_longitude, bbox):
        return None
    if not all(_inside_bbox(latitude, longitude, bbox) for latitude, longitude in ring_wgs84):
        return None
    return {
        "candidate_id": candidate_id(
            config["catalog"]["candidate_id_prefix"],
            config["catalog"]["catalog_version"],
            grid_hash,
            spacing_m,
            cell_size_m,
            row,
            column,
        ),
        "latitude": round(center_latitude, 10),
        "longitude": round(center_longitude, 10),
        "cell_geometry": {
            "type": "Polygon",
            "coordinates": [[[round(lon, 10), round(lat, 10)] for lat, lon in ring_wgs84]],
        },
        "artifacts": {field: None for field in ARTIFACT_FIELDS},
        "generation": {
            "row": row,
            "column": column,
            "center_easting_m": round(easting, 6),
            "center_northing_m": round(northing, 6),
        },
    }


def iter_catalog_candidates(
    config: dict[str, Any], *, spacing_m: int, cell_size_m: int,
    grid_hash: str,
) -> Iterator[dict[str, Any]]:
    """Itera todas las celdas válidas en el orden canónico de F1."""
    bbox = config["region"]["bbox"]
    min_easting, max_easting, min_northing, max_northing = catalog_projected_bounds(bbox)
    columns = max(0, math.floor((max_easting - min_easting - cell_size_m) / spacing_m) + 1)
    rows = max(0, math.floor((max_northing - min_northing - cell_size_m) / spacing_m) + 1)
    for row in range(rows):
        for column in range(columns):
            candidate = build_candidate_entry(
                config,
                spacing_m=spacing_m,
                cell_size_m=cell_size_m,
                grid_hash=grid_hash,
                row=row,
                column=column,
            )
            if candidate is not None:
                yield candidate


def build_catalog(
    config: dict[str, Any], *, spacing_m: int, cell_size_m: int | None = None,
    config_source: str = "config/madrid.yaml",
) -> dict[str, Any]:
    """Genera celdas cuadradas completas dentro de la bbox D004."""
    validate_document(config, "region_config")
    spacing_m = _positive_integer(spacing_m, "spacing_m")
    cell_size_m = spacing_m if cell_size_m is None else _positive_integer(cell_size_m, "cell_size_m")
    region = config["region"]
    catalog = config["catalog"]
    bbox = region["bbox"]
    identity = catalog_grid_identity(
        config, spacing_m=spacing_m, cell_size_m=cell_size_m
    )
    grid_hash = sha256_json(identity)[:12]
    candidates = list(iter_catalog_candidates(
        config,
        spacing_m=spacing_m,
        cell_size_m=cell_size_m,
        grid_hash=grid_hash,
    ))
    parameters = {
        "region_bbox_wgs84": bbox,
        "source_crs": region["crs"],
        "projected_crs": catalog["projected_crs"],
        "spacing_m": spacing_m,
        "cell_size_m": cell_size_m,
        "border_policy": catalog["border_policy"],
        "order": "row_south_to_north_then_column_west_to_east",
        "grid_hash": grid_hash,
        "generator_version": GRID_GENERATOR_VERSION,
    }
    manifest = {
        "schema_version": "1.0",
        "manifest_id": f"{catalog['catalog_version']}-s{spacing_m}-l{cell_size_m}",
        "region_id": region["name"],
        "catalog_version": catalog["catalog_version"],
        "osm_snapshot_id": None,
        "generation": parameters,
        "provenance": build_provenance(
            artifact_id=f"{catalog['catalog_version']}-s{spacing_m}-l{cell_size_m}",
            source=config_source,
            source_version=config["schema_version"],
            input_hashes={"f1_config": sha256_json(f1_config_input(config))},
            parameters=parameters,
            code_version=MANIFEST_GENERATOR_VERSION,
        ),
        "candidates": candidates,
    }
    validate_document(manifest, "manifest")
    return manifest


def write_manifest(manifest: dict[str, Any], path: str | Path) -> None:
    """Serializa de forma estable el manifest validado."""
    validate_document(manifest, "manifest")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
