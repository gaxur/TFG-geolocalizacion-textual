"""Validaciones básicas de los contratos de Fase 0.

No pretende sustituir a un validador JSON Schema completo. Comprueba los
campos y restricciones necesarias para los contratos iniciales y mantiene el
núcleo libre de dependencias externas.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SchemaValidationError(ValueError):
    """Documento incompatible con el contrato solicitado."""


def _required(document: Mapping[str, Any], fields: tuple[str, ...], context: str) -> None:
    missing = [field for field in fields if field not in document]
    if missing:
        raise SchemaValidationError(f"{context}: faltan campos: {', '.join(missing)}")


def _no_unknown(document: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(document) - allowed
    if unknown:
        raise SchemaValidationError(f"{context}: campos desconocidos: {', '.join(sorted(unknown))}")


def _number(value: Any, field: str, minimum: float | None = None, maximum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaValidationError(f"{field}: debe ser numérico")
    if minimum is not None and value < minimum:
        raise SchemaValidationError(f"{field}: valor inferior al mínimo")
    if maximum is not None and value > maximum:
        raise SchemaValidationError(f"{field}: valor superior al máximo")


def _version(document: Mapping[str, Any], context: str) -> None:
    if document.get("schema_version") != "1.0":
        raise SchemaValidationError(f"{context}: schema_version debe ser '1.0'")


def _validate_bbox(bbox: Any, context: str) -> None:
    if not isinstance(bbox, Mapping):
        raise SchemaValidationError(f"{context}: bbox debe ser un objeto")
    _required(bbox, ("north", "south", "east", "west"), context)
    _no_unknown(bbox, {"north", "south", "east", "west"}, context)
    _number(bbox["north"], f"{context}.north", -90, 90)
    _number(bbox["south"], f"{context}.south", -90, 90)
    _number(bbox["east"], f"{context}.east", -180, 180)
    _number(bbox["west"], f"{context}.west", -180, 180)
    if bbox["south"] >= bbox["north"] or bbox["west"] >= bbox["east"]:
        raise SchemaValidationError(f"{context}: límites invertidos")


def _validate_region_config(document: Mapping[str, Any]) -> None:
    context = "region_config"
    _required(document, ("schema_version", "region", "catalog", "artifacts"), context)
    _no_unknown(document, {"schema_version", "region", "catalog", "artifacts"}, context)
    _version(document, context)

    region = document["region"]
    if not isinstance(region, Mapping):
        raise SchemaValidationError("region debe ser un objeto")
    _required(region, ("name", "bbox", "crs"), "region")
    _no_unknown(region, {"name", "bbox", "crs"}, "region")
    if not isinstance(region["name"], str) or not region["name"]:
        raise SchemaValidationError("region.name debe ser texto no vacío")
    if region["crs"] != "EPSG:4326":
        raise SchemaValidationError("region.crs debe ser EPSG:4326")
    _validate_bbox(region["bbox"], "region.bbox")

    catalog = document["catalog"]
    if not isinstance(catalog, Mapping):
        raise SchemaValidationError("catalog debe ser un objeto")
    _required(catalog, ("projected_crs", "candidate_spacing_m", "candidate_generation"), "catalog")
    _no_unknown(catalog, {"projected_crs", "candidate_spacing_m", "candidate_generation"}, "catalog")
    if catalog["projected_crs"] != "EPSG:25830":
        raise SchemaValidationError("catalog.projected_crs debe ser EPSG:25830")
    spacing = catalog["candidate_spacing_m"]
    if spacing is not None:
        _number(spacing, "catalog.candidate_spacing_m", 0)
    if not isinstance(catalog["candidate_generation"], str) or not catalog["candidate_generation"]:
        raise SchemaValidationError("catalog.candidate_generation debe ser texto no vacío")

    artifacts = document["artifacts"]
    if not isinstance(artifacts, Mapping):
        raise SchemaValidationError("artifacts debe ser un objeto")
    _required(artifacts, ("raw_osm", "processed_osm", "manifest", "embeddings"), "artifacts")
    _no_unknown(artifacts, {"raw_osm", "processed_osm", "manifest", "embeddings"}, "artifacts")
    if any(not isinstance(artifacts[field], str) or not artifacts[field] for field in artifacts):
        raise SchemaValidationError("todos los paths de artifacts deben ser texto no vacío")


def _validate_llm(document: Mapping[str, Any]) -> None:
    context = "llm_geo_query"
    _required(document, ("schema_version", "query_id", "input", "region", "objects", "relations", "visual_clues", "unparsed_clues", "warnings"), context)
    _no_unknown(document, {"schema_version", "query_id", "input", "region", "objects", "relations", "visual_clues", "unparsed_clues", "warnings"}, context)
    _version(document, context)
    if not isinstance(document["query_id"], str) or not document["query_id"]:
        raise SchemaValidationError("query_id debe ser texto no vacío")
    input_data = document["input"]
    if not isinstance(input_data, Mapping):
        raise SchemaValidationError("input debe ser un objeto")
    _required(input_data, ("text", "language"), "input")
    _no_unknown(input_data, {"text", "language"}, "input")
    if not isinstance(input_data["text"], str) or not input_data["text"]:
        raise SchemaValidationError("input.text debe ser texto no vacío")
    if not isinstance(input_data["language"], str) or len(input_data["language"]) < 2:
        raise SchemaValidationError("input.language no es válido")
    if not isinstance(document["objects"], list) or not isinstance(document["relations"], list):
        raise SchemaValidationError("objects y relations deben ser listas")
    for item in document["objects"]:
        if not isinstance(item, Mapping):
            raise SchemaValidationError("cada object debe ser un objeto")
        _required(item, ("id", "mention", "canonical_type", "name", "negated", "certainty", "confidence", "attributes"), "object")
        _no_unknown(item, {"id", "mention", "canonical_type", "name", "negated", "certainty", "confidence", "attributes"}, "object")
        if item["certainty"] not in {"explicit", "inferred", "uncertain"}:
            raise SchemaValidationError("certainty de object no válida")
        if not isinstance(item["attributes"], list):
            raise SchemaValidationError("object.attributes debe ser una lista")
    for field in ("visual_clues", "unparsed_clues", "warnings"):
        if not isinstance(document[field], list):
            raise SchemaValidationError(f"{field} debe ser una lista")


def _validate_manifest(document: Mapping[str, Any]) -> None:
    context = "manifest"
    required = ("schema_version", "manifest_id", "region_id", "catalog_version", "candidates")
    _required(document, required, context)
    _no_unknown(document, set(required) | {"osm_snapshot_id"}, context)
    _version(document, context)
    if not isinstance(document["candidates"], list):
        raise SchemaValidationError("manifest.candidates debe ser una lista")
    for candidate in document["candidates"]:
        if not isinstance(candidate, Mapping):
            raise SchemaValidationError("cada candidato debe ser un objeto")
        required_candidate = ("candidate_id", "latitude", "longitude", "cell_geometry", "artifacts")
        _required(candidate, required_candidate, "candidate")
        _no_unknown(candidate, set(required_candidate) | {"generation"}, "candidate")
        if not isinstance(candidate["candidate_id"], str) or not candidate["candidate_id"]:
            raise SchemaValidationError("candidate_id debe ser texto no vacío")
        _number(candidate["latitude"], "candidate.latitude", -90, 90)
        _number(candidate["longitude"], "candidate.longitude", -180, 180)
        artifacts = candidate["artifacts"]
        if not isinstance(artifacts, Mapping):
            raise SchemaValidationError("candidate.artifacts debe ser un objeto")
        artifact_fields = ("osm_image", "osm_embedding", "satellite_image", "satellite_embedding", "scene_id", "scene_graph", "scene_embedding")
        _required(artifacts, artifact_fields, "candidate.artifacts")
        _no_unknown(artifacts, set(artifact_fields), "candidate.artifacts")


def _validate_experiment(document: Mapping[str, Any]) -> None:
    context = "experiment_parameters"
    required = ("schema_version", "experiment_id", "parameters")
    _required(document, required, context)
    _no_unknown(document, set(required), context)
    _version(document, context)
    parameters = document["parameters"]
    fields = ("candidate_spacing_m", "min_candidates", "target_candidates", "max_candidates", "proximity_radii_m", "relaxation_factors", "scoring_weights", "confidence_thresholds", "language_strategy", "distance_thresholds_m", "confidence_interval_method")
    if not isinstance(parameters, Mapping):
        raise SchemaValidationError("parameters debe ser un objeto")
    _required(parameters, fields, "parameters")
    _no_unknown(parameters, set(fields), "parameters")
    if parameters["candidate_spacing_m"] is not None:
        _number(parameters["candidate_spacing_m"], "parameters.candidate_spacing_m", 0)
    for field in ("min_candidates", "target_candidates", "max_candidates"):
        value = parameters[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise SchemaValidationError(f"parameters.{field} debe ser entero positivo o null")


def _validate_evaluation(document: Mapping[str, Any]) -> None:
    context = "evaluation_example"
    required = ("schema_version", "sample_id", "location_id", "split", "description", "search_scope", "ground_truth", "provenance", "reproducibility", "quality")
    _required(document, required, context)
    _version(document, context)
    _no_unknown(document, set(required), context)
    if document["split"] not in {"smoke", "development", "test"}:
        raise SchemaValidationError("split no válido")
    description = document["description"]
    if not isinstance(description, Mapping):
        raise SchemaValidationError("description debe ser un objeto")
    _required(description, ("text", "language", "source_type", "instructions_version"), "description")
    if description["source_type"] not in {"human_in_situ", "manual_controlled", "vlm_generated", "existing_dataset"}:
        raise SchemaValidationError("source_type no válido")
    ground_truth = document["ground_truth"]
    if not isinstance(ground_truth, Mapping):
        raise SchemaValidationError("ground_truth debe ser un objeto")
    _required(ground_truth, ("latitude", "longitude", "crs", "capture_method", "catalog_assignment"), "ground_truth")
    _number(ground_truth["latitude"], "ground_truth.latitude", -90, 90)
    _number(ground_truth["longitude"], "ground_truth.longitude", -180, 180)
    if ground_truth["crs"] != "EPSG:4326":
        raise SchemaValidationError("ground_truth.crs debe ser EPSG:4326")


def validate_document(document: Any, schema_name: str) -> None:
    if not isinstance(document, Mapping):
        raise SchemaValidationError("el documento raíz debe ser un objeto")
    validators = {
        "region_config": _validate_region_config,
        "llm_geo_query": _validate_llm,
        "evaluation_example": _validate_evaluation,
        "manifest": _validate_manifest,
        "experiment_parameters": _validate_experiment,
    }
    try:
        validator = validators[schema_name]
    except KeyError as exc:
        raise ValueError(f"schema no soportado por el validador básico: {schema_name}") from exc
    validator(document)
