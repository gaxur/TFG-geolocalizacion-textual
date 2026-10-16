"""Selección fija y preflight de cobertura para el renderizado F4."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .f3_inputs import CatalogInput
from .f4_contracts import (
    F4_FULL_SELECTION_POLICY,
    F4_FULL_SELECTIONS,
    F4_SELECTED_CANDIDATES,
    F4_SELECTION_SHA256,
    F4_SELECTION_VERSION,
)
from .f4_geometry import bbox_contains, bbox_wgs84_to_epsg3857, candidate_raster_geometry
from .osm_snapshot import SnapshotConflictError, validate_local_snapshot
from .validation import SchemaValidationError, validate_document


class F4PreflightError(ValueError):
    """La selección o la fuente cartográfica no supera el preflight F4."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _logical_path(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise F4PreflightError(f"path fuera del proyecto: {path}") from error
    if not relative.parts:
        raise F4PreflightError("path lógico vacío")
    return relative.as_posix()


def build_osm_source_reference(snapshot_dir: str | Path, project_root: str | Path) -> dict[str, Any]:
    """Construye la referencia F4 de un snapshot local ya validado."""
    snapshot_path = Path(snapshot_dir)
    root = Path(project_root)
    try:
        provenance, raw = validate_local_snapshot(snapshot_path)
    except SnapshotConflictError as error:
        raise F4PreflightError("snapshot OSM local inválido") from error
    provenance_path = snapshot_path / "provenance.json"
    coverage = bbox_wgs84_to_epsg3857(provenance["bbox"])
    return {
        "contract_version": "f4-osm-source-v1",
        "source_id": provenance["osm_snapshot_id"],
        "source_type": "osm_snapshot",
        "data_path": _logical_path(snapshot_path / "source.osm", root),
        "data_sha256": sha256_bytes(raw),
        "provenance_path": _logical_path(provenance_path, root),
        "provenance_sha256": sha256_bytes(provenance_path.read_bytes()),
        "coverage_bbox_wgs84": dict(provenance["bbox"]),
        "coverage_bbox_epsg3857": coverage.as_document(),
        "selection": dict(provenance["selection"]),
        "closure": dict(provenance["closure"]),
        "license": provenance["license"],
        "attribution": provenance["attribution"],
    }


def load_verified_selection(path: str | Path, catalog: CatalogInput) -> tuple[Mapping[str, Any], str]:
    selection_path = Path(path)
    try:
        raw = selection_path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise F4PreflightError("selección F4 ilegible") from error
    try:
        validate_document(document, "f4_visual_selection")
    except SchemaValidationError as error:
        raise F4PreflightError("selección F4 incompatible") from error
    if document["evaluation_use"] is not False or document["text_or_ground_truth_used"] is not False:
        raise F4PreflightError("política de selección F4 no válida")
    if document["source_manifest_id"] != catalog.manifest_id or document["source_manifest_sha256"] != catalog.sha256:
        raise F4PreflightError("selección F4 no corresponde al manifest F1")
    digest = sha256_bytes(raw)
    if document["selection_id"] == F4_SELECTION_VERSION:
        actual = tuple((item.get("candidate_id"), item.get("role")) for item in document["candidates"] if isinstance(item, dict))
        if actual != F4_SELECTED_CANDIDATES or digest != F4_SELECTION_SHA256:
            raise F4PreflightError("la selección fija de nueve candidatos ha cambiado")
        known = {candidate.candidate_id for candidate in catalog.candidates}
        if any(candidate_id not in known for candidate_id, _ in actual):
            raise F4PreflightError("selección F4 contiene candidate_id ajeno a F1")
        return document, digest
    expected_full = F4_FULL_SELECTIONS.get(document["selection_id"])
    if (
        expected_full is None
        or document["selection_policy"] != F4_FULL_SELECTION_POLICY
        or document["candidate_count"] != expected_full["candidate_count"]
        or document["order"] != "catalog_manifest_order"
        or (catalog.spacing_m, catalog.cell_size_m) != (expected_full["spacing_m"], expected_full["cell_size_m"])
        or len(catalog.candidates) != expected_full["candidate_count"]
        or digest != expected_full["selection_sha256"]
    ):
        raise F4PreflightError("selección de galería completa F4 no válida")
    expanded = dict(document)
    expanded["candidates"] = [
        {"candidate_id": candidate.candidate_id, "role": "full_catalog"}
        for candidate in catalog.candidates
    ]
    return expanded, digest


def build_coverage_preflight(
    catalog: CatalogInput,
    selection: Mapping[str, Any],
    source_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    source_bbox = bbox_wgs84_to_epsg3857(source_provenance["bbox"])
    rows = []
    for selected in selection["candidates"]:
        candidate = candidates[selected["candidate_id"]]
        geometry = candidate_raster_geometry(candidate.latitude, candidate.longitude)
        covered = bbox_contains(source_bbox, geometry.output_bbox)
        deficits = {
            "west_m": max(0.0, source_bbox.min_x - geometry.output_bbox.min_x),
            "south_m": max(0.0, source_bbox.min_y - geometry.output_bbox.min_y),
            "east_m": max(0.0, geometry.output_bbox.max_x - source_bbox.max_x),
            "north_m": max(0.0, geometry.output_bbox.max_y - source_bbox.max_y),
        }
        rows.append({
            "candidate_id": candidate.candidate_id,
            "role": selected["role"],
            "latitude": candidate.latitude,
            "longitude": candidate.longitude,
            "covered": covered,
            "status": "covered" if covered else "requires_margin",
            "output_bbox": geometry.output_bbox.as_document(),
            "margin_deficit_m": deficits,
        })
    return {
        "schema_version": "1.0",
        "profile_id": "crosstext2loc-osm-z18-crop256-resize512-exp-v2",
        "selection_id": selection["selection_id"],
        "source_id": source_provenance.get("osm_snapshot_id", source_provenance.get("source_id")),
        "source_bbox_wgs84": dict(source_provenance["bbox"]),
        "source_bbox_epsg3857": source_bbox.as_document(),
        "covered_count": sum(row["covered"] for row in rows),
        "requires_margin_count": sum(not row["covered"] for row in rows),
        "candidates": rows,
    }


def preflight_local_snapshot(
    catalog: CatalogInput,
    selection: Mapping[str, Any],
    snapshot_dir: str | Path,
) -> dict[str, Any]:
    try:
        provenance, _ = validate_local_snapshot(snapshot_dir)
    except SnapshotConflictError as error:
        raise F4PreflightError("snapshot OSM local inválido") from error
    return build_coverage_preflight(catalog, selection, provenance)
