#!/usr/bin/env python3
"""Genera un PMTiles MVT local desde el PBF F4 ya presente en el proyecto.

No descarga datos, no modifica el PBF original ni regenera las geometrías F1.
El archivo y su provenance se publican con nombres nuevos y sin reemplazo.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_madrid_map_assets import build_map_assets
from src.tfg_phase0.madrid_osm_cartography import (
    DEFAULT_MARGIN_METERS,
    DEFAULT_MAX_ZOOM,
    DEFAULT_MIN_ZOOM,
    audit_local_pbf,
    build_mvt_tiles,
    validate_pmtiles_archive,
    vector_layer_metadata,
    write_pmtiles,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _catalog_lineage(validation_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    asset_manifest = build_map_assets(
        config_path=ROOT / "config/madrid.yaml",
        output_dir=validation_dir,
        manifest_25m=ROOT / "data/processed/catalog/manifest-25m.json",
        manifest_50m=ROOT / "data/processed/catalog/manifest-50m.json",
    )
    manifest_hashes = {}
    for size in (25, 50):
        gallery_id = f"madrid-{size}m"
        manifest_hashes[gallery_id] = asset_manifest["galleries"][gallery_id]["manifest_sha256"]
    return asset_manifest, manifest_hashes


def build_archive(
    *,
    output_path: Path,
    margin_m: float = DEFAULT_MARGIN_METERS,
    min_zoom: int = DEFAULT_MIN_ZOOM,
    max_zoom: int = DEFAULT_MAX_ZOOM,
) -> dict[str, Any]:
    output_path = output_path.resolve()
    provenance_path = output_path.with_suffix(output_path.suffix + ".provenance.json")
    if output_path.exists() or provenance_path.exists():
        raise FileExistsError(
            f"No se sobrescriben artefactos existentes: {output_path} / {provenance_path}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_dir = ROOT / "data/raw/osm/f4_sources/madrid-geofabrik-20261014"
    features, audit = audit_local_pbf(
        source_dir,
        ROOT / "config/madrid.yaml",
        margin_m=margin_m,
    )
    audit["toolchain"].update({
        "mapbox_vector_tile": version("mapbox-vector-tile"),
        "pmtiles_writer": version("pmtiles"),
        "mercantile": version("mercantile"),
        "protobuf": version("protobuf"),
        "pyclipper": version("pyclipper"),
        "generator_script_sha256": _sha256(Path(__file__).resolve()),
        "cartography_module_sha256": _sha256(ROOT / "src/tfg_phase0/madrid_osm_cartography.py"),
        "requirements_sha256": _sha256(ROOT / "requirements-cartography.txt"),
    })
    layers = vector_layer_metadata(features, min_zoom=min_zoom, max_zoom=max_zoom)
    if not any(layer["id"] == "building" for layer in layers):
        raise ValueError("El área F4 no produce huellas de edificios en D004+buffer")
    if not any(layer["id"] == "transportation" for layer in layers):
        raise ValueError("El área F4 no produce calles en D004+buffer")

    encoded_tiles, tile_generation = build_mvt_tiles(
        features,
        {
            "map_bounds_wgs84": audit["interpretation"]["context_bbox_wgs84"],
        },
        min_zoom=min_zoom,
        max_zoom=max_zoom,
    )
    audit["feature_count_for_map"] = len(features)
    audit["tile_generation"] = tile_generation
    feature_stats = {
        "audit": audit,
        "vector_layers": layers,
        "toolchain": audit["toolchain"],
    }

    catalog_dir = ROOT / "data/processed/catalog"
    with TemporaryDirectory(prefix="madrid-pmtiles-validation-") as validation_temp:
        validation_assets, catalog_hashes = _catalog_lineage(Path(validation_temp) / "cells")
        f1_geojson_hashes = {
            gallery: validation_assets["galleries"][gallery]["geojson_sha256"]
            for gallery in ("madrid-25m", "madrid-50m")
        }
        with TemporaryDirectory(prefix=".madrid-pmtiles-stage-", dir=output_path.parent) as stage_temp:
            stage_dir = Path(stage_temp)
            stage_archive = stage_dir / output_path.name
            stage_provenance = stage_archive.with_suffix(stage_archive.suffix + ".provenance.json")
            write_pmtiles(
                stage_archive,
                encoded_tiles,
                {
                    "map_bounds_wgs84": audit["interpretation"]["context_bbox_wgs84"],
                    "d004_bbox_wgs84": validation_assets["region_bbox_wgs84"],
                    "margin_m": margin_m,
                },
                source_id=audit["source"]["source_id"],
                source_sha256=audit["source"]["sha256"],
                feature_stats=feature_stats,
            )
            pmtiles_check = validate_pmtiles_archive(
                stage_archive,
                audit["interpretation"]["context_bbox_wgs84"],
            )
            provenance = json.loads(stage_provenance.read_text(encoding="utf-8"))
            provenance["catalog_lineage"] = {
                "manifests_are_f1_geometry": True,
                "osm_snapshot_id": None,
                "manifest_sha256": catalog_hashes,
                "geojson_sha256_reproduced_in_validation_temp": f1_geojson_hashes,
                "selection_config_sha256": {
                    f"madrid-{size}m": _sha256(ROOT / f"config/madrid_f4_visual_gallery_{size}m.json")
                    for size in (25, 50)
                },
            }
            provenance["pmtiles"]["path"] = output_path.name
            provenance["pmtiles"]["validation"] = pmtiles_check
            stage_provenance.write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if output_path.exists() or provenance_path.exists():
                raise FileExistsError("Un artefacto destino apareció durante la preparación")
            os.rename(stage_archive, output_path)
            try:
                os.rename(stage_provenance, provenance_path)
            except Exception:
                # Keep the validated archive; never delete or replace a user file.
                raise RuntimeError(
                    f"PMTiles válido publicado en {output_path}, pero faltó publicar su provenance"
                )

    return {
        "pmtiles_path": output_path.as_posix(),
        "pmtiles_provenance_path": provenance_path.as_posix(),
        "pmtiles_sha256": _sha256(output_path),
        "pmtiles_size_bytes": output_path.stat().st_size,
        "validation": pmtiles_check,
        "catalog_manifest_sha256": catalog_hashes,
        "f1_geojson_hashes_reproduced_in_temp": f1_geojson_hashes,
        "audit": audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "data/processed/map-assets/madrid.pmtiles",
    )
    parser.add_argument("--margin-m", type=float, default=DEFAULT_MARGIN_METERS)
    parser.add_argument("--min-zoom", type=int, default=DEFAULT_MIN_ZOOM)
    parser.add_argument("--max-zoom", type=int, default=DEFAULT_MAX_ZOOM)
    args = parser.parse_args()
    result = build_archive(
        output_path=args.output,
        margin_m=args.margin_m,
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
