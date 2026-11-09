#!/usr/bin/env python3
"""Exporta las celdas métricas F1 a GeoJSON estático para el frontend.

La salida no incorpora OSM, alturas de edificios, rankings ni ground truth. Si
se proporciona un manifest F4, se valida contra la selección congelada y contra
la geometría que vuelve a producir el generador F1 actual. Si no está disponible
el manifest F4, `--regenerate-grid` permite exportar únicamente la cuadrícula
canónica derivada de `config/madrid.yaml`, dejando clara esa procedencia.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.catalog import build_catalog
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.madrid_map_assets import (
    GALLERIES,
    EXPECTED_CANDIDATE_COUNTS,
    MAP_ASSETS_CONTRACT,
    MapAssetError,
    _file_sha256,
    _manifest_sha256,
    catalog_to_geojson,
    validate_catalog_geometry,
)
from src.tfg_phase0.provenance import canonical_json
from src.tfg_phase0.validation import validate_document


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MapAssetError(f"No se pudo leer JSON válido en {path}: {error}") from error
    if not isinstance(value, dict):
        raise MapAssetError(f"Se esperaba un objeto JSON en {path}")
    return value


def _load_gallery_manifest(
    *, spacing_m: int,
    config: dict[str, Any],
    manifest_path: Path | None,
    selection_path: Path,
    regenerate_grid: bool,
) -> tuple[dict[str, Any], str, str, str | None]:
    canonical = build_catalog(config, spacing_m=spacing_m, cell_size_m=spacing_m)
    selection = _read_json(selection_path)
    expected_gallery = GALLERIES[spacing_m]
    expected_count = EXPECTED_CANDIDATE_COUNTS[spacing_m]
    if selection.get("candidate_count") != expected_count:
        raise MapAssetError(f"candidate_count inesperado en {selection_path}")
    if selection.get("source_manifest_id") != canonical["manifest_id"]:
        raise MapAssetError(f"source_manifest_id inesperado en {selection_path}")

    if regenerate_grid:
        manifest = canonical
        source_mode = "canonical_f1_grid_regeneration"
        source_sha = _manifest_sha256(canonical)
        if source_sha != selection.get("source_manifest_sha256"):
            raise MapAssetError(
                f"La regeneración F1 de {expected_gallery} no reproduce el hash "
                "del manifest F4 seleccionado; no se publican celdas incompatibles."
            )
        osm_snapshot_id = None
    else:
        if manifest_path is None or not manifest_path.is_file():
            raise FileNotFoundError(
                f"Falta el manifest F4 {expected_gallery}: {manifest_path}. "
                "Recupéralo de los artefactos F4 validados o usa explícitamente "
                "--regenerate-grid para generar solo la geometría F1."
            )
        manifest = _read_json(manifest_path)
        validate_document(manifest, "manifest")
        actual_sha = _file_sha256(manifest_path)
        if actual_sha != selection.get("source_manifest_sha256"):
            raise MapAssetError(
                f"El SHA-256 de {manifest_path} no coincide con "
                f"{selection_path}: {actual_sha} != {selection.get('source_manifest_sha256')}"
            )
        validate_catalog_geometry(manifest, canonical, spacing_m=spacing_m)
        source_mode = "validated_selection_manifest"
        source_sha = actual_sha
        osm_snapshot_id = manifest["osm_snapshot_id"]

    validate_catalog_geometry(manifest, canonical, spacing_m=spacing_m)
    return manifest, source_mode, source_sha, osm_snapshot_id


def build_map_assets(
    *,
    config_path: Path,
    output_dir: Path,
    manifest_25m: Path | None = None,
    manifest_50m: Path | None = None,
    regenerate_grid: bool = False,
    replace: bool = False,
) -> dict[str, Any]:
    manifests_supplied = manifest_25m is not None or manifest_50m is not None
    if regenerate_grid and manifests_supplied:
        raise ValueError(
            "Selecciona exactamente una vía: --regenerate-grid o ambos manifests F4"
        )
    if not regenerate_grid and ((manifest_25m is None) != (manifest_50m is None)):
        raise ValueError("Para validar F4 hay que aportar ambos manifests de 25 m y 50 m")

    config_path = config_path.resolve()
    config = load_region_config(config_path)
    config_relative = config_path.name
    try:
        config_relative = config_path.relative_to(ROOT).as_posix()
    except ValueError:
        pass
    selectors = {
        25: ROOT / "config/madrid_f4_visual_gallery_25m.json",
        50: ROOT / "config/madrid_f4_visual_gallery_50m.json",
    }
    manifest_paths = {25: manifest_25m, 50: manifest_50m}

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pending: dict[str, bytes] = {}
    galleries: dict[str, Any] = {}
    source_modes: set[str] = set()
    snapshot_ids: set[str | None] = set()

    for spacing_m, gallery_id in GALLERIES.items():
        selection = _read_json(selectors[spacing_m])
        source_manifest, source_mode, source_sha, osm_snapshot_id = _load_gallery_manifest(
            spacing_m=spacing_m,
            config=config,
            manifest_path=manifest_paths[spacing_m],
            selection_path=selectors[spacing_m],
            regenerate_grid=regenerate_grid,
        )
        geojson = catalog_to_geojson(source_manifest, spacing_m=spacing_m)
        geojson_bytes = (canonical_json(geojson) + "\n").encode("utf-8")
        geojson_file = f"cells-{spacing_m}m.geojson"
        pending[geojson_file] = geojson_bytes
        galleries[gallery_id] = {
            "candidate_count": len(source_manifest["candidates"]),
            "cell_size_m": spacing_m,
            "grid_hash": source_manifest["generation"]["grid_hash"],
            "manifest_id": source_manifest["manifest_id"],
            "manifest_sha256": source_sha,
            "expected_f4_manifest_sha256": selection["source_manifest_sha256"],
            "f4_manifest_sha256": source_sha if source_mode == "validated_selection_manifest" else None,
            "source_mode": source_mode,
            "osm_snapshot_id": osm_snapshot_id,
            "geojson_file": geojson_file,
            "geojson_sha256": hashlib.sha256(geojson_bytes).hexdigest(),
            "geometry_crs": "EPSG:4326",
            "construction_crs": "EPSG:25830",
            "canonical_f1_geometry_match": True,
        }
        source_modes.add(source_mode)
        snapshot_ids.add(osm_snapshot_id)

    bbox = config["region"]["bbox"]
    asset_manifest = {
        "schema_version": "1.0",
        "contract_version": MAP_ASSETS_CONTRACT,
        "region_id": config["region"]["name"],
        "region_bbox_wgs84": bbox,
        "catalog_version": config["catalog"]["catalog_version"],
        "catalog_config_file": config_relative,
        "catalog_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "osm_snapshot_id": next(iter(snapshot_ids)) if len(snapshot_ids) == 1 else None,
        "source_mode": next(iter(source_modes)) if len(source_modes) == 1 else "mixed",
        "geometry_attribution": "Geometrías de la cuadrícula F1 del catálogo del TFG.",
        "basemap_attribution_required": "© OpenStreetMap contributors · Open Database License 1.0",
        "galleries": galleries,
        "basemap": {
            "file": "madrid.pmtiles",
            "expected_tile_schema": "madrid-osm-explicit-height-v1",
            "expected_source_layers": ["building", "transportation", "landuse", "water"],
            "offline_only": True,
        },
    }
    pending["map-assets.json"] = (
        json.dumps(asset_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")

    conflicts = [
        name for name, content in pending.items()
        if (output_dir / name).exists() and (output_dir / name).read_bytes() != content
    ]
    if conflicts and not replace:
        raise FileExistsError(
            "No se sobrescriben recursos locales distintos: " + ", ".join(conflicts)
            + ". Revisa procedencia/hashes; usa --replace solo con autorización explícita."
        )
    for name, content in pending.items():
        target = output_dir / name
        if target.exists() and target.read_bytes() == content:
            continue
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
    return asset_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/map-assets")
    parser.add_argument("--manifest-25m", type=Path)
    parser.add_argument("--manifest-50m", type=Path)
    parser.add_argument(
        "--regenerate-grid", action="store_true",
        help="Regenera solo la geometría F1 desde config/madrid.yaml; no afirma lineage F4/OSM.",
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    result = build_map_assets(
        config_path=args.config,
        output_dir=args.output_dir,
        manifest_25m=args.manifest_25m,
        manifest_50m=args.manifest_50m,
        regenerate_grid=args.regenerate_grid,
        replace=args.replace,
    )
    print(f"Recursos GeoJSON: {args.output_dir}")
    for gallery_id, gallery in result["galleries"].items():
        print(
            f"{gallery_id}: {gallery['candidate_count']} celdas; "
            f"{gallery['geojson_file']} SHA-256={gallery['geojson_sha256']}"
        )
    print(f"Modo de procedencia: {result['source_mode']}")
    print("PMTiles: no generado; requiere el PBF local/provenance indicado en la documentación.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
