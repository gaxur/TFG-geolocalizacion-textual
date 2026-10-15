"""Carga e invariantes cruzados de los contratos visuales F4."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Mapping

from .f3_inputs import CatalogInput, F3InputError, load_verified_catalog
from .f4_contracts import (
    F4_EMBEDDING_DIMENSION,
    F4_EXPERIMENTAL_PROFILE_ID,
    F4_PROFILE_STATUS,
    F4_VISUAL_CONTRACT_VERSION,
)
from .validation import SchemaValidationError, validate_document


VISUAL_DATASET_ID_PREFIX = "f4-madrid-visual-sha256-"
EMBEDDING_DATASET_ID_PREFIX = "f4-madrid-embeddings-sha256-"


class F4ValidationError(ValueError):
    """Un input o artefacto F4 incumple su contrato o sus referencias."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def visual_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    """Extrae los únicos campos efectivos que identifican el dataset visual."""
    return {
        "contract_version": document["contract_version"],
        "generator_version": document["generator_version"],
        "catalog": dict(document["catalog"]),
        "profile": dict(document["profile"]),
        "source": dict(document["source"]),
        "renderer": dict(document["renderer"]),
        "style": dict(document["style"]),
        "images": [dict(image) for image in document["images"]],
    }


def visual_dataset_id(document: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            visual_identity(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (KeyError, TypeError, ValueError) as error:
        raise F4ValidationError("identidad visual F4 no serializable") from error
    return VISUAL_DATASET_ID_PREFIX + sha256_bytes(encoded)


def embedding_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    """Extrae los inputs y outputs que identifican un dataset de embeddings."""
    return {
        "contract_version": document["contract_version"],
        "visual_dataset": dict(document["visual_dataset"]),
        "model": dict(document["model"]),
        "checkpoint": dict(document["checkpoint"]),
        "preprocessing": dict(document["preprocessing"]),
        "embedding": dict(document["embedding"]),
    }


def embedding_dataset_id(document: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            embedding_identity(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (KeyError, TypeError, ValueError) as error:
        raise F4ValidationError("identidad de embeddings F4 no serializable") from error
    return EMBEDDING_DATASET_ID_PREFIX + sha256_bytes(encoded)


def load_verified_f1_50m(
    manifest_path: str | Path,
    config: Mapping[str, Any],
) -> CatalogInput:
    """Reutiliza la verificación F1 y limita F4.1 al catálogo experimental de 50 m."""
    try:
        catalog = load_verified_catalog(manifest_path, config)
    except F3InputError as error:
        raise F4ValidationError("manifest F1 de F4 inválido") from error
    if catalog.spacing_m != 50 or catalog.cell_size_m != 50:
        raise F4ValidationError("F4.1a requiere spacing_m=50 y cell_size_m=50")
    return catalog


def _coordinates_match(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-10)


def validate_visual_manifest(
    document: Mapping[str, Any],
    catalog: CatalogInput,
) -> None:
    """Valida schema, identidad y correspondencia exacta con candidatos F1."""
    try:
        validate_document(document, "f4_visual_manifest")
    except SchemaValidationError as error:
        raise F4ValidationError("manifest visual F4 inválido") from error

    catalog_ref = document["catalog"]
    expected_catalog = {
        "manifest_id": catalog.manifest_id,
        "manifest_sha256": catalog.sha256,
        "region_id": catalog.region_id,
        "catalog_version": catalog.catalog_version,
        "spacing_m": catalog.spacing_m,
        "cell_size_m": catalog.cell_size_m,
        "grid_hash": catalog.grid_hash,
    }
    if dict(catalog_ref) != expected_catalog:
        raise F4ValidationError("referencia al manifest F1 inconsistente")
    if document["contract_version"] != F4_VISUAL_CONTRACT_VERSION:
        raise F4ValidationError("versión de contrato visual no soportada")
    profile = document["profile"]
    if (
        profile["profile_id"] != F4_EXPERIMENTAL_PROFILE_ID
        or profile["compatibility_status"] != F4_PROFILE_STATUS
    ):
        raise F4ValidationError("perfil visual experimental no soportado")

    candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    seen: set[str] = set()
    previous_id: str | None = None
    for image in document["images"]:
        candidate_id = image["candidate_id"]
        if candidate_id in seen:
            raise F4ValidationError(f"candidate_id duplicado: {candidate_id}")
        if previous_id is not None and candidate_id <= previous_id:
            raise F4ValidationError("las imágenes deben ordenarse por candidate_id")
        previous_id = candidate_id
        seen.add(candidate_id)
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise F4ValidationError(f"candidate_id ajeno al manifest F1: {candidate_id}")
        if not _coordinates_match(image["latitude"], candidate.latitude):
            raise F4ValidationError(f"latitud inconsistente para {candidate_id}")
        if not _coordinates_match(image["longitude"], candidate.longitude):
            raise F4ValidationError(f"longitud inconsistente para {candidate_id}")

    if document["visual_dataset_id"] != visual_dataset_id(document):
        raise F4ValidationError("visual_dataset_id no corresponde a los inputs efectivos")


def validate_embedding_manifest(
    document: Mapping[str, Any],
    visual_manifest: Mapping[str, Any] | None = None,
) -> None:
    """Valida metadatos futuros de embeddings, sin cargar ni calcular vectores."""
    try:
        validate_document(document, "f4_embedding_manifest")
    except SchemaValidationError as error:
        raise F4ValidationError("manifest de embeddings F4 inválido") from error
    if document["embedding"]["dimension"] != F4_EMBEDDING_DIMENSION:
        raise F4ValidationError("la dimensión CrossText2Loc debe ser 768")
    if document["embedding_dataset_id"] != embedding_dataset_id(document):
        raise F4ValidationError("embedding_dataset_id no corresponde a los inputs efectivos")
    if visual_manifest is not None:
        expected = visual_manifest["visual_dataset_id"]
        if document["visual_dataset"]["visual_dataset_id"] != expected:
            raise F4ValidationError("referencia al dataset visual inconsistente")
        generated = sum(image["generation_status"] == "generated" for image in visual_manifest["images"])
        if document["embedding"]["count"] != generated:
            raise F4ValidationError("el número de embeddings no coincide con las imágenes generadas")


def validate_retrieval_result(
    document: Mapping[str, Any],
    catalog: CatalogInput | None = None,
) -> None:
    """Valida un futuro Top-K sin aceptar ni modelar ground truth."""
    try:
        validate_document(document, "f4_retrieval_result")
    except SchemaValidationError as error:
        raise F4ValidationError("resultado Top-K F4 inválido") from error
    if catalog is None:
        return
    candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    for result in document["results"]:
        candidate = candidates.get(result["candidate_id"])
        if candidate is None:
            raise F4ValidationError("resultado con candidate_id ajeno a F1")
        if not _coordinates_match(result["latitude"], candidate.latitude):
            raise F4ValidationError("resultado con latitud inconsistente")
        if not _coordinates_match(result["longitude"], candidate.longitude):
            raise F4ValidationError("resultado con longitud inconsistente")


def load_visual_manifest(path: str | Path, catalog: CatalogInput) -> Mapping[str, Any]:
    """Carga un manifest visual JSON local y verifica todas sus referencias."""
    try:
        raw = Path(path).read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise F4ValidationError("no se pudo cargar el manifest visual F4") from error
    validate_visual_manifest(document, catalog)
    return document


def verify_visual_image_files(
    document: Mapping[str, Any],
    dataset_root: str | Path,
) -> None:
    """Verifica bytes, hash e IHDR PNG de las imágenes marcadas como generadas."""
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
        if len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
            raise F4ValidationError(f"imagen no es PNG con IHDR válido: {image['candidate_id']}")
        width, height, bit_depth, color_type = struct.unpack(">IIBB", raw[16:26])
        if width != image["width_px"] or height != image["height_px"]:
            raise F4ValidationError(f"dimensiones PNG no coinciden: {image['candidate_id']}")
        if bit_depth != 8 or color_type != 2:
            raise F4ValidationError(f"PNG no está codificado como RGB de 8 bits: {image['candidate_id']}")
