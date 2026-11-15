"""Materializa geometrías F1 exactas para la vista cartográfica del MVP.

Este módulo solo publica geometrías de celdas procedentes del generador F1.
No contiene ni deriva ground truth, ranking, alturas de edificios o datos OSM.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .provenance import canonical_json
from .validation import validate_document


MAP_ASSETS_CONTRACT = "madrid-map-assets-v1"
GALLERIES = {25: "madrid-25m", 50: "madrid-50m"}
EXPECTED_CANDIDATE_COUNTS = {25: 1115, 50: 253}


class MapAssetError(ValueError):
    """Los artefactos de mapa no corresponden al catálogo esperado."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256((canonical_json(manifest) + "\n").encode("utf-8")).hexdigest()


def _geometry_signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
    generation = candidate["generation"]
    return (
        candidate["candidate_id"],
        candidate["latitude"],
        candidate["longitude"],
        canonical_json(candidate["cell_geometry"]),
        generation["row"],
        generation["column"],
        generation["center_easting_m"],
        generation["center_northing_m"],
    )


def validate_catalog_geometry(
    source_manifest: dict[str, Any], canonical_manifest: dict[str, Any], *, spacing_m: int
) -> None:
    """Comprueba la geometría candidata contra la generación F1 actual exacta."""
    validate_document(source_manifest, "manifest")
    validate_document(canonical_manifest, "manifest")
    expected_id = f"madrid-pilot-grid-v1-s{spacing_m}-l{spacing_m}"
    if source_manifest["manifest_id"] != expected_id:
        raise MapAssetError(
            f"El manifest {source_manifest['manifest_id']!r} no corresponde a {expected_id!r}"
        )
    if source_manifest["generation"] != canonical_manifest["generation"]:
        raise MapAssetError("La identidad geométrica del manifest no coincide con F1 actual")
    actual = source_manifest["candidates"]
    expected = canonical_manifest["candidates"]
    if len(actual) != EXPECTED_CANDIDATE_COUNTS[spacing_m]:
        raise MapAssetError(
            f"Se esperaban {EXPECTED_CANDIDATE_COUNTS[spacing_m]} celdas de {spacing_m} m; "
            f"el manifest contiene {len(actual)}"
        )
    if len(actual) != len(expected):
        raise MapAssetError("El número de celdas difiere de la generación F1 canónica")
    if [_geometry_signature(row) for row in actual] != [
        _geometry_signature(row) for row in expected
    ]:
        raise MapAssetError("Una o más geometrías/IDs difieren de la generación F1 canónica")


def catalog_to_geojson(manifest: dict[str, Any], *, spacing_m: int) -> dict[str, Any]:
    """Convierte las celdas del manifest a GeoJSON EPSG:4326 sin aproximarlas."""
    gallery_id = GALLERIES[spacing_m]
    features = []
    for candidate in manifest["candidates"]:
        candidate_id = candidate["candidate_id"]
        candidate_key = f"{gallery_id}:{candidate_id}"
        geometry = candidate["cell_geometry"]
        ring = geometry["coordinates"][0]
        if len(ring) != 5 or ring[0] != ring[-1]:
            raise MapAssetError(f"Anillo GeoJSON inválido para {candidate_id}")
        if any(
            not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90)
            for point in ring
        ):
            raise MapAssetError(f"Coordenada fuera de EPSG:4326 para {candidate_id}")
        features.append({
            "type": "Feature",
            "id": candidate_key,
            "geometry": geometry,
            "properties": {
                "candidate_key": candidate_key,
                "candidate_id": candidate_id,
                "gallery_id": gallery_id,
                "cell_size_m": spacing_m,
                "center_latitude": candidate["latitude"],
                "center_longitude": candidate["longitude"],
                "row": candidate["generation"]["row"],
                "column": candidate["generation"]["column"],
            },
        })
    if len({feature["id"] for feature in features}) != len(features):
        raise MapAssetError(f"IDs de celda duplicados en {gallery_id}")
    bbox = manifest["generation"]["region_bbox_wgs84"]
    return {
        "type": "FeatureCollection",
        "name": f"{gallery_id}-canonical-cells",
        "bbox": [bbox["west"], bbox["south"], bbox["east"], bbox["north"]],
        "features": features,
    }
