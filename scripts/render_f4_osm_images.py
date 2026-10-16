#!/usr/bin/env python3
"""Renderiza y publica galerías visuales F4 con Mapnik y OSM Carto."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import mapnik
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_contracts import experimental_visual_profile
from src.tfg_phase0.f4_geometry import bbox_wgs84_to_epsg3857
from src.tfg_phase0.f4_preflight import load_verified_selection
from src.tfg_phase0.f4_validation import (
    geometry_document,
    load_verified_f1_catalog,
    sha256_bytes,
    validate_visual_bundle,
    visual_dataset_id,
)


OSM_CARTO_COMMIT = "491bd4a4675a94f3950ff45843d0c4696d8ae420"
EFFECTIVE_PROJECT_FILES = (
    "compose.f4-osm-render.yaml",
    "docker/f4-osm-carto-arm64/Dockerfile",
    "docker/f4-osm-carto-arm64/external-data.local.yml",
    "docker/f4-osm-carto-arm64/osm-carto-v5.9.0-emoji-fallback.patch",
    "scripts/render_f4_osm_images.py",
    "scripts/run_f4_osm_carto.sh",
    "scripts/run_f4_osm_render.sh",
    "scripts/verify_f4_osm_pbf.py",
    "src/tfg_phase0/f4_contracts.py",
    "src/tfg_phase0/f4_geometry.py",
    "src/tfg_phase0/f4_validation.py",
)
EFFECTIVE_CARTO_FILES = (
    "external/openstreetmap-carto-v5.9.0/openstreetmap-carto.lua",
    "external/openstreetmap-carto-v5.9.0/openstreetmap-carto.style",
    "external/openstreetmap-carto-v5.9.0/functions.sql",
    "external/openstreetmap-carto-v5.9.0/indexes.sql",
    "external/openstreetmap-carto-v5.9.0/scripts/get-external-data.py",
)


def file_entry(path: Path, *, source: str, license_name: str) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "logical_path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
        "source": source,
        "license": license_name,
    }


def render_mosaic(style_path: Path, geometry: dict[str, object], output: Path) -> None:
    width = geometry["mosaic_width_px"]
    height = geometry["mosaic_height_px"]
    bbox = geometry["source_mosaic_bbox"]
    map_object = mapnik.Map(width, height)
    mapnik.load_map(map_object, str(style_path), True)
    map_object.zoom_to_box(mapnik.Box2d(bbox["min_x"], bbox["min_y"], bbox["max_x"], bbox["max_y"]))
    mapnik.render_to_file(map_object, str(output), "png")


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256_bytes(raw)


def valid_cached_row(row_path: Path, image_path: Path, expected: dict[str, object]) -> dict[str, object] | None:
    try:
        row = json.loads(row_path.read_text(encoding="utf-8"))
        if row.get("cache_identity") != expected or row.get("generation_status") != "generated":
            return None
        raw = image_path.read_bytes()
        if sha256_bytes(raw) != row["image_sha256"]:
            return None
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            if image.size != (512, 512) or image.mode != "RGB" or image.format != "PNG" or not any(low != high for low, high in image.getextrema()):
                return None
        return {key: value for key, value in row.items() if key != "cache_identity"}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def publish_cached_row(row_path: Path, image_path: Path, row: dict[str, object], identity: dict[str, object]) -> None:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    row_path.parent.mkdir(parents=True, exist_ok=True)
    document = dict(row)
    rendered_path = Path(document.pop("rendered_path"))
    document["cache_identity"] = identity
    raw = (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=image_path.parent, prefix=f".{image_path.name}.", delete=False) as stream:
        temporary_image = Path(stream.name)
    with tempfile.NamedTemporaryFile(dir=row_path.parent, prefix=f".{row_path.name}.", delete=False) as stream:
        stream.write(raw)
        temporary_row = Path(stream.name)
    try:
        shutil.copyfile(rendered_path, temporary_image)
        os.replace(temporary_image, image_path)
        os.replace(temporary_row, row_path)
    finally:
        temporary_image.unlink(missing_ok=True)
        temporary_row.unlink(missing_ok=True)


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def make_readable(root: Path) -> None:
    for path in root.rglob("*"):
        os.chmod(path, 0o755 if path.is_dir() else 0o644)
    os.chmod(root, 0o755)


def publish_content_file(directory: Path, stem: str, suffix: str, raw: bytes) -> Path:
    digest = sha256_bytes(raw)
    path = directory / f"{stem}-sha256-{digest}{suffix}"
    directory.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError(f"colisión de contenido en {path}")
    else:
        path.write_bytes(raw)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--carto-root", required=True, type=Path)
    parser.add_argument("--renderer-root", required=True, type=Path)
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--resume-root", type=Path)
    parser.add_argument("--reuse-bundle", type=Path)
    parser.add_argument("--only-candidate")
    args = parser.parse_args()

    config = load_region_config(ROOT / "config/madrid.yaml")
    catalog = load_verified_f1_catalog(ROOT / args.manifest, config)
    selection, selection_hash = load_verified_selection(ROOT / args.selection, catalog)
    candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    source_dir = ROOT / args.source_dir
    source_provenance_path = source_dir / "provenance.json"
    source_provenance = json.loads(source_provenance_path.read_text(encoding="utf-8"))
    source_bbox = bbox_wgs84_to_epsg3857(source_provenance["bbox"])
    carto_root = ROOT / args.carto_root
    renderer_root = ROOT / args.renderer_root
    style_path = carto_root / "project.xml"

    asset_paths = sorted(path for folder in ("symbols", "patterns") for path in (carto_root / folder).glob("**/*") if path.is_file())
    external_assets = sorted((renderer_root / "downloads").glob("*.zip"))
    font_paths = sorted((carto_root / "fonts").glob("*.ttf")) + sorted((carto_root / "fonts").glob("*.otf"))

    (ROOT / "data/processed/visual").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="f4-visual-", dir=ROOT / "data/processed/visual") as temp_name:
        temp = Path(temp_name)
        images_dir = temp / "images"
        images_dir.mkdir()
        assets_entries = [file_entry(path, source="openstreetmap-carto-v5.9.0", license_name="CC0-1.0") for path in asset_paths]
        for path in external_assets:
            license_name = "Public-Domain" if path.name.startswith("ne_") else "ODbL-1.0"
            assets_entries.append(file_entry(path, source="osm-carto-external-data-v5.9.0", license_name=license_name))
        assets = {"schema_version": "1.0", "manifest_id": "osm-carto-v5.9.0-assets", "kind": "renderer_assets", "files": assets_entries}
        fonts = {"schema_version": "1.0", "manifest_id": "ubuntu-font-packages-v1", "kind": "fonts", "files": [file_entry(path, source="ubuntu-24.04-package", license_name="package-specific-see-container") for path in font_paths]}
        manifests_dir = renderer_root / "manifests"
        assets_raw = (json.dumps(assets, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        fonts_raw = (json.dumps(fonts, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        assets_path = publish_content_file(manifests_dir, "assets", ".json", assets_raw)
        fonts_path = publish_content_file(manifests_dir, "fonts", ".json", fonts_raw)
        compiled_style_path = publish_content_file(renderer_root / "compiled", "project", ".xml", style_path.read_bytes())
        effective_entries = [file_entry(ROOT / path, source="tfg-project", license_name="project-original") for path in EFFECTIVE_PROJECT_FILES]
        effective_entries.extend(file_entry(ROOT / path, source="openstreetmap-carto-v5.9.0", license_name="CC0-1.0") for path in EFFECTIVE_CARTO_FILES)
        renderer_config = {
            "schema_version": "1.0",
            "container_image_digest": args.container_image_digest,
            "files": effective_entries,
        }
        renderer_config_raw = (json.dumps(renderer_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        renderer_config_path = publish_content_file(manifests_dir, "renderer-config", ".json", renderer_config_raw)

        cache_inputs = {
            "cache_version": "f4-render-cache-v1",
            "profile": experimental_visual_profile(),
            "catalog_manifest_id": catalog.manifest_id,
            "catalog_manifest_sha256": catalog.sha256,
            "source_sha256": source_provenance["raw_sha256"],
            "container_image_digest": args.container_image_digest,
            "renderer_configuration_sha256": sha256_bytes(renderer_config_raw),
            "compiled_style_sha256": sha256_bytes(style_path.read_bytes()),
            "assets_manifest_sha256": sha256_bytes(assets_path.read_bytes()),
            "fonts_manifest_sha256": sha256_bytes(fonts_path.read_bytes()),
        }
        resume_root = ROOT / (args.resume_root or Path("data/processed/visual-staging")) / canonical_hash(cache_inputs)
        cache_images = resume_root / "images"
        cache_rows = resume_root / "rows"
        cache_images.mkdir(parents=True, exist_ok=True)
        cache_rows.mkdir(parents=True, exist_ok=True)

        if args.reuse_bundle:
            reuse_root = ROOT / args.reuse_bundle
            reuse_manifest = json.loads((reuse_root / "manifest.json").read_text(encoding="utf-8"))
            compatible = (
                reuse_manifest.get("profile") == cache_inputs["profile"]
                and reuse_manifest.get("source", {}).get("data_sha256") == cache_inputs["source_sha256"]
                and reuse_manifest.get("renderer", {}).get("container_image_digest") == cache_inputs["container_image_digest"]
                and reuse_manifest.get("renderer", {}).get("configuration_sha256") == cache_inputs["renderer_configuration_sha256"]
                and reuse_manifest.get("style", {}).get("compiled_style_sha256") == cache_inputs["compiled_style_sha256"]
                and reuse_manifest.get("style", {}).get("assets_manifest_sha256") == cache_inputs["assets_manifest_sha256"]
                and reuse_manifest.get("style", {}).get("fonts_manifest_sha256") == cache_inputs["fonts_manifest_sha256"]
            )
            if not compatible:
                raise RuntimeError("bundle de reutilización incompatible con los inputs efectivos")
            for old_row in reuse_manifest["images"]:
                if old_row["generation_status"] != "generated" or old_row["candidate_id"] not in candidates:
                    continue
                candidate = candidates[old_row["candidate_id"]]
                identity = dict(cache_inputs, candidate_id=candidate.candidate_id, latitude=candidate.latitude, longitude=candidate.longitude, geometry=geometry_document(candidate.latitude, candidate.longitude))
                if (
                    old_row["latitude"] != candidate.latitude
                    or old_row["longitude"] != candidate.longitude
                    or old_row["geometry"] != identity["geometry"]
                ):
                    raise RuntimeError(f"fila a reutilizar incompatible: {candidate.candidate_id}")
                source_image = reuse_root / old_row["image_path"]
                if sha256_bytes(source_image.read_bytes()) != old_row["image_sha256"]:
                    raise RuntimeError(f"imagen a reutilizar corrupta: {candidate.candidate_id}")
                seeded = dict(old_row, rendered_path=str(source_image))
                publish_cached_row(cache_rows / f"{candidate.candidate_id}.json", cache_images / f"{candidate.candidate_id}.png", seeded, identity)

        rows = []
        cache_hits = 0
        rendered = 0
        for selected in selection["candidates"]:
            candidate = candidates[selected["candidate_id"]]
            geometry = geometry_document(candidate.latitude, candidate.longitude)
            covered = all((
                source_bbox.min_x <= geometry["output_bbox"]["min_x"],
                source_bbox.min_y <= geometry["output_bbox"]["min_y"],
                source_bbox.max_x >= geometry["output_bbox"]["max_x"],
                source_bbox.max_y >= geometry["output_bbox"]["max_y"],
            ))
            if not covered:
                rows.append({"candidate_id": candidate.candidate_id, "latitude": candidate.latitude, "longitude": candidate.longitude, "generation_status": "insufficient_source", "geometry": geometry, "image_path": None, "image_sha256": None, "width_px": None, "height_px": None, "color_mode": None, "format": None, "error_code": "source_does_not_cover_output_bbox"})
                continue
            if args.only_candidate and candidate.candidate_id != args.only_candidate:
                rows.append({"candidate_id": candidate.candidate_id, "latitude": candidate.latitude, "longitude": candidate.longitude, "generation_status": "failed", "geometry": geometry, "image_path": None, "image_sha256": None, "width_px": None, "height_px": None, "color_mode": None, "format": None, "error_code": "renderer_failed"})
                continue
            identity = dict(cache_inputs, candidate_id=candidate.candidate_id, latitude=candidate.latitude, longitude=candidate.longitude, geometry=geometry)
            cached_image = cache_images / f"{candidate.candidate_id}.png"
            cached_row_path = cache_rows / f"{candidate.candidate_id}.json"
            cached = valid_cached_row(cached_row_path, cached_image, identity)
            if cached is not None:
                shutil.copyfile(cached_image, images_dir / f"{candidate.candidate_id}.png")
                rows.append(cached)
                cache_hits += 1
                continue
            mosaic = temp / f"{candidate.candidate_id}.mosaic.png"
            render_mosaic(style_path, geometry, mosaic)
            with Image.open(mosaic) as source:
                crop = source.transform((256, 256), Image.Transform.EXTENT, (geometry["crop_left_px"], geometry["crop_top_px"], geometry["crop_left_px"] + 256, geometry["crop_top_px"] + 256), resample=Image.Resampling.BICUBIC)
                final = crop.resize((512, 512), Image.Resampling.BICUBIC).convert("RGB")
                final_path = images_dir / f"{candidate.candidate_id}.png"
                final.save(final_path, format="PNG", optimize=False, compress_level=9)
                extrema = final.getextrema()
                if all(low == high for low, high in extrema):
                    raise RuntimeError(f"render uniforme sin contenido cartográfico: {candidate.candidate_id}")
            mosaic.unlink()
            row = {"candidate_id": candidate.candidate_id, "latitude": candidate.latitude, "longitude": candidate.longitude, "generation_status": "generated", "geometry": geometry, "image_path": f"images/{candidate.candidate_id}.png", "image_sha256": sha256_bytes(final_path.read_bytes()), "width_px": 512, "height_px": 512, "color_mode": "RGB", "format": "PNG", "error_code": None}
            publish_cached_row(cached_row_path, cached_image, dict(row, rendered_path=str(final_path)), identity)
            rows.append(row)
            rendered += 1

        source_raw = (source_dir / "source.osm.pbf").read_bytes()
        manifest = {
            "schema_version": "2.0", "visual_dataset_id": "f4-madrid-visual-sha256-" + "0" * 64,
            "contract_version": "f4-visual-dataset-v2", "generator_version": "phase4-visual-dataset-v2",
            "catalog": {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "region_id": catalog.region_id, "catalog_version": catalog.catalog_version, "spacing_m": catalog.spacing_m, "cell_size_m": catalog.cell_size_m, "grid_hash": catalog.grid_hash},
            "selection": {"selection_id": selection["selection_id"], "logical_path": args.selection.as_posix(), "sha256": selection_hash},
            "profile": experimental_visual_profile(),
            "source": {"contract_version": "f4-osm-source-v1", "source_id": source_provenance["source_id"], "source_type": "osm_render_extract", "data_path": (args.source_dir / "source.osm.pbf").as_posix(), "data_sha256": sha256_bytes(source_raw), "provenance_path": (args.source_dir / "provenance.json").as_posix(), "provenance_sha256": sha256_bytes(source_provenance_path.read_bytes()), "coverage_bbox_wgs84": source_provenance["bbox"], "coverage_bbox_epsg3857": source_bbox.as_document(), "selection": source_provenance["selection"], "closure": source_provenance["closure"], "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors. Datos disponibles bajo la Open Database License (ODbL). https://www.openstreetmap.org/copyright"},
            "renderer": {"contract_version": "f4-renderer-provenance-v1", "renderer_id": "mapnik-3.1.0-ubuntu24.04-arm64", "name": "Mapnik", "version": "3.1.0", "configuration_path": renderer_config_path.relative_to(ROOT).as_posix(), "configuration_sha256": sha256_bytes(renderer_config_path.read_bytes()), "container_image_digest": args.container_image_digest, "license": "LGPL-2.1"},
            "style": {"style_id": "openstreetmap-carto", "version": "5.9.0", "repository_commit": OSM_CARTO_COMMIT, "compiled_style_path": compiled_style_path.relative_to(ROOT).as_posix(), "compiled_style_sha256": sha256_bytes(compiled_style_path.read_bytes()), "assets_manifest_path": assets_path.relative_to(ROOT).as_posix(), "assets_manifest_sha256": sha256_bytes(assets_path.read_bytes()), "fonts_manifest_path": fonts_path.relative_to(ROOT).as_posix(), "fonts_manifest_sha256": sha256_bytes(fonts_path.read_bytes()), "license": "CC0-1.0"},
            "images": rows,
        }
        manifest["visual_dataset_id"] = visual_dataset_id(manifest)
        final_dir = ROOT / args.output_root / manifest["visual_dataset_id"]
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        validate_visual_bundle(manifest, catalog, selection=selection, selection_sha256=selection_hash, dataset_root=temp, project_root=ROOT)
        make_readable(temp)
        if final_dir.exists():
            if tree_hashes(final_dir) != tree_hashes(temp):
                raise RuntimeError(f"dataset existente no es byte a byte reproducible: {final_dir}")
        else:
            temp.rename(final_dir)
        print(json.dumps({"bundle": final_dir.relative_to(ROOT).as_posix(), "cache_hits": cache_hits, "rendered": rendered}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
