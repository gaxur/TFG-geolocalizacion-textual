"""Carga e invariantes cruzados de los contratos visuales F4."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Mapping
import zlib

from .f3_inputs import CatalogInput, F3InputError, load_verified_catalog
from .f4_contracts import (
    F4_EMBEDDING_DIMENSION,
    F4_SELECTED_CANDIDATES,
    F4_SELECTION_SHA256,
    F4_SELECTION_VERSION,
    F4_VISUAL_CONTRACT_VERSION,
)
from .f4_geometry import BBox3857, bbox_contains, bbox_wgs84_to_epsg3857, candidate_raster_geometry
from .osm_snapshot import SnapshotValidationError, validate_osm_xml
from .validation import SchemaValidationError, validate_document


VISUAL_DATASET_ID_PREFIX = "f4-madrid-visual-sha256-"
EMBEDDING_DATASET_ID_PREFIX = "f4-madrid-embeddings-sha256-"
GEOMETRY_ABS_TOLERANCE = 1e-7


class F4ValidationError(ValueError):
    """Un input o artefacto F4 incumple su contrato o sus referencias."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (KeyError, TypeError, ValueError) as error:
        raise F4ValidationError("identidad F4 no serializable") from error


def visual_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": document["contract_version"],
        "generator_version": document["generator_version"],
        "catalog": dict(document["catalog"]),
        "selection": dict(document["selection"]),
        "profile": dict(document["profile"]),
        "source": dict(document["source"]),
        "renderer": dict(document["renderer"]),
        "style": dict(document["style"]),
        "images": [dict(image) for image in document["images"]],
    }


def visual_dataset_id(document: Mapping[str, Any]) -> str:
    return VISUAL_DATASET_ID_PREFIX + sha256_bytes(_identity_bytes(visual_identity(document)))


def embedding_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": document["contract_version"],
        "visual_dataset": dict(document["visual_dataset"]),
        "model": dict(document["model"]),
        "checkpoint": dict(document["checkpoint"]),
        "preprocessing": dict(document["preprocessing"]),
        "embedding": dict(document["embedding"]),
    }


def embedding_dataset_id(document: Mapping[str, Any]) -> str:
    return EMBEDDING_DATASET_ID_PREFIX + sha256_bytes(_identity_bytes(embedding_identity(document)))


def load_verified_f1_50m(manifest_path: str | Path, config: Mapping[str, Any]) -> CatalogInput:
    try:
        catalog = load_verified_catalog(manifest_path, config)
    except F3InputError as error:
        raise F4ValidationError("manifest F1 de F4 inválido") from error
    if catalog.spacing_m != 50 or catalog.cell_size_m != 50:
        raise F4ValidationError("F4 requiere spacing_m=50 y cell_size_m=50 para este piloto")
    return catalog


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=GEOMETRY_ABS_TOLERANCE)


def _bbox_from_document(value: Mapping[str, Any]) -> BBox3857:
    return BBox3857(float(value["min_x"]), float(value["min_y"]), float(value["max_x"]), float(value["max_y"]))


def geometry_document(latitude: float, longitude: float) -> dict[str, Any]:
    geometry = candidate_raster_geometry(latitude, longitude)
    return {
        "center_x": geometry.center_x, "center_y": geometry.center_y,
        "global_pixel_x": geometry.global_pixel_x, "global_pixel_y": geometry.global_pixel_y,
        "request_bbox": geometry.request_bbox.as_document(),
        "source_mosaic_bbox": geometry.source_mosaic_bbox.as_document(),
        "output_bbox": geometry.output_bbox.as_document(),
        "tile_min_x": geometry.tile_min_x, "tile_min_y": geometry.tile_min_y,
        "tile_max_x": geometry.tile_max_x, "tile_max_y": geometry.tile_max_y,
        "mosaic_width_px": geometry.mosaic_width_px, "mosaic_height_px": geometry.mosaic_height_px,
        "candidate_pixel_x": geometry.candidate_pixel_x, "candidate_pixel_y": geometry.candidate_pixel_y,
        "crop_left_px": geometry.crop_left_px, "crop_top_px": geometry.crop_top_px,
        "native_meters_per_pixel": geometry.native_meters_per_pixel,
        "output_meters_per_pixel": geometry.native_meters_per_pixel / 2,
    }


def _validate_geometry(actual: Mapping[str, Any], latitude: float, longitude: float) -> None:
    expected = geometry_document(latitude, longitude)
    for field, expected_value in expected.items():
        actual_value = actual[field]
        if isinstance(expected_value, dict):
            if actual_value.get("crs") != "EPSG:3857" or any(
                not _close(actual_value[key], expected_value[key]) for key in ("min_x", "min_y", "max_x", "max_y")
            ):
                raise F4ValidationError(f"geometry.{field} no corresponde al perfil y centro F1")
        elif isinstance(expected_value, float):
            if not _close(actual_value, expected_value):
                raise F4ValidationError(f"geometry.{field} no corresponde al perfil y centro F1")
        elif actual_value != expected_value:
            raise F4ValidationError(f"geometry.{field} no corresponde al perfil y centro F1")


def validate_visual_manifest(
    document: Mapping[str, Any],
    catalog: CatalogInput,
    *,
    selection: Mapping[str, Any],
    selection_sha256: str,
) -> None:
    try:
        validate_document(document, "f4_visual_manifest")
    except SchemaValidationError as error:
        raise F4ValidationError("manifest visual F4 inválido") from error
    if document["contract_version"] != F4_VISUAL_CONTRACT_VERSION:
        raise F4ValidationError("versión de contrato visual no soportada")
    expected_catalog = {
        "manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256,
        "region_id": catalog.region_id, "catalog_version": catalog.catalog_version,
        "spacing_m": catalog.spacing_m, "cell_size_m": catalog.cell_size_m, "grid_hash": catalog.grid_hash,
    }
    if dict(document["catalog"]) != expected_catalog:
        raise F4ValidationError("referencia al manifest F1 inconsistente")
    try:
        validate_document(selection, "f4_visual_selection")
    except SchemaValidationError as error:
        raise F4ValidationError("selección F4 inválida") from error
    actual_selection = tuple((item["candidate_id"], item["role"]) for item in selection["candidates"])
    if actual_selection != F4_SELECTED_CANDIDATES or selection_sha256 != F4_SELECTION_SHA256:
        raise F4ValidationError("selección F4 no corresponde a la fixture fija versionada")
    if (
        selection["source_manifest_id"] != catalog.manifest_id
        or selection["source_manifest_sha256"] != catalog.sha256
        or selection["selection_id"] != F4_SELECTION_VERSION
        or document["selection"]["selection_id"] != F4_SELECTION_VERSION
        or document["selection"]["sha256"] != selection_sha256
    ):
        raise F4ValidationError("referencia a la selección F4 inconsistente")
    expected_ids = [item["candidate_id"] for item in selection["candidates"]]
    actual_ids = [item["candidate_id"] for item in document["images"]]
    if actual_ids != expected_ids:
        raise F4ValidationError("el manifest debe incluir exactamente los nueve candidatos seleccionados")

    candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    source_bbox = _bbox_from_document(document["source"]["coverage_bbox_epsg3857"])
    expected_source_bbox = bbox_wgs84_to_epsg3857(document["source"]["coverage_bbox_wgs84"])
    if any(
        not _close(getattr(source_bbox, field), getattr(expected_source_bbox, field))
        for field in ("min_x", "min_y", "max_x", "max_y")
    ):
        raise F4ValidationError("bbox EPSG:3857 de la fuente no corresponde a su bbox WGS84")
    if document["source"]["source_type"] == "osm_snapshot":
        expected_source_id = f"osm-madrid-pilot-osmxml-sha256-{document['source']['data_sha256']}"
        if document["source"]["source_id"] != expected_source_id:
            raise F4ValidationError("source_id OSM no corresponde a data_sha256")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for image in document["images"]:
        candidate_id = image["candidate_id"]
        if candidate_id in seen_ids:
            raise F4ValidationError(f"candidate_id duplicado: {candidate_id}")
        seen_ids.add(candidate_id)
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise F4ValidationError(f"candidate_id ajeno al manifest F1: {candidate_id}")
        if not _close(image["latitude"], candidate.latitude) or not _close(image["longitude"], candidate.longitude):
            raise F4ValidationError(f"coordenadas inconsistentes para {candidate_id}")
        _validate_geometry(image["geometry"], candidate.latitude, candidate.longitude)
        covered = bbox_contains(source_bbox, _bbox_from_document(image["geometry"]["output_bbox"]))
        if covered and image["generation_status"] == "insufficient_source":
            raise F4ValidationError(f"imagen marcada sin cobertura aunque la fuente la cubre: {candidate_id}")
        if image["generation_status"] == "generated" and not covered:
            raise F4ValidationError(f"imagen generada sin cobertura completa: {candidate_id}")
        if not covered and not (
            image["generation_status"] == "insufficient_source"
            and image["error_code"] == "source_does_not_cover_output_bbox"
        ):
            raise F4ValidationError(f"cobertura insuficiente no declarada: {candidate_id}")
        path = image["image_path"]
        if path is not None:
            if path in seen_paths:
                raise F4ValidationError(f"image_path duplicado: {path}")
            seen_paths.add(path)
            if path != f"images/{candidate_id}.png":
                raise F4ValidationError("image_path debe derivar exactamente de candidate_id")
    if document["visual_dataset_id"] != visual_dataset_id(document):
        raise F4ValidationError("visual_dataset_id no corresponde a los inputs efectivos")


def validate_embedding_manifest(document: Mapping[str, Any], visual_manifest: Mapping[str, Any] | None = None) -> None:
    try:
        validate_document(document, "f4_embedding_manifest")
    except SchemaValidationError as error:
        raise F4ValidationError("manifest de embeddings F4 inválido") from error
    if document["embedding"]["dimension"] != F4_EMBEDDING_DIMENSION:
        raise F4ValidationError("la dimensión CrossText2Loc debe ser 768")
    if document["embedding_dataset_id"] != embedding_dataset_id(document):
        raise F4ValidationError("embedding_dataset_id no corresponde a los inputs efectivos")
    if visual_manifest is not None:
        if document["visual_dataset"]["visual_dataset_id"] != visual_manifest["visual_dataset_id"]:
            raise F4ValidationError("referencia al dataset visual inconsistente")
        generated = sum(image["generation_status"] == "generated" for image in visual_manifest["images"])
        if document["embedding"]["count"] != generated:
            raise F4ValidationError("el número de embeddings no coincide con las imágenes generadas")


def validate_retrieval_result(document: Mapping[str, Any], catalog: CatalogInput | None = None) -> None:
    try:
        validate_document(document, "f4_retrieval_result")
    except SchemaValidationError as error:
        raise F4ValidationError("resultado Top-K F4 inválido") from error
    if catalog is not None:
        candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
        for result in document["results"]:
            candidate = candidates.get(result["candidate_id"])
            if candidate is None or not _close(result["latitude"], candidate.latitude) or not _close(result["longitude"], candidate.longitude):
                raise F4ValidationError("resultado Top-K inconsistente con F1")


def load_visual_manifest(
    path: str | Path,
    catalog: CatalogInput,
    *,
    selection: Mapping[str, Any],
    selection_sha256: str,
) -> Mapping[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise F4ValidationError("no se pudo cargar el manifest visual F4") from error
    validate_visual_manifest(
        document,
        catalog,
        selection=selection,
        selection_sha256=selection_sha256,
    )
    return document


def _validate_png(raw: bytes, expected_width: int, expected_height: int) -> None:
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise F4ValidationError("firma PNG inválida")
    offset = 8
    idat = bytearray()
    seen_ihdr = False
    seen_iend = False
    seen_idat = False
    idat_closed = False
    width = height = None
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise F4ValidationError("chunk PNG truncado")
        length = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(raw):
            raise F4ValidationError("payload PNG truncado")
        payload = raw[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", raw[offset + 8 + length:end])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise F4ValidationError("CRC PNG inválido")
        if kind == b"IHDR":
            if seen_ihdr or offset != 8 or length != 13:
                raise F4ValidationError("IHDR PNG inválido")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if (width, height) != (expected_width, expected_height) or (bit_depth, color_type, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise F4ValidationError("PNG no es RGB 8-bit no entrelazado 512 x 512")
            seen_ihdr = True
        elif kind == b"IDAT":
            if not seen_ihdr or seen_iend or idat_closed:
                raise F4ValidationError("orden de chunks PNG inválido")
            seen_idat = True
            idat.extend(payload)
        elif kind == b"IEND":
            if length != 0 or not seen_ihdr or not idat:
                raise F4ValidationError("IEND PNG inválido")
            seen_iend = True
            offset = end
            break
        elif kind[0] & 0x20 == 0:
            raise F4ValidationError("chunk crítico PNG desconocido")
        elif seen_idat:
            idat_closed = True
        offset = end
    if not seen_iend or offset != len(raw):
        raise F4ValidationError("PNG sin IEND final o con bytes sobrantes")
    try:
        decompressor = zlib.decompressobj()
        pixels = decompressor.decompress(bytes(idat)) + decompressor.flush()
    except zlib.error as error:
        raise F4ValidationError("IDAT PNG no se puede descomprimir") from error
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise F4ValidationError("stream IDAT PNG no termina limpiamente")
    row_size = 1 + expected_width * 3
    if len(pixels) != expected_height * row_size:
        raise F4ValidationError("datos de píxeles PNG incompletos")
    if any(pixels[row * row_size] > 4 for row in range(expected_height)):
        raise F4ValidationError("filtro PNG no válido")
    previous = bytearray(expected_width * 3)
    first_pixel = None
    varied = False
    for row_index in range(expected_height):
        offset = row_index * row_size
        filter_type = pixels[offset]
        encoded = pixels[offset + 1:offset + row_size]
        decoded = bytearray(len(encoded))
        for index, value in enumerate(encoded):
            left = decoded[index - 3] if index >= 3 else 0
            up = previous[index]
            upper_left = previous[index - 3] if index >= 3 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            else:
                estimate = left + up - upper_left
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
            decoded[index] = (value + predictor) & 0xFF
        for index in range(0, len(decoded), 3):
            pixel = bytes(decoded[index:index + 3])
            if first_pixel is None:
                first_pixel = pixel
            elif pixel != first_pixel:
                varied = True
                break
        previous = decoded
        if varied:
            break
    if not varied:
        raise F4ValidationError("PNG uniforme sin contenido cartográfico")


def verify_visual_image_files(document: Mapping[str, Any], dataset_root: str | Path) -> None:
    root = Path(dataset_root).resolve()
    for image in document["images"]:
        if image["generation_status"] != "generated":
            continue
        path = root / image["image_path"]
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as error:
            raise F4ValidationError(f"imagen fuera del dataset o inexistente: {path}") from error
        if not resolved.is_file() or path.is_symlink():
            raise F4ValidationError(f"imagen no es un fichero regular: {path}")
        raw = resolved.read_bytes()
        if sha256_bytes(raw) != image["image_sha256"]:
            raise F4ValidationError(f"SHA-256 de imagen no coincide: {image['candidate_id']}")
        try:
            _validate_png(raw, image["width_px"], image["height_px"])
        except F4ValidationError as error:
            raise F4ValidationError(f"PNG inválido para {image['candidate_id']}: {error}") from error


def validate_render_extract_provenance(
    provenance: Mapping[str, Any], source_raw: bytes, source: Mapping[str, Any]
) -> None:
    required = {
        "acquired_at_utc", "attribution", "bbox", "closure", "data_timestamp_utc",
        "http", "license", "raw_format", "raw_sha256", "raw_size_bytes",
        "resolved_filename", "selection", "source_id", "source_url",
    }
    if not isinstance(provenance, Mapping) or set(provenance) != required:
        raise F4ValidationError("provenance del extracto de render no cumple su contrato")
    if (
        provenance["source_id"] != source["source_id"]
        or provenance["raw_sha256"] != source["data_sha256"]
        or provenance["raw_size_bytes"] != len(source_raw)
        or provenance["bbox"] != source["coverage_bbox_wgs84"]
        or provenance["selection"] != source["selection"]
        or provenance["closure"] != source["closure"]
        or provenance["license"] != source["license"]
        or provenance["attribution"] != source["attribution"]
        or provenance["raw_format"] != "osmpbf"
    ):
        raise F4ValidationError("provenance del extracto de render no corresponde al manifest")


def validate_visual_bundle(
    document: Mapping[str, Any],
    catalog: CatalogInput,
    *,
    selection: Mapping[str, Any],
    selection_sha256: str,
    dataset_root: str | Path,
    project_root: str | Path,
) -> None:
    validate_visual_manifest(document, catalog, selection=selection, selection_sha256=selection_sha256)
    root = Path(project_root).resolve()

    def verified_file(logical_path: str, expected_hash: str, label: str) -> bytes:
        path = (root / logical_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise F4ValidationError(f"{label} fuera del proyecto") from error
        if not path.is_file() or path.is_symlink():
            raise F4ValidationError(f"{label} inexistente o no regular")
        raw = path.read_bytes()
        if sha256_bytes(raw) != expected_hash:
            raise F4ValidationError(f"hash de {label} no coincide")
        return raw

    selection_raw = verified_file(document["selection"]["logical_path"], document["selection"]["sha256"], "selección visual")
    try:
        stored_selection = json.loads(selection_raw.decode("utf-8"))
        validate_document(stored_selection, "f4_visual_selection")
    except (UnicodeDecodeError, json.JSONDecodeError, SchemaValidationError) as error:
        raise F4ValidationError("selección visual almacenada inválida") from error
    if stored_selection != selection:
        raise F4ValidationError("selección suministrada no coincide con el fichero verificado")
    source_raw = verified_file(document["source"]["data_path"], document["source"]["data_sha256"], "datos de fuente")
    provenance_raw = verified_file(document["source"]["provenance_path"], document["source"]["provenance_sha256"], "provenance de fuente")
    try:
        provenance = json.loads(provenance_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise F4ValidationError("provenance de fuente no es JSON UTF-8") from error
    renderer_config_raw = verified_file(document["renderer"]["configuration_path"], document["renderer"]["configuration_sha256"], "configuración del renderer")
    try:
        renderer_config = json.loads(renderer_config_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise F4ValidationError("configuración del renderer no es JSON UTF-8") from error
    if (
        not isinstance(renderer_config, Mapping)
        or set(renderer_config) != {"schema_version", "container_image_digest", "files"}
        or renderer_config["schema_version"] != "1.0"
        or renderer_config["container_image_digest"] != document["renderer"]["container_image_digest"]
        or not isinstance(renderer_config["files"], list)
        or not renderer_config["files"]
    ):
        raise F4ValidationError("configuración efectiva del renderer inválida")
    seen_renderer_paths = set()
    for entry in renderer_config["files"]:
        if not isinstance(entry, Mapping) or set(entry) != {"logical_path", "sha256", "size_bytes", "source", "license"}:
            raise F4ValidationError("entrada de configuración efectiva inválida")
        if entry["logical_path"] in seen_renderer_paths:
            raise F4ValidationError("path duplicado en configuración efectiva")
        seen_renderer_paths.add(entry["logical_path"])
        effective_raw = verified_file(entry["logical_path"], entry["sha256"], f"input efectivo {entry['logical_path']}")
        if len(effective_raw) != entry["size_bytes"]:
            raise F4ValidationError(f"tamaño de input efectivo no coincide: {entry['logical_path']}")
    verified_file(document["style"]["compiled_style_path"], document["style"]["compiled_style_sha256"], "estilo compilado")
    for kind in ("assets", "fonts"):
        raw = verified_file(document["style"][f"{kind}_manifest_path"], document["style"][f"{kind}_manifest_sha256"], f"manifest de {kind}")
        try:
            asset_document = json.loads(raw.decode("utf-8"))
            validate_document(asset_document, "f4_assets_manifest")
        except (UnicodeDecodeError, json.JSONDecodeError, SchemaValidationError) as error:
            raise F4ValidationError(f"manifest de {kind} inválido") from error
        expected_kind = "renderer_assets" if kind == "assets" else "fonts"
        if asset_document["kind"] != expected_kind:
            raise F4ValidationError(f"manifest de {kind} declara el tipo incorrecto")
        for asset in asset_document["files"]:
            verified_raw = verified_file(asset["logical_path"], asset["sha256"], f"asset {asset['logical_path']}")
            if len(verified_raw) != asset["size_bytes"]:
                raise F4ValidationError(f"tamaño de asset no coincide: {asset['logical_path']}")

    if document["source"]["source_type"] == "osm_snapshot":
        try:
            validate_document(provenance, "osm_snapshot")
        except SchemaValidationError as error:
            raise F4ValidationError("provenance OSM no cumple su contrato") from error
        if (
            provenance.get("osm_snapshot_id") != document["source"]["source_id"]
            or provenance.get("raw_sha256") != document["source"]["data_sha256"]
            or provenance.get("bbox") != document["source"]["coverage_bbox_wgs84"]
            or provenance.get("selection") != document["source"]["selection"]
            or provenance.get("closure") != document["source"]["closure"]
        ):
            raise F4ValidationError("provenance OSM no corresponde al manifest visual")
        if provenance["raw_size_bytes"] != len(source_raw):
            raise F4ValidationError("tamaño raw OSM no corresponde a provenance")
        if sha256_bytes(provenance["query"].encode("utf-8")) != provenance["query_sha256"]:
            raise F4ValidationError("hash de consulta OSM no corresponde a provenance")
        try:
            counts = validate_osm_xml(source_raw, len(source_raw), provenance["bbox"])
        except SnapshotValidationError as error:
            raise F4ValidationError("fuente OSM estructuralmente inválida") from error
        if counts != provenance["counts"]:
            raise F4ValidationError("conteos de fuente OSM no corresponden a provenance")
    elif document["source"]["source_type"] == "osm_render_extract":
        validate_render_extract_provenance(provenance, source_raw, document["source"])
    verify_visual_image_files(document, dataset_root)
