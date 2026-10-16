"""Validaciones comunes de los contratos JSON del proyecto.

No pretende sustituir a un validador JSON Schema completo. Comprueba los
campos y restricciones necesarias para los contratos y mantiene el núcleo
libre de dependencias externas.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
import urllib.parse
from typing import Any

from .f3_contracts import F3_GEOMETRY_REASONS, F3_INVALID_REASONS, F3_NOT_ASSOCIABLE_REASONS
from .f4_contracts import (
    F4_EMBEDDING_CONTRACT_VERSION,
    F4_EMBEDDING_DIMENSION,
    F4_EXPERIMENTAL_PROFILE_ID,
    F4_IMAGE_STATUSES,
    F4_PROFILE_STATUS,
    F4_RETRIEVAL_CONTRACT_VERSION,
    F4_VISUAL_CONTRACT_VERSION,
    F4_VISUAL_GENERATOR_VERSION,
    experimental_visual_profile,
)


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
    _required(document, ("schema_version", "region", "catalog", "osm_acquisition", "artifacts"), context)
    _no_unknown(document, {"schema_version", "region", "catalog", "osm_acquisition", "artifacts"}, context)
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
    catalog_fields = (
        "projected_crs", "catalog_version", "candidate_id_prefix",
        "candidate_spacing_m", "cell_size_m", "candidate_generation",
        "border_policy",
    )
    _required(catalog, catalog_fields, "catalog")
    _no_unknown(catalog, set(catalog_fields), "catalog")
    if catalog["projected_crs"] != "EPSG:25830":
        raise SchemaValidationError("catalog.projected_crs debe ser EPSG:25830")
    for field in ("catalog_version", "candidate_id_prefix"):
        if not isinstance(catalog[field], str) or not catalog[field]:
            raise SchemaValidationError(f"catalog.{field} debe ser texto no vacío")
    if not re.fullmatch(r"[A-Z][A-Z0-9]*", catalog["candidate_id_prefix"]):
        raise SchemaValidationError("catalog.candidate_id_prefix no es válido")
    for field in ("candidate_spacing_m", "cell_size_m"):
        value = catalog[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise SchemaValidationError(f"catalog.{field} debe ser entero positivo o null")
    if catalog["candidate_generation"] != "projected_square_grid":
        raise SchemaValidationError("catalog.candidate_generation no está soportado")
    if catalog["border_policy"] != "full_cell_within_bbox":
        raise SchemaValidationError("catalog.border_policy no está soportado")

    acquisition = document["osm_acquisition"]
    if not isinstance(acquisition, Mapping):
        raise SchemaValidationError("osm_acquisition debe ser un objeto")
    acquisition_fields = (
        "provider", "endpoint", "raw_format", "server_timeout_seconds",
        "connect_timeout_seconds", "http_total_timeout_seconds", "max_retries",
        "backoff_seconds", "retry_after_max_seconds", "max_raw_bytes",
        "acquirer_version", "user_agent",
    )
    _required(acquisition, acquisition_fields, "osm_acquisition")
    _no_unknown(acquisition, set(acquisition_fields), "osm_acquisition")
    expected = {
        "provider": "overpass", "raw_format": "osmxml",
        "server_timeout_seconds": 60, "connect_timeout_seconds": 10,
        "http_total_timeout_seconds": 120, "max_retries": 2,
        "backoff_seconds": [5, 15], "retry_after_max_seconds": 60,
        "acquirer_version": "phase2-overpass-v1",
    }
    for field, value in expected.items():
        if acquisition[field] != value:
            raise SchemaValidationError(f"osm_acquisition.{field} debe ser {value!r}")
    endpoint = acquisition["endpoint"]
    parsed_endpoint = urllib.parse.urlsplit(endpoint) if isinstance(endpoint, str) else None
    if (
        parsed_endpoint is None
        or parsed_endpoint.scheme != "https"
        or not parsed_endpoint.hostname
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or parsed_endpoint.query
        or parsed_endpoint.fragment
    ):
        raise SchemaValidationError("osm_acquisition.endpoint debe usar HTTPS")
    if isinstance(acquisition["max_raw_bytes"], bool) or not isinstance(acquisition["max_raw_bytes"], int) or acquisition["max_raw_bytes"] < 1:
        raise SchemaValidationError("osm_acquisition.max_raw_bytes debe ser entero positivo")
    if not isinstance(acquisition["user_agent"], str) or not acquisition["user_agent"]:
        raise SchemaValidationError("osm_acquisition.user_agent debe ser texto no vacío")

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
    required = (
        "schema_version", "manifest_id", "region_id", "catalog_version",
        "osm_snapshot_id", "generation", "provenance", "candidates",
    )
    _required(document, required, context)
    _no_unknown(document, set(required), context)
    _version(document, context)
    for field in ("manifest_id", "region_id", "catalog_version"):
        if not isinstance(document[field], str) or not document[field]:
            raise SchemaValidationError(f"manifest.{field} debe ser texto no vacío")
    if document["osm_snapshot_id"] is not None and not isinstance(document["osm_snapshot_id"], str):
        raise SchemaValidationError("manifest.osm_snapshot_id debe ser texto o null")
    generation = document["generation"]
    if not isinstance(generation, Mapping):
        raise SchemaValidationError("manifest.generation debe ser un objeto")
    generation_fields = (
        "region_bbox_wgs84", "source_crs", "projected_crs", "spacing_m",
        "cell_size_m", "border_policy", "order", "grid_hash",
        "generator_version",
    )
    _required(generation, generation_fields, "manifest.generation")
    _no_unknown(generation, set(generation_fields), "manifest.generation")
    _validate_bbox(generation["region_bbox_wgs84"], "manifest.generation.region_bbox_wgs84")
    if generation["source_crs"] != "EPSG:4326" or generation["projected_crs"] != "EPSG:25830":
        raise SchemaValidationError("CRS de generación no soportados")
    for field in ("spacing_m", "cell_size_m"):
        value = generation[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise SchemaValidationError(f"manifest.generation.{field} debe ser entero positivo")
    if generation["border_policy"] != "full_cell_within_bbox":
        raise SchemaValidationError("manifest.generation.border_policy no está soportado")
    if generation["order"] != "row_south_to_north_then_column_west_to_east":
        raise SchemaValidationError("manifest.generation.order no está soportado")
    if not isinstance(generation["grid_hash"], str) or not re.fullmatch(r"[0-9a-f]{12}", generation["grid_hash"]):
        raise SchemaValidationError("manifest.generation.grid_hash no es válido")
    if generation["generator_version"] != "phase1-grid-v1":
        raise SchemaValidationError("manifest.generation.generator_version no está soportado")
    provenance = document["provenance"]
    if not isinstance(provenance, Mapping):
        raise SchemaValidationError("manifest.provenance debe ser un objeto")
    provenance_fields = (
        "schema_version", "artifact_id", "source", "source_version",
        "input_hashes", "parameters_hash", "code_version",
    )
    _required(provenance, provenance_fields, "manifest.provenance")
    _no_unknown(provenance, set(provenance_fields), "manifest.provenance")
    _version(provenance, "manifest.provenance")
    if not isinstance(provenance["input_hashes"], Mapping):
        raise SchemaValidationError("manifest.provenance.input_hashes debe ser un objeto")
    if any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or not re.fullmatch(r"[0-9a-f]{64}", value)
        for key, value in provenance["input_hashes"].items()
    ):
        raise SchemaValidationError("manifest.provenance.input_hashes debe contener hashes SHA-256")
    for field in ("artifact_id", "source"):
        if not isinstance(provenance[field], str) or not provenance[field]:
            raise SchemaValidationError(f"manifest.provenance.{field} debe ser texto no vacío")
    for field in ("source_version", "code_version"):
        if provenance[field] is not None and not isinstance(provenance[field], str):
            raise SchemaValidationError(f"manifest.provenance.{field} debe ser texto o null")
    parameters_hash = provenance["parameters_hash"]
    if not isinstance(parameters_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", parameters_hash):
        raise SchemaValidationError("manifest.provenance.parameters_hash debe ser SHA-256")
    if not isinstance(document["candidates"], list):
        raise SchemaValidationError("manifest.candidates debe ser una lista")
    candidate_ids = set()
    for candidate in document["candidates"]:
        if not isinstance(candidate, Mapping):
            raise SchemaValidationError("cada candidato debe ser un objeto")
        required_candidate = ("candidate_id", "latitude", "longitude", "cell_geometry", "artifacts")
        _required(candidate, required_candidate, "candidate")
        _no_unknown(candidate, set(required_candidate) | {"generation"}, "candidate")
        if not isinstance(candidate["candidate_id"], str) or not candidate["candidate_id"]:
            raise SchemaValidationError("candidate_id debe ser texto no vacío")
        if candidate["candidate_id"] in candidate_ids:
            raise SchemaValidationError("candidate_id debe ser único")
        candidate_ids.add(candidate["candidate_id"])
        _number(candidate["latitude"], "candidate.latitude", -90, 90)
        _number(candidate["longitude"], "candidate.longitude", -180, 180)
        geometry = candidate["cell_geometry"]
        if not isinstance(geometry, Mapping):
            raise SchemaValidationError("candidate.cell_geometry debe ser un objeto")
        _required(geometry, ("type", "coordinates"), "candidate.cell_geometry")
        _no_unknown(geometry, {"type", "coordinates"}, "candidate.cell_geometry")
        if geometry["type"] != "Polygon":
            raise SchemaValidationError("candidate.cell_geometry.type debe ser Polygon")
        coordinates = geometry["coordinates"]
        if not isinstance(coordinates, list) or len(coordinates) != 1:
            raise SchemaValidationError("candidate.cell_geometry.coordinates debe contener un anillo")
        ring = coordinates[0]
        if not isinstance(ring, list) or len(ring) != 5 or ring[0] != ring[-1]:
            raise SchemaValidationError("el polígono debe ser un rectángulo cerrado")
        for point in ring:
            if not isinstance(point, list) or len(point) != 2:
                raise SchemaValidationError("cada vértice debe ser [longitude, latitude]")
            _number(point[0], "cell_geometry.longitude", -180, 180)
            _number(point[1], "cell_geometry.latitude", -90, 90)
        longitudes = {point[0] for point in ring[:-1]}
        latitudes = {point[1] for point in ring[:-1]}
        if len(longitudes) < 2 or len(latitudes) < 2:
            raise SchemaValidationError("candidate.cell_geometry no puede ser degenerada")
        if not min(longitudes) <= candidate["longitude"] <= max(longitudes):
            raise SchemaValidationError("candidate.longitude debe estar dentro de la celda")
        if not min(latitudes) <= candidate["latitude"] <= max(latitudes):
            raise SchemaValidationError("candidate.latitude debe estar dentro de la celda")
        artifacts = candidate["artifacts"]
        if not isinstance(artifacts, Mapping):
            raise SchemaValidationError("candidate.artifacts debe ser un objeto")
        artifact_fields = ("osm_image", "osm_embedding", "satellite_image", "satellite_embedding", "scene_id", "scene_graph", "scene_embedding")
        _required(artifacts, artifact_fields, "candidate.artifacts")
        _no_unknown(artifacts, set(artifact_fields), "candidate.artifacts")
        if any(value is not None and not isinstance(value, str) for value in artifacts.values()):
            raise SchemaValidationError("los artefactos deben ser texto o null")
        candidate_generation = candidate.get("generation")
        if not isinstance(candidate_generation, Mapping):
            raise SchemaValidationError("candidate.generation debe ser un objeto")
        fields = ("row", "column", "center_easting_m", "center_northing_m")
        _required(candidate_generation, fields, "candidate.generation")
        _no_unknown(candidate_generation, set(fields), "candidate.generation")
        for field in ("row", "column"):
            value = candidate_generation[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SchemaValidationError(f"candidate.generation.{field} debe ser entero no negativo")
        for field in ("center_easting_m", "center_northing_m"):
            _number(candidate_generation[field], f"candidate.generation.{field}")


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


def _validate_osm_snapshot(document: Mapping[str, Any]) -> None:
    context = "osm_snapshot"
    fields = (
        "schema_version", "osm_snapshot_id", "region_id", "provider", "endpoint",
        "acquired_at_utc", "bbox", "query", "query_sha256", "raw_format",
        "raw_size_bytes", "raw_sha256", "acquirer_version", "counts", "attempts",
        "http", "license", "attribution", "selection", "closure",
    )
    _required(document, fields, context)
    _no_unknown(document, set(fields), context)
    _version(document, context)
    if not isinstance(document["osm_snapshot_id"], str) or not re.fullmatch(r"osm-madrid-pilot-osmxml-sha256-[0-9a-f]{64}", document["osm_snapshot_id"]):
        raise SchemaValidationError("osm_snapshot_id no es válido")
    if document["region_id"] != "madrid_pilot" or document["provider"] != "overpass":
        raise SchemaValidationError("región o proveedor OSM no soportado")
    snapshot_endpoint = document["endpoint"]
    parsed_snapshot_endpoint = (
        urllib.parse.urlsplit(snapshot_endpoint)
        if isinstance(snapshot_endpoint, str)
        else None
    )
    if (
        parsed_snapshot_endpoint is None
        or parsed_snapshot_endpoint.scheme != "https"
        or not parsed_snapshot_endpoint.hostname
        or parsed_snapshot_endpoint.username is not None
        or parsed_snapshot_endpoint.password is not None
        or parsed_snapshot_endpoint.query
        or parsed_snapshot_endpoint.fragment
    ):
        raise SchemaValidationError("endpoint OSM no es válido")
    if not isinstance(document["acquired_at_utc"], str) or not document["acquired_at_utc"].endswith("Z"):
        raise SchemaValidationError("acquired_at_utc debe ser UTC")
    if not isinstance(document["query"], str) or not document["query"]:
        raise SchemaValidationError("query debe ser texto no vacío")
    _validate_bbox(document["bbox"], "osm_snapshot.bbox")
    for field in ("query_sha256", "raw_sha256"):
        if not isinstance(document[field], str) or not re.fullmatch(r"[0-9a-f]{64}", document[field]):
            raise SchemaValidationError(f"osm_snapshot.{field} debe ser SHA-256")
    if document["raw_format"] != "osmxml" or document["acquirer_version"] != "phase2-overpass-v1":
        raise SchemaValidationError("formato o versión de adquirente no soportados")
    if isinstance(document["raw_size_bytes"], bool) or not isinstance(document["raw_size_bytes"], int) or document["raw_size_bytes"] < 1:
        raise SchemaValidationError("raw_size_bytes debe ser entero positivo")
    if isinstance(document["attempts"], bool) or not isinstance(document["attempts"], int) or not 1 <= document["attempts"] <= 3:
        raise SchemaValidationError("attempts debe estar entre 1 y 3")
    counts = document["counts"]
    if not isinstance(counts, Mapping):
        raise SchemaValidationError("counts debe ser un objeto")
    count_fields = (
        "node", "way", "relation", "resolved_relation_members",
        "unresolved_relation_members", "selected_objects", "added_way_nodes",
    )
    _required(counts, count_fields, "osm_snapshot.counts")
    _no_unknown(counts, set(count_fields), "osm_snapshot.counts")
    for field in ("node", "way", "relation"):
        value = counts[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise SchemaValidationError(f"osm_snapshot.counts.{field} debe ser positivo")
    for field in ("resolved_relation_members", "unresolved_relation_members"):
        value = counts[field]
        if not isinstance(value, Mapping):
            raise SchemaValidationError(f"osm_snapshot.counts.{field} debe ser un objeto")
        _required(value, ("node", "way", "relation"), f"osm_snapshot.counts.{field}")
        _no_unknown(value, {"node", "way", "relation"}, f"osm_snapshot.counts.{field}")
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value.values()):
            raise SchemaValidationError(f"osm_snapshot.counts.{field} contiene un valor inválido")
    selected = counts["selected_objects"]
    selected_fields = ("node_bbox", "way_bbox_intersection", "relation_context")
    if not isinstance(selected, Mapping):
        raise SchemaValidationError("osm_snapshot.counts.selected_objects debe ser un objeto")
    _required(selected, selected_fields, "osm_snapshot.counts.selected_objects")
    _no_unknown(selected, set(selected_fields), "osm_snapshot.counts.selected_objects")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in selected.values()):
        raise SchemaValidationError("osm_snapshot.counts.selected_objects contiene un valor inválido")
    if isinstance(counts["added_way_nodes"], bool) or not isinstance(counts["added_way_nodes"], int) or counts["added_way_nodes"] < 0:
        raise SchemaValidationError("osm_snapshot.counts.added_way_nodes no es válido")
    http = document["http"]
    if not isinstance(http, Mapping):
        raise SchemaValidationError("http debe ser un objeto")
    _required(http, ("status", "content_type"), "osm_snapshot.http")
    _no_unknown(http, {"status", "content_type"}, "osm_snapshot.http")
    if isinstance(http["status"], bool) or not isinstance(http["status"], int) or not 100 <= http["status"] <= 599:
        raise SchemaValidationError("http.status no es válido")
    if http["content_type"] is not None and not isinstance(http["content_type"], str):
        raise SchemaValidationError("http.content_type debe ser texto o null")
    if document["license"] != "ODbL-1.0":
        raise SchemaValidationError("license debe ser ODbL-1.0")
    expected_attribution = (
        "© OpenStreetMap contributors. Datos disponibles bajo la Open Database "
        "License (ODbL). https://www.openstreetmap.org/copyright"
    )
    if document["attribution"] != expected_attribution:
        raise SchemaValidationError("attribution OSM no es válida")
    selection = document["selection"]
    if not isinstance(selection, Mapping):
        raise SchemaValidationError("selection debe ser un objeto")
    _required(selection, ("nodes", "ways", "relations"), "osm_snapshot.selection")
    _no_unknown(selection, {"nodes", "ways", "relations"}, "osm_snapshot.selection")
    expected_selection = {
        "nodes": "bbox", "ways": "bbox_intersection",
        "relations": "direct_parent_of_local_node_or_way",
    }
    if dict(selection) != expected_selection:
        raise SchemaValidationError("selection no corresponde a D048")
    closure = document["closure"]
    if not isinstance(closure, Mapping):
        raise SchemaValidationError("closure debe ser un objeto")
    _required(closure, ("ways", "relations"), "osm_snapshot.closure")
    _no_unknown(closure, {"ways", "relations"}, "osm_snapshot.closure")
    if dict(closure) != {"ways": "all_referenced_nodes", "relations": "not_expanded"}:
        raise SchemaValidationError("closure no corresponde a D048")


def _string_map(value: Any, context: str) -> None:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) or not isinstance(item, str)
        for key, item in value.items()
    ):
        raise SchemaValidationError(f"{context} debe mapear strings a strings")


def _positive_id(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SchemaValidationError(f"{field} debe ser un entero positivo")


def _non_negative_integer(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SchemaValidationError(f"{field} debe ser un entero no negativo")


def _finite_number(value: Any, field: str, *, minimum: float | None = None) -> None:
    _number(value, field, minimum=minimum)
    if not math.isfinite(value):
        raise SchemaValidationError(f"{field} debe ser finito")


def _sha256(value: Any, field: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise SchemaValidationError(f"{field} debe ser SHA-256")


def _logical_path(value: Any, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:[\\/]", value)
        or any(part in {"", ".", ".."} for part in value.replace("\\", "/").split("/"))
    ):
        raise SchemaValidationError(f"{field} debe ser un path lógico relativo")


def _validate_metric_bbox(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise SchemaValidationError("metric_bbox debe ser un objeto o null")
    fields = ("min_easting_m", "min_northing_m", "max_easting_m", "max_northing_m")
    _required(value, fields, "metric_bbox")
    _no_unknown(value, set(fields), "metric_bbox")
    for field in fields:
        _finite_number(value[field], f"metric_bbox.{field}")
    if value["min_easting_m"] > value["max_easting_m"] or value["min_northing_m"] > value["max_northing_m"]:
        raise SchemaValidationError("metric_bbox contiene límites invertidos")


def _validate_f3_osm_object(document: Mapping[str, Any]) -> None:
    context = "f3_osm_object"
    fields = (
        "osm_type", "osm_id", "osm_ref", "tags", "source_role",
        "geometry_role", "geometry_status", "geometry_reason", "metric_bbox",
    )
    _required(document, fields, context)
    _no_unknown(document, set(fields) | {"is_closed"}, context)
    osm_type = document["osm_type"]
    if osm_type not in {"node", "way"}:
        raise SchemaValidationError("f3_osm_object.osm_type no válido")
    _positive_id(document["osm_id"], "f3_osm_object.osm_id")
    if document["osm_ref"] != f"{osm_type}/{document['osm_id']}":
        raise SchemaValidationError("f3_osm_object.osm_ref no corresponde a su identidad")
    _string_map(document["tags"], "f3_osm_object.tags")
    source_role = document["source_role"]
    expected_roles = {
        "node": {"node_bbox", "added_way_node"},
        "way": {"way_bbox_intersection"},
    }
    if source_role not in expected_roles[osm_type]:
        raise SchemaValidationError("f3_osm_object.source_role no corresponde al tipo")
    role = document["geometry_role"]
    status = document["geometry_status"]
    reason = document["geometry_reason"]
    if role not in {"point", "line", "area", "none"}:
        raise SchemaValidationError("f3_osm_object.geometry_role no válido")
    if status not in {"valid", "not_associable", "invalid"}:
        raise SchemaValidationError("f3_osm_object.geometry_status no válido")
    if status == "valid" and (role == "none" or reason is not None):
        raise SchemaValidationError("un objeto válido requiere geometría y razón null")
    if status == "valid" and document["metric_bbox"] is None:
        raise SchemaValidationError("un objeto válido requiere metric_bbox")
    if status != "valid" and reason not in F3_GEOMETRY_REASONS:
        raise SchemaValidationError("un objeto no válido o no asociable requiere una razón conocida")
    if status == "not_associable" and reason not in F3_NOT_ASSOCIABLE_REASONS:
        raise SchemaValidationError("geometry_reason no corresponde a not_associable")
    if status == "invalid" and reason not in F3_INVALID_REASONS:
        raise SchemaValidationError("geometry_reason no corresponde a invalid")
    if osm_type == "node":
        if "is_closed" in document:
            raise SchemaValidationError("is_closed no está permitido para nodes")
        if role != "point":
            raise SchemaValidationError("un node debe tener geometry_role point")
        if source_role == "node_bbox" and status != "valid":
            raise SchemaValidationError("un node_bbox debe ser válido")
        if source_role == "added_way_node" and (
            status != "not_associable"
            or reason != "added_way_node_direct_association_forbidden"
        ):
            raise SchemaValidationError("un added_way_node no puede asociarse directamente")
    else:
        if not isinstance(document.get("is_closed"), bool):
            raise SchemaValidationError("is_closed es obligatorio para ways")
        if status == "valid" and role not in {"line", "area"}:
            raise SchemaValidationError("un way válido debe ser line o area")
        if status != "valid" and role != "none":
            raise SchemaValidationError("un way no asociable o inválido debe usar geometry_role none")
        if status == "not_associable" and not reason.startswith("unknown_closed_way_"):
            raise SchemaValidationError("un way no asociable debe ser unknown_closed_way")
        if status == "not_associable" and document["is_closed"] is not True:
            raise SchemaValidationError("unknown_closed_way requiere un way cerrado")
        if reason == "invalid_area_open_way" and document["is_closed"] is not False:
            raise SchemaValidationError("invalid_area_open_way requiere un way abierto")
        if reason in {"invalid_area_empty", "invalid_area_non_positive", "invalid_area_invalid_polygon"} and document["is_closed"] is not True:
            raise SchemaValidationError("la razón invalid_area requiere un way cerrado")
    _validate_metric_bbox(document["metric_bbox"])


def _validate_f3_association(document: Mapping[str, Any]) -> None:
    context = "f3_association"
    fields = (
        "candidate_id", "osm_type", "osm_id", "osm_ref", "geometry_role",
        "intersects", "contains", "within", "crosses", "touches", "overlaps",
        "boundary_contact_only", "center_distance_m",
    )
    _required(document, fields, context)
    _no_unknown(document, set(fields), context)
    if not isinstance(document["candidate_id"], str) or not document["candidate_id"]:
        raise SchemaValidationError("f3_association.candidate_id debe ser texto no vacío")
    osm_type = document["osm_type"]
    if osm_type not in {"node", "way"}:
        raise SchemaValidationError("f3_association.osm_type no válido")
    _positive_id(document["osm_id"], "f3_association.osm_id")
    if document["osm_ref"] != f"{osm_type}/{document['osm_id']}":
        raise SchemaValidationError("f3_association.osm_ref no corresponde a su identidad")
    role = document["geometry_role"]
    if role not in {"point", "line", "area"}:
        raise SchemaValidationError("f3_association.geometry_role no válido")
    if (osm_type == "node" and role != "point") or (osm_type == "way" and role == "point"):
        raise SchemaValidationError("f3_association.geometry_role no corresponde al tipo")
    for field in ("intersects", "contains", "within", "crosses", "touches", "overlaps", "boundary_contact_only"):
        if not isinstance(document[field], bool):
            raise SchemaValidationError(f"f3_association.{field} debe ser booleano")
    if document["intersects"] is not True:
        raise SchemaValidationError("una asociación F3 debe cumplir intersects=true")
    if document["boundary_contact_only"] != document["touches"]:
        raise SchemaValidationError("boundary_contact_only debe ser igual a touches en F3 v1")
    _finite_number(document["center_distance_m"], "f3_association.center_distance_m", minimum=0)


def _validate_type_counts(value: Any, context: str) -> None:
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{context} debe ser un objeto")
    _required(value, ("node", "way", "relation"), context)
    _no_unknown(value, {"node", "way", "relation"}, context)
    for key, count in value.items():
        _non_negative_integer(count, f"{context}.{key}")


def _validate_f3_relation_context(document: Mapping[str, Any]) -> None:
    context = "f3_relation_context"
    fields = (
        "relation_id", "relation_ref", "tags", "closure_status", "member_count",
        "present_member_counts", "unresolved_member_counts", "associated_members",
    )
    _required(document, fields, context)
    _no_unknown(document, set(fields), context)
    _positive_id(document["relation_id"], "f3_relation_context.relation_id")
    if document["relation_ref"] != f"relation/{document['relation_id']}":
        raise SchemaValidationError("f3_relation_context.relation_ref no corresponde a su identidad")
    _string_map(document["tags"], "f3_relation_context.tags")
    if document["closure_status"] != "not_expanded":
        raise SchemaValidationError("f3_relation_context.closure_status no válido")
    _non_negative_integer(document["member_count"], "f3_relation_context.member_count")
    _validate_type_counts(document["present_member_counts"], "present_member_counts")
    _validate_type_counts(document["unresolved_member_counts"], "unresolved_member_counts")
    total = sum(document["present_member_counts"].values()) + sum(document["unresolved_member_counts"].values())
    if total != document["member_count"]:
        raise SchemaValidationError("member_count no coincide con members presentes y ausentes")
    members = document["associated_members"]
    if not isinstance(members, list) or not members:
        raise SchemaValidationError("associated_members debe ser una lista no vacía")
    seen_members = set()
    associated_counts = {"node": 0, "way": 0, "relation": 0}
    for member in members:
        member_fields = ("member_type", "member_id", "member_ref", "role", "candidate_ids")
        if not isinstance(member, Mapping):
            raise SchemaValidationError("cada associated_member debe ser un objeto")
        _required(member, member_fields, "associated_member")
        _no_unknown(member, set(member_fields), "associated_member")
        member_type = member["member_type"]
        if member_type not in {"node", "way"}:
            raise SchemaValidationError("associated_member.member_type no válido")
        _positive_id(member["member_id"], "associated_member.member_id")
        if member["member_ref"] != f"{member_type}/{member['member_id']}":
            raise SchemaValidationError("associated_member.member_ref no corresponde a su identidad")
        if not isinstance(member["role"], str):
            raise SchemaValidationError("associated_member.role debe ser texto")
        identity = (member_type, member["member_id"], member["role"])
        if identity in seen_members:
            raise SchemaValidationError("associated_members contiene un member duplicado")
        seen_members.add(identity)
        associated_counts[member_type] += 1
        candidates = member["candidate_ids"]
        if not isinstance(candidates, list) or not candidates or any(not isinstance(item, str) or not item for item in candidates):
            raise SchemaValidationError("candidate_ids debe contener strings no vacíos")
        if len(candidates) != len(set(candidates)):
            raise SchemaValidationError("candidate_ids no puede contener duplicados")
    for member_type in ("node", "way"):
        if associated_counts[member_type] > document["present_member_counts"][member_type]:
            raise SchemaValidationError(
                f"associated_members de tipo {member_type} supera present_member_counts"
            )


def _validate_f3_provenance(document: Mapping[str, Any]) -> None:
    context = "f3_provenance"
    fields = (
        "schema_version", "f3_dataset_id", "generator_version", "contract_version",
        "inputs", "geometry", "software", "serialization", "counts",
    )
    _required(document, fields, context)
    _no_unknown(document, set(fields), context)
    _version(document, context)
    if not isinstance(document["f3_dataset_id"], str) or not re.fullmatch(r"f3-madrid-pilot-associations-sha256-[0-9a-f]{64}", document["f3_dataset_id"]):
        raise SchemaValidationError("f3_dataset_id no es válido")
    if document["generator_version"] != "phase3-geometric-associations-v1" or document["contract_version"] != "f3-associations-v1":
        raise SchemaValidationError("versiones F3 no soportadas")
    top_level_fields = {
        "inputs": {"catalog", "osm", "rules", "config"},
        "geometry": {
            "source_crs", "projected_crs", "transform_name", "transform_version",
            "transform_source_sha256", "association_predicate", "predicate_direction",
            "boundary_contact_policy", "relation_policy", "invalid_geometry_policy",
            "direct_node_policy",
        },
        "software": {
            "generator_source_sha256", "python_implementation", "python_version",
            "numpy_version", "shapely_version", "geos_version", "platform_system", "platform_machine",
        },
        "serialization": {
            "version", "encoding", "ensure_ascii", "allow_nan", "separators",
            "key_order", "row_order", "metric_rounding_digits",
            "negative_zero_policy", "final_newline",
        },
    }
    for field, expected in top_level_fields.items():
        value = document[field]
        if not isinstance(value, Mapping):
            raise SchemaValidationError(f"f3_provenance.{field} debe ser un objeto")
        _required(value, tuple(expected), f"f3_provenance.{field}")
        _no_unknown(value, expected, f"f3_provenance.{field}")

    inputs = document["inputs"]
    catalog = inputs["catalog"]
    catalog_fields = {
        "logical_path", "size_bytes", "sha256", "schema_version", "manifest_id",
        "region_id", "catalog_version", "spacing_m", "cell_size_m", "source_crs",
        "projected_crs", "grid_hash", "generator_version",
    }
    if not isinstance(catalog, Mapping):
        raise SchemaValidationError("f3_provenance.inputs.catalog debe ser un objeto")
    _required(catalog, tuple(catalog_fields), "f3_provenance.inputs.catalog")
    _no_unknown(catalog, catalog_fields, "f3_provenance.inputs.catalog")
    _logical_path(catalog["logical_path"], "f3_provenance.inputs.catalog.logical_path")
    _non_negative_integer(catalog["size_bytes"], "f3_provenance.inputs.catalog.size_bytes")
    if catalog["size_bytes"] == 0:
        raise SchemaValidationError("catalog.size_bytes debe ser positivo")
    _sha256(catalog["sha256"], "f3_provenance.inputs.catalog.sha256")
    if catalog["schema_version"] != "1.0" or catalog["region_id"] != "madrid_pilot":
        raise SchemaValidationError("schema o región del catálogo F3 no válidos")
    for field in ("manifest_id", "catalog_version"):
        if not isinstance(catalog[field], str) or not catalog[field]:
            raise SchemaValidationError(f"catalog.{field} debe ser texto no vacío")
    for field in ("spacing_m", "cell_size_m"):
        _positive_id(catalog[field], f"catalog.{field}")
    if catalog["source_crs"] != "EPSG:4326" or catalog["projected_crs"] != "EPSG:25830":
        raise SchemaValidationError("CRS del catálogo F3 no válidos")
    if not isinstance(catalog["grid_hash"], str) or not re.fullmatch(r"[0-9a-f]{12}", catalog["grid_hash"]):
        raise SchemaValidationError("catalog.grid_hash no válido")
    if catalog["generator_version"] != "phase1-grid-v1":
        raise SchemaValidationError("catalog.generator_version no soportado")

    osm = inputs["osm"]
    osm_fields = {
        "logical_path", "provenance_logical_path", "osm_snapshot_id", "raw_sha256",
        "raw_size_bytes", "schema_version", "region_id", "selection", "closure",
    }
    if not isinstance(osm, Mapping):
        raise SchemaValidationError("f3_provenance.inputs.osm debe ser un objeto")
    _required(osm, tuple(osm_fields), "f3_provenance.inputs.osm")
    _no_unknown(osm, osm_fields, "f3_provenance.inputs.osm")
    for field in ("logical_path", "provenance_logical_path"):
        _logical_path(osm[field], f"f3_provenance.inputs.osm.{field}")
    if not isinstance(osm["osm_snapshot_id"], str) or not re.fullmatch(r"osm-madrid-pilot-osmxml-sha256-[0-9a-f]{64}", osm["osm_snapshot_id"]):
        raise SchemaValidationError("inputs.osm.osm_snapshot_id no válido")
    _sha256(osm["raw_sha256"], "f3_provenance.inputs.osm.raw_sha256")
    if not osm["osm_snapshot_id"].endswith(osm["raw_sha256"]):
        raise SchemaValidationError("osm_snapshot_id no corresponde a raw_sha256")
    _positive_id(osm["raw_size_bytes"], "f3_provenance.inputs.osm.raw_size_bytes")
    if osm["schema_version"] != "1.0" or osm["region_id"] != "madrid_pilot":
        raise SchemaValidationError("schema o región del snapshot F3 no válidos")
    if osm["selection"] != {
        "nodes": "bbox", "ways": "bbox_intersection",
        "relations": "direct_parent_of_local_node_or_way",
    }:
        raise SchemaValidationError("inputs.osm.selection no corresponde a D048")
    if osm["closure"] != {"ways": "all_referenced_nodes", "relations": "not_expanded"}:
        raise SchemaValidationError("inputs.osm.closure no corresponde a D048")

    rules = inputs["rules"]
    expected_rules = {
        "decision": "D049",
        "policy": "way_is_area-v1",
        "repository": "https://github.com/tyrasd/osm-polygon-features",
        "release": "v0.9.2",
        "commit": "069a46416629ddbe84390c7a3ccc600fe73ee706",
        "file": "polygon-features.json",
        "size_bytes": 2753,
        "sha256": "cf81018ba820557c59c2c27de7ea6b314009abed040cd11249e94ed1a3a10583",
        "license": "CC0-1.0",
    }
    if not isinstance(rules, Mapping) or dict(rules) != expected_rules:
        raise SchemaValidationError("inputs.rules no corresponde a D049")

    config = inputs["config"]
    config_fields = {"logical_path", "schema_version", "file_sha256", "canonical_policy", "canonical_sha256"}
    if not isinstance(config, Mapping):
        raise SchemaValidationError("f3_provenance.inputs.config debe ser un objeto")
    _required(config, tuple(config_fields), "f3_provenance.inputs.config")
    _no_unknown(config, config_fields, "f3_provenance.inputs.config")
    _logical_path(config["logical_path"], "f3_provenance.inputs.config.logical_path")
    if config["schema_version"] != "1.0":
        raise SchemaValidationError("inputs.config.schema_version no válido")
    if config["canonical_policy"] != "f3-config-v1":
        raise SchemaValidationError("inputs.config.canonical_policy no válido")
    for field in ("file_sha256", "canonical_sha256"):
        _sha256(config[field], f"f3_provenance.inputs.config.{field}")

    geometry = document["geometry"]
    expected_geometry = {
        "source_crs": "EPSG:4326",
        "projected_crs": "EPSG:25830",
        "transform_name": "tfg_phase0.crs.wgs84_to_epsg25830",
        "transform_version": "phase1-crs-v1",
        "association_predicate": "intersects",
        "predicate_direction": "osm_geometry_to_candidate_cell",
        "boundary_contact_policy": "touches",
        "relation_policy": "present_associated_members_one_hop",
        "invalid_geometry_policy": "reject_without_repair",
        "direct_node_policy": "node_bbox_only",
    }
    if any(geometry[field] != value for field, value in expected_geometry.items()):
        raise SchemaValidationError("f3_provenance.geometry no corresponde a D050")
    _sha256(geometry["transform_source_sha256"], "geometry.transform_source_sha256")

    software = document["software"]
    for field in ("python_implementation", "python_version", "numpy_version", "shapely_version", "geos_version", "platform_system", "platform_machine"):
        if not isinstance(software[field], str) or not software[field]:
            raise SchemaValidationError(f"f3_provenance.software.{field} debe ser texto no vacío")
    _sha256(software["generator_source_sha256"], "f3_provenance.software.generator_source_sha256")

    serialization = document["serialization"]
    expected_serialization = {
        "version": "f3-jsonl-v1",
        "encoding": "UTF-8",
        "ensure_ascii": False,
        "allow_nan": False,
        "separators": [",", ":"],
        "key_order": "lexicographic",
        "metric_rounding_digits": 6,
        "negative_zero_policy": "normalize_to_positive_zero",
        "final_newline": True,
    }
    if any(serialization[field] != value for field, value in expected_serialization.items()):
        raise SchemaValidationError("f3_provenance.serialization no corresponde a D050")
    expected_row_order = {
        "osm_objects": "osm_type_node_way_then_osm_id_numeric",
        "associations": "candidate_id_then_osm_type_node_way_then_osm_id_numeric",
        "relations": "relation_id_numeric",
        "members": "member_type_node_way_relation_then_member_id_numeric_then_role",
        "candidate_ids": "lexicographic_unique",
    }
    if serialization["row_order"] != expected_row_order:
        raise SchemaValidationError("f3_provenance.serialization.row_order no válido")

    counts = document["counts"]
    if not isinstance(counts, Mapping):
        raise SchemaValidationError("f3_provenance.counts debe ser un objeto")
    count_fields = {
        "input_objects", "objects_by_type", "objects_by_source_role",
        "objects_by_geometry_role", "objects_by_geometry_status", "associations",
        "boundary_contact_only", "multi_cell_objects", "unknown_closed_way",
        "invalid_area", "invalid_way_geometry", "relations_input",
        "relations_emitted", "relations_without_associated_members",
        "present_relation_members", "unresolved_relation_members",
    }
    _required(counts, tuple(count_fields), "f3_provenance.counts")
    _no_unknown(counts, count_fields, "f3_provenance.counts")
    for field, value in counts.items():
        if field in {"input_objects", "present_relation_members", "unresolved_relation_members"}:
            _validate_type_counts(value, f"f3_provenance.counts.{field}")
        elif isinstance(value, Mapping):
            for key, count in value.items():
                _non_negative_integer(count, f"f3_provenance.counts.{field}.{key}")
        else:
            _non_negative_integer(value, f"f3_provenance.counts.{field}")


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


def _validate_f4_query_dataset(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "dataset_id", "dataset_version", "region", "catalog", "partition_policy", "queries"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "f4-query-dataset-v1":
        raise SchemaValidationError("f4_query_dataset incompatible")
    if not isinstance(document["dataset_id"], str) or not re.fullmatch(r"f4-madrid-queries-sha256-[0-9a-f]{64}", document["dataset_id"]):
        raise SchemaValidationError("f4_query_dataset.dataset_id no válido")
    _non_empty_string(document["dataset_version"], "f4_query_dataset.dataset_version")
    region = document["region"]
    if not isinstance(region, Mapping) or set(region) != {"region_id", "bbox_wgs84"} or region["region_id"] != "madrid_pilot":
        raise SchemaValidationError("región del dataset F4.3 no válida")
    _validate_bbox(region["bbox_wgs84"], "f4_query_dataset.region.bbox_wgs84")
    catalog = document["catalog"]
    if not isinstance(catalog, Mapping) or set(catalog) != {"manifest_id", "manifest_sha256", "candidate_count", "assignment_policy"}:
        raise SchemaValidationError("catálogo del dataset F4.3 no válido")
    _non_empty_string(catalog["manifest_id"], "f4_query_dataset.catalog.manifest_id")
    _sha256(catalog["manifest_sha256"], "f4_query_dataset.catalog.manifest_sha256")
    if catalog["candidate_count"] not in {253, 1115} or catalog["assignment_policy"] != "projected_cell_interior_boundary_ambiguous_v1":
        raise SchemaValidationError("política de asignación F4.3 no válida")
    policy = document["partition_policy"]
    if not isinstance(policy, Mapping) or set(policy) != {"version", "group_by", "evaluation_frozen", "evaluation_use_restriction", "near_duplicate_token_jaccard_threshold"}:
        raise SchemaValidationError("política de partición F4.3 no válida")
    if policy["version"] != "location-and-derivation-group-v1" or policy["group_by"] != ["location_id", "derivation_group_id"] or policy["evaluation_use_restriction"] != "no_parameter_prompt_checkpoint_or_pipeline_selection":
        raise SchemaValidationError("política de partición F4.3 no soportada")
    if not isinstance(policy["evaluation_frozen"], bool):
        raise SchemaValidationError("evaluation_frozen debe ser booleano")
    _finite_number(policy["near_duplicate_token_jaccard_threshold"], "near_duplicate_token_jaccard_threshold", minimum=0)
    if policy["near_duplicate_token_jaccard_threshold"] > 1:
        raise SchemaValidationError("umbral Jaccard fuera de rango")
    if not isinstance(document["queries"], list):
        raise SchemaValidationError("queries debe ser una lista")
    for index, query in enumerate(document["queries"]):
        _validate_f4_query(query, f"queries[{index}]")


def _validate_f4_query(query: Any, label: str) -> None:
    fields = {"query_id", "location_id", "derivation_group_id", "partition", "description", "provenance", "reference", "ambiguity", "validation_status"}
    if not isinstance(query, Mapping) or set(query) != fields:
        raise SchemaValidationError(f"{label} incompatible")
    _non_empty_string(query["query_id"], f"{label}.query_id")
    if query["location_id"] is not None:
        _non_empty_string(query["location_id"], f"{label}.location_id")
    _non_empty_string(query["derivation_group_id"], f"{label}.derivation_group_id")
    if query["partition"] not in {"development", "evaluation"} or query["validation_status"] not in {"pending", "validated", "rejected"}:
        raise SchemaValidationError(f"{label} contiene estado o partición no válidos")
    description = query["description"]
    if not isinstance(description, Mapping) or set(description) != {"text", "language", "contains_coordinates"}:
        raise SchemaValidationError(f"{label}.description no válida")
    _non_empty_string(description["text"], f"{label}.description.text")
    _non_empty_string(description["language"], f"{label}.description.language")
    if description["contains_coordinates"] is not False:
        raise SchemaValidationError("las consultas ordinarias F4.3 no contienen coordenadas")
    provenance = query["provenance"]
    provenance_fields = {"source_type", "description", "independent_environment_observation", "instructions_version", "collected_at_utc"}
    if not isinstance(provenance, Mapping) or set(provenance) != provenance_fields or provenance["source_type"] not in {"human_in_situ", "osm_map_observed", "synthetic", "model_assisted", "technical_probe", "existing_dataset"}:
        raise SchemaValidationError(f"{label}.provenance no válida")
    for field in ("description", "instructions_version"):
        _non_empty_string(provenance[field], f"{label}.provenance.{field}")
    if not isinstance(provenance["independent_environment_observation"], bool) or (provenance["collected_at_utc"] is not None and not isinstance(provenance["collected_at_utc"], str)):
        raise SchemaValidationError(f"{label}.provenance incompleta")
    reference = query["reference"]
    reference_fields = {"status", "latitude", "longitude", "crs", "capture_method", "reported_accuracy_m", "validation_method", "catalog_assignment"}
    if not isinstance(reference, Mapping) or set(reference) != reference_fields or reference["status"] not in {"pending", "validated", "rejected"}:
        raise SchemaValidationError(f"{label}.reference no válida")
    if reference["latitude"] is not None:
        _finite_number(reference["latitude"], f"{label}.reference.latitude", minimum=-90)
        if reference["latitude"] > 90:
            raise SchemaValidationError("latitud fuera de rango")
    if reference["longitude"] is not None:
        _finite_number(reference["longitude"], f"{label}.reference.longitude", minimum=-180)
        if reference["longitude"] > 180:
            raise SchemaValidationError("longitud fuera de rango")
    if reference["crs"] not in {None, "EPSG:4326"} or (reference["reported_accuracy_m"] is not None and (not isinstance(reference["reported_accuracy_m"], (int, float)) or reference["reported_accuracy_m"] < 0)):
        raise SchemaValidationError(f"{label}.reference contiene CRS o precisión no válidos")
    assignment = reference["catalog_assignment"]
    if assignment is not None:
        base_assignment_fields = {"status", "candidate_id", "center_distance_m", "distance_to_cell_boundary_m", "boundary_ambiguous"}
        allowed_assignment_fields = base_assignment_fields | {"candidate_ids"}
        if not isinstance(assignment, Mapping) or not base_assignment_fields <= set(assignment) or not set(assignment) <= allowed_assignment_fields:
            raise SchemaValidationError(f"{label}.reference.catalog_assignment no válida")
        if assignment["status"] not in {"assigned", "outside_region", "outside_catalog_coverage", "boundary_ambiguous", "accuracy_insufficient"} or not isinstance(assignment["boundary_ambiguous"], bool):
            raise SchemaValidationError(f"{label}.reference.catalog_assignment contiene estado no válido")
    ambiguity = query["ambiguity"]
    if not isinstance(ambiguity, Mapping) or set(ambiguity) != {"status", "notes"} or ambiguity["status"] not in {"unreviewed", "not_ambiguous", "ambiguous"}:
        raise SchemaValidationError(f"{label}.ambiguity no válida")


def _validate_f4_evaluation_result(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "evaluation_id", "protocol", "inputs", "coverage", "metrics", "per_query"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "f4-evaluation-result-v1":
        raise SchemaValidationError("f4_evaluation_result incompatible")
    if not isinstance(document["evaluation_id"], str) or not re.fullmatch(r"f4-madrid-evaluation-sha256-[0-9a-f]{64}", document["evaluation_id"]):
        raise SchemaValidationError("evaluation_id no válido")
    for field in ("protocol", "inputs", "coverage", "metrics"):
        if not isinstance(document[field], Mapping):
            raise SchemaValidationError(f"f4_evaluation_result.{field} debe ser objeto")
    if not isinstance(document["per_query"], list):
        raise SchemaValidationError("per_query debe ser lista")
    protocol = document["protocol"]
    protocol_fields = {"version", "partition", "exact_match", "distance", "distance_summary_scope", "percentile_method", "percentile_minimum_sample", "ks", "distance_thresholds_m", "ground_truth_ranking_use", "ranking_validation"}
    if set(protocol) != protocol_fields or protocol["version"] != "f4-madrid-exhaustive-evaluation-v1" or protocol["partition"] not in {"development", "evaluation"} or protocol["exact_match"] != "assigned_f1_candidate_id_with_catalog_gaps_as_failures" or protocol["distance"] != "haversine_mean_earth_radius_6371008.8m" or protocol["distance_summary_scope"] != "conditional_on_ranking" or protocol["percentile_method"] != "linear_n_minus_1" or protocol["percentile_minimum_sample"] != 20 or protocol["ks"] != [1, 5, 10] or protocol["distance_thresholds_m"] != [25, 50, 100, 500] or protocol["ground_truth_ranking_use"] is not False or protocol["ranking_validation"] != "producer_contract_and_artifact_sha256":
        raise SchemaValidationError("protocolo F4.3 no válido")
    inputs = document["inputs"]
    input_fields = {"query_dataset_id", "query_dataset_sha256", "catalog_manifest_id", "catalog_manifest_sha256", "visual_dataset_id", "visual_manifest_sha256", "embedding_dataset_id", "embedding_manifest_sha256", "checkpoint_sha256", "ranking_set_id", "ranking_set_sha256", "rankings_frozen_before_reference_access", "ranking_artifacts"}
    if set(inputs) != input_fields:
        raise SchemaValidationError("inputs F4.3 no válidos")
    for field in ("query_dataset_sha256", "catalog_manifest_sha256", "visual_manifest_sha256", "embedding_manifest_sha256", "checkpoint_sha256", "ranking_set_sha256"):
        _sha256(inputs[field], f"f4_evaluation_result.inputs.{field}")
    for field in ("query_dataset_id", "catalog_manifest_id", "visual_dataset_id", "embedding_dataset_id"):
        _non_empty_string(inputs[field], f"f4_evaluation_result.inputs.{field}")
    if not isinstance(inputs["ranking_set_id"], str) or not re.fullmatch(r"f4-madrid-rankings-sha256-[0-9a-f]{64}", inputs["ranking_set_id"]) or not isinstance(inputs["rankings_frozen_before_reference_access"], bool):
        raise SchemaValidationError("referencia al ranking_set no válida")
    if not isinstance(inputs["ranking_artifacts"], list):
        raise SchemaValidationError("ranking_artifacts debe ser lista")
    ranking_ids = set()
    for item in inputs["ranking_artifacts"]:
        if not isinstance(item, Mapping) or set(item) != {"query_id", "logical_path", "sha256"}:
            raise SchemaValidationError("ranking_artifact no válido")
        _non_empty_string(item["query_id"], "ranking_artifact.query_id")
        _logical_path(item["logical_path"], "ranking_artifact.logical_path")
        _sha256(item["sha256"], "ranking_artifact.sha256")
        if item["query_id"] in ranking_ids:
            raise SchemaValidationError("ranking_artifact duplicado")
        ranking_ids.add(item["query_id"])
    coverage = document["coverage"]
    coverage_fields = {"partition_queries", "validated_references", "exact_denominator", "geographic_denominator", "rankings_found", "rankings_top10_ready", "exact_metrics_available", "geographic_metrics_available"}
    if set(coverage) != coverage_fields:
        raise SchemaValidationError("coverage F4.3 no válida")
    for field in coverage_fields - {"exact_metrics_available", "geographic_metrics_available"}:
        _non_negative_integer(coverage[field], f"coverage.{field}")
    if coverage["exact_metrics_available"] != (coverage["exact_denominator"] > 0) or coverage["geographic_metrics_available"] != (coverage["geographic_denominator"] > 0):
        raise SchemaValidationError("disponibilidad de métricas no corresponde a denominadores")
    if coverage["validated_references"] > coverage["partition_queries"] or coverage["exact_denominator"] > coverage["validated_references"] or coverage["geographic_denominator"] > coverage["validated_references"] or coverage["rankings_found"] > coverage["partition_queries"] or coverage["rankings_top10_ready"] > coverage["rankings_found"]:
        raise SchemaValidationError("conteos de cobertura F4.3 inconsistentes")
    metrics = document["metrics"]
    if set(metrics) != {"exact_available", "geographic_available", "exact_recall_at_k", "top1_error_m_conditional_on_ranking", "minimum_error_at_k_m_conditional_on_ranking", "geo_recall_at_k"} or metrics["exact_available"] != coverage["exact_metrics_available"] or metrics["geographic_available"] != coverage["geographic_metrics_available"]:
        raise SchemaValidationError("metrics F4.3 no válidas")
    for value in metrics["exact_recall_at_k"].values():
        if value is not None:
            _finite_number(value, "exact_recall_at_k", minimum=0)
            if value > 1:
                raise SchemaValidationError("Recall fuera de rango")
    if set(metrics["exact_recall_at_k"]) != {"1", "5", "10"} or set(metrics["minimum_error_at_k_m_conditional_on_ranking"]) != {"1", "5", "10"} or set(metrics["geo_recall_at_k"]) != {"1", "5", "10"}:
        raise SchemaValidationError("claves K de métricas no válidas")
    summaries = [metrics["top1_error_m_conditional_on_ranking"], *metrics["minimum_error_at_k_m_conditional_on_ranking"].values()]
    for summary in summaries:
        fields = {"eligible_count", "observed_count", "missing_count", "mean", "median", "p90", "p95", "percentiles_available"}
        if not isinstance(summary, Mapping) or set(summary) != fields:
            raise SchemaValidationError("resumen de distancia no válido")
        for field in ("eligible_count", "observed_count", "missing_count"):
            _non_negative_integer(summary[field], f"distance_summary.{field}")
        if summary["observed_count"] + summary["missing_count"] != summary["eligible_count"] or not isinstance(summary["percentiles_available"], bool):
            raise SchemaValidationError("conteos del resumen de distancia inconsistentes")
        for field in ("mean", "median", "p90", "p95"):
            if summary[field] is not None:
                _finite_number(summary[field], f"distance_summary.{field}", minimum=0)
    for by_threshold in metrics["geo_recall_at_k"].values():
        if set(by_threshold) != {"25", "50", "100", "500"}:
            raise SchemaValidationError("umbrales GeoRecall no válidos")
        for value in by_threshold.values():
            if value is not None:
                _finite_number(value, "geo_recall_at_k", minimum=0)
                if value > 1:
                    raise SchemaValidationError("GeoRecall fuera de rango")
    if len(document["per_query"]) != coverage["partition_queries"]:
        raise SchemaValidationError("per_query no corresponde a partition_queries")
    seen_queries = set()
    for row in document["per_query"]:
        if not isinstance(row, Mapping) or "query_id" not in row or "status" not in row or row["status"] not in {"reference_unavailable", "outside_region", "missing_ranking", "evaluated"}:
            raise SchemaValidationError("fila per_query no válida")
        if row["query_id"] in seen_queries:
            raise SchemaValidationError("query_id duplicado en per_query")
        seen_queries.add(row["query_id"])
    from .f4_evaluation import evaluation_id
    if document["evaluation_id"] != evaluation_id(document):
        raise SchemaValidationError("evaluation_id no corresponde al contenido")


def _validate_f4_ranking_set(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "ranking_set_id", "query_inputs_sha256", "embedding_dataset_id", "checkpoint_sha256", "partition", "frozen_before_reference_access", "rankings"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "f4-ranking-set-v1":
        raise SchemaValidationError("f4_ranking_set incompatible")
    if not isinstance(document["ranking_set_id"], str) or not re.fullmatch(r"f4-madrid-rankings-sha256-[0-9a-f]{64}", document["ranking_set_id"]):
        raise SchemaValidationError("ranking_set_id no válido")
    _sha256(document["query_inputs_sha256"], "ranking_set.query_inputs_sha256")
    _sha256(document["checkpoint_sha256"], "ranking_set.checkpoint_sha256")
    if not isinstance(document["embedding_dataset_id"], str) or not re.fullmatch(r"f4-madrid-embeddings-sha256-[0-9a-f]{64}", document["embedding_dataset_id"]):
        raise SchemaValidationError("ranking_set.embedding_dataset_id no válido")
    if document["partition"] not in {"development", "evaluation"} or not isinstance(document["frozen_before_reference_access"], bool) or not isinstance(document["rankings"], list):
        raise SchemaValidationError("ranking_set contiene partición o freeze no válidos")
    seen = set()
    for item in document["rankings"]:
        if not isinstance(item, Mapping) or set(item) != {"query_id", "logical_path", "sha256", "effective_k"}:
            raise SchemaValidationError("entrada de ranking_set no válida")
        _non_empty_string(item["query_id"], "ranking_set.query_id")
        _logical_path(item["logical_path"], "ranking_set.logical_path")
        _sha256(item["sha256"], "ranking_set.sha256")
        _positive_id(item["effective_k"], "ranking_set.effective_k")
        if item["effective_k"] > 1115 or item["query_id"] in seen:
            raise SchemaValidationError("ranking_set contiene K o query_id no válido")
        seen.add(item["query_id"])
    from .f4_evaluation import ranking_set_id
    if document["ranking_set_id"] != ranking_set_id(document):
        raise SchemaValidationError("ranking_set_id no corresponde al contenido")


def _validate_f4_gallery_comparison(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "comparison_id", "query_inputs_sha256", "checkpoint_sha256", "galleries", "queries", "empirical_metrics_available", "limitations"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "f4-gallery-comparison-v1":
        raise SchemaValidationError("f4_gallery_comparison incompatible")
    if not isinstance(document["comparison_id"], str) or not re.fullmatch(r"f4-madrid-gallery-comparison-sha256-[0-9a-f]{64}", document["comparison_id"]):
        raise SchemaValidationError("comparison_id no válido")
    _sha256(document["query_inputs_sha256"], "comparison.query_inputs_sha256")
    _sha256(document["checkpoint_sha256"], "comparison.checkpoint_sha256")
    if set(document["galleries"]) != {"25m", "50m"} or document["galleries"]["25m"]["candidate_count"] != 1115 or document["galleries"]["50m"]["candidate_count"] != 253:
        raise SchemaValidationError("galerías comparadas no corresponden a 25 m y 50 m")
    if document["empirical_metrics_available"] is not False or not isinstance(document["queries"], list) or not isinstance(document["limitations"], list):
        raise SchemaValidationError("comparación técnica F4.4 no válida")
    seen = set()
    for query in document["queries"]:
        required = {"query_id", "top1_25m", "top1_50m", "top1_cross_gallery_distance_m", "minimum_top10_cross_gallery_distance_m"}
        if not isinstance(query, Mapping) or set(query) != required or query["query_id"] in seen:
            raise SchemaValidationError("consulta comparativa no válida")
        seen.add(query["query_id"])
        for field in ("top1_cross_gallery_distance_m", "minimum_top10_cross_gallery_distance_m"):
            _finite_number(query[field], f"comparison.{field}", minimum=0)
    from .f4_evaluation import gallery_comparison_id
    if document["comparison_id"] != gallery_comparison_id(document):
        raise SchemaValidationError("comparison_id no corresponde al contenido")


def _validate_f4_linguistic_query_set(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "query_set_id", "protocol_version", "partition", "provenance", "groups"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "f4-linguistic-query-set-v1" or document["protocol_version"] != "f4-linguistic-robustness-v1" or document["partition"] != "development":
        raise SchemaValidationError("f4_linguistic_query_set incompatible")
    if not isinstance(document["query_set_id"], str) or not re.fullmatch(r"f4-madrid-linguistic-queries-sha256-[0-9a-f]{64}", document["query_set_id"]):
        raise SchemaValidationError("query_set_id lingüístico no válido")
    provenance = document["provenance"]
    if provenance != {"source_type": "technical_controlled", "independent_environment_observation": False, "ground_truth_available": False, "description": provenance.get("description")}:
        raise SchemaValidationError("provenance lingüística no válida")
    _non_empty_string(provenance["description"], "linguistic.provenance.description")
    if not isinstance(document["groups"], list) or not document["groups"]:
        raise SchemaValidationError("groups lingüísticos vacíos")


def _validate_f4_linguistic_robustness_result(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "robustness_result_id", "query_set_id", "query_set_sha256", "gallery", "checkpoint_sha256", "ranking_set_id", "ranking_set_sha256", "top_k", "comparisons", "aggregates", "geographic_accuracy_available", "limitations"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "f4-linguistic-robustness-result-v1" or document["top_k"] != 10 or document["geographic_accuracy_available"] is not False:
        raise SchemaValidationError("f4_linguistic_robustness_result incompatible")
    if not isinstance(document["robustness_result_id"], str) or not re.fullmatch(r"f4-madrid-linguistic-robustness-sha256-[0-9a-f]{64}", document["robustness_result_id"]):
        raise SchemaValidationError("robustness_result_id no válido")
    for field in ("query_set_sha256", "checkpoint_sha256", "ranking_set_sha256"):
        _sha256(document[field], f"robustness.{field}")
    if not isinstance(document["gallery"], Mapping) or not isinstance(document["comparisons"], list) or not isinstance(document["aggregates"], list) or not isinstance(document["limitations"], list):
        raise SchemaValidationError("estructura de robustez no válida")
    from .f4_robustness import robustness_result_id
    if document["robustness_result_id"] != robustness_result_id(document):
        raise SchemaValidationError("robustness_result_id no corresponde al contenido")


def _validate_crosstext2loc_retrieval_request(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "query", "gallery_ids", "top_k"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "crosstext2loc-retrieval-request-v1":
        raise SchemaValidationError("crosstext2loc_retrieval_request incompatible")
    query = document["query"]
    if not isinstance(query, Mapping) or set(query) != {"query_id", "text", "language"}:
        raise SchemaValidationError("query de retrieval no válida")
    for field in ("query_id", "text", "language"):
        _non_empty_string(query[field], f"retrieval_request.query.{field}")
    if not isinstance(document["gallery_ids"], list) or not 1 <= len(document["gallery_ids"]) <= 2 or len(set(document["gallery_ids"])) != len(document["gallery_ids"]):
        raise SchemaValidationError("gallery_ids debe contener una o dos galerías únicas")
    for gallery_id in document["gallery_ids"]:
        _non_empty_string(gallery_id, "retrieval_request.gallery_id")
    _positive_id(document["top_k"], "retrieval_request.top_k")
    if document["top_k"] > 1115:
        raise SchemaValidationError("top_k excede el máximo soportado")


def _validate_crosstext2loc_retrieval_response(document: Mapping[str, Any]) -> None:
    fields = {"schema_version", "contract_version", "query", "model", "retrievals", "timings_ms"}
    if set(document) != fields or document["schema_version"] != "1.0" or document["contract_version"] != "crosstext2loc-retrieval-response-v1":
        raise SchemaValidationError("crosstext2loc_retrieval_response incompatible")
    query = document["query"]
    if not isinstance(query, Mapping) or set(query) != {"query_id", "text", "language"}:
        raise SchemaValidationError("query de respuesta no válida")
    for field in ("query_id", "text", "language"):
        _non_empty_string(query[field], f"retrieval_response.query.{field}")
    model = document["model"]
    if not isinstance(model, Mapping) or set(model) != {"name", "checkpoint_sha256"} or model["name"] != "CLIP-L/14@336":
        raise SchemaValidationError("modelo de respuesta no válido")
    _sha256(model["checkpoint_sha256"], "retrieval_response.model.checkpoint_sha256")
    retrievals = document["retrievals"]
    if not isinstance(retrievals, list) or not 1 <= len(retrievals) <= 2:
        raise SchemaValidationError("retrievals debe contener una o dos galerías")
    seen_galleries = set()
    for retrieval in retrievals:
        required = {"gallery_id", "visual_dataset_id", "embedding_dataset_id", "gallery_count", "requested_k", "effective_k", "ranking_method", "tie_break", "results"}
        if not isinstance(retrieval, Mapping) or set(retrieval) != required or retrieval["ranking_method"] != "exhaustive_cosine" or retrieval["tie_break"] != "candidate_id_ascending":
            raise SchemaValidationError("retrieval de galería no válido")
        if retrieval["gallery_id"] in seen_galleries:
            raise SchemaValidationError("gallery_id duplicado en respuesta")
        seen_galleries.add(retrieval["gallery_id"])
        for field in ("gallery_id", "visual_dataset_id", "embedding_dataset_id"):
            _non_empty_string(retrieval[field], f"retrieval_response.{field}")
        _positive_id(retrieval["gallery_count"], "retrieval_response.gallery_count")
        _positive_id(retrieval["requested_k"], "retrieval_response.requested_k")
        _positive_id(retrieval["effective_k"], "retrieval_response.effective_k")
        if not isinstance(retrieval["results"], list) or len(retrieval["results"]) != retrieval["effective_k"] or retrieval["effective_k"] != retrieval["requested_k"] or retrieval["effective_k"] > retrieval["gallery_count"]:
            raise SchemaValidationError("results de galería vacío")
        previous_score = None
        seen_candidates = set()
        for index, row in enumerate(retrieval["results"], 1):
            if not isinstance(row, Mapping) or set(row) != {"rank", "candidate_id", "latitude", "longitude", "cosine_similarity"} or row["rank"] != index:
                raise SchemaValidationError("fila de resultado residente no válida")
            _non_empty_string(row["candidate_id"], "retrieval_response.candidate_id")
            if row["candidate_id"] in seen_candidates:
                raise SchemaValidationError("candidate_id duplicado en respuesta")
            seen_candidates.add(row["candidate_id"])
            _finite_number(row["latitude"], "retrieval_response.latitude", minimum=-90)
            _finite_number(row["longitude"], "retrieval_response.longitude", minimum=-180)
            _finite_number(row["cosine_similarity"], "retrieval_response.cosine_similarity", minimum=-1)
            if row["latitude"] > 90 or row["longitude"] > 180 or row["cosine_similarity"] > 1:
                raise SchemaValidationError("resultado residente fuera de rango")
            if previous_score is not None and (row["cosine_similarity"] > previous_score or (row["cosine_similarity"] == previous_score and row["candidate_id"] < retrieval["results"][index - 2]["candidate_id"])):
                raise SchemaValidationError("scores residentes no descendentes")
            previous_score = row["cosine_similarity"]
    timings = document["timings_ms"]
    if not isinstance(timings, Mapping) or set(timings) != {"text_encoding", "ranking_by_gallery", "total"} or not isinstance(timings["ranking_by_gallery"], Mapping):
        raise SchemaValidationError("timings residentes no válidos")
    _finite_number(timings["text_encoding"], "retrieval_response.timings.text_encoding", minimum=0)
    _finite_number(timings["total"], "retrieval_response.timings.total", minimum=0)
    for value in timings["ranking_by_gallery"].values():
        _finite_number(value, "retrieval_response.timings.ranking", minimum=0)
    if set(timings["ranking_by_gallery"]) != seen_galleries:
        raise SchemaValidationError("timings no corresponden a retrievals")


def _non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise SchemaValidationError(f"{field} debe ser texto no vacío")


def _validate_render_bbox(value: Any, field: str) -> None:
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{field} debe ser un objeto")
    fields = ("crs", "min_x", "min_y", "max_x", "max_y")
    _required(value, fields, field)
    _no_unknown(value, set(fields), field)
    if value["crs"] != "EPSG:3857":
        raise SchemaValidationError(f"{field}.crs debe ser EPSG:3857")
    for coordinate in fields[1:]:
        _finite_number(value[coordinate], f"{field}.{coordinate}")
    if value["min_x"] >= value["max_x"] or value["min_y"] >= value["max_y"]:
        raise SchemaValidationError(f"{field} contiene límites invertidos o vacíos")


def _validate_f4_profile(profile: Any) -> None:
    if not isinstance(profile, Mapping):
        raise SchemaValidationError("f4_visual_manifest.profile debe ser un objeto")
    expected = experimental_visual_profile()
    if dict(profile) != expected:
        raise SchemaValidationError(
            f"f4_visual_manifest.profile debe ser {F4_EXPERIMENTAL_PROFILE_ID} "
            f"con estado {F4_PROFILE_STATUS}"
        )


def _validate_f4_visual_manifest(document: Mapping[str, Any]) -> None:
    context = "f4_visual_manifest"
    fields = (
        "schema_version", "visual_dataset_id", "contract_version", "generator_version",
        "catalog", "selection", "profile", "source", "renderer", "style", "images",
    )
    _required(document, fields, context)
    _no_unknown(document, set(fields), context)
    if document["schema_version"] != "2.0":
        raise SchemaValidationError("f4_visual_manifest.schema_version debe ser '2.0'")
    if document["contract_version"] != F4_VISUAL_CONTRACT_VERSION:
        raise SchemaValidationError("f4_visual_manifest.contract_version no soportada")
    if document["generator_version"] != F4_VISUAL_GENERATOR_VERSION:
        raise SchemaValidationError("f4_visual_manifest.generator_version no soportada")
    if not isinstance(document["visual_dataset_id"], str) or not re.fullmatch(
        r"f4-madrid-visual-sha256-[0-9a-f]{64}", document["visual_dataset_id"]
    ):
        raise SchemaValidationError("f4_visual_manifest.visual_dataset_id no válido")

    catalog = document["catalog"]
    catalog_fields = (
        "manifest_id", "manifest_sha256", "region_id", "catalog_version",
        "spacing_m", "cell_size_m", "grid_hash",
    )
    if not isinstance(catalog, Mapping):
        raise SchemaValidationError("f4_visual_manifest.catalog debe ser un objeto")
    _required(catalog, catalog_fields, "f4_visual_manifest.catalog")
    _no_unknown(catalog, set(catalog_fields), "f4_visual_manifest.catalog")
    for field in ("manifest_id", "region_id", "catalog_version"):
        _non_empty_string(catalog[field], f"f4_visual_manifest.catalog.{field}")
    _sha256(catalog["manifest_sha256"], "f4_visual_manifest.catalog.manifest_sha256")
    if catalog["region_id"] != "madrid_pilot":
        raise SchemaValidationError("f4_visual_manifest.catalog.region_id no soportado")
    if (catalog["spacing_m"], catalog["cell_size_m"]) not in {(25, 25), (50, 50)}:
        raise SchemaValidationError("f4_visual_manifest requiere catálogo de 25 m o 50 m")
    if not isinstance(catalog["grid_hash"], str) or not re.fullmatch(r"[0-9a-f]{12}", catalog["grid_hash"]):
        raise SchemaValidationError("f4_visual_manifest.catalog.grid_hash no válido")

    selection = document["selection"]
    if not isinstance(selection, Mapping) or set(selection) != {"selection_id", "logical_path", "sha256"}:
        raise SchemaValidationError("f4_visual_manifest.selection no válida")
    if selection["selection_id"] not in {"f4-nine-candidates-v1", "f4-full-50m-gallery-v1", "f4-full-25m-gallery-v1"}:
        raise SchemaValidationError("f4_visual_manifest.selection_id no soportado")
    _logical_path(selection["logical_path"], "f4_visual_manifest.selection.logical_path")
    _sha256(selection["sha256"], "f4_visual_manifest.selection.sha256")
    _validate_f4_profile(document["profile"])

    source = document["source"]
    source_fields = (
        "contract_version", "source_id", "source_type", "data_path", "data_sha256",
        "provenance_path", "provenance_sha256", "coverage_bbox_wgs84",
        "coverage_bbox_epsg3857", "selection", "closure", "license", "attribution",
    )
    if not isinstance(source, Mapping):
        raise SchemaValidationError("f4_visual_manifest.source debe ser un objeto")
    _required(source, source_fields, "f4_visual_manifest.source")
    _no_unknown(source, set(source_fields), "f4_visual_manifest.source")
    if source["contract_version"] != "f4-osm-source-v1":
        raise SchemaValidationError("f4_visual_manifest.source.contract_version no soportada")
    for field in ("source_id", "license", "attribution"):
        _non_empty_string(source[field], f"f4_visual_manifest.source.{field}")
    if source["source_type"] not in {"osm_snapshot", "osm_render_extract", "synthetic_fixture"}:
        raise SchemaValidationError("f4_visual_manifest.source.source_type no válido")
    _logical_path(source["data_path"], "f4_visual_manifest.source.data_path")
    _logical_path(source["provenance_path"], "f4_visual_manifest.source.provenance_path")
    _sha256(source["data_sha256"], "f4_visual_manifest.source.data_sha256")
    _sha256(source["provenance_sha256"], "f4_visual_manifest.source.provenance_sha256")
    _validate_bbox(source["coverage_bbox_wgs84"], "f4_visual_manifest.source.coverage_bbox_wgs84")
    _validate_render_bbox(source["coverage_bbox_epsg3857"], "f4_visual_manifest.source.coverage_bbox_epsg3857")
    if not isinstance(source["selection"], Mapping) or not isinstance(source["closure"], Mapping):
        raise SchemaValidationError("f4_visual_manifest.source requiere selection y closure")

    renderer = document["renderer"]
    renderer_fields = {
        "contract_version", "renderer_id", "name", "version", "configuration_path",
        "configuration_sha256", "container_image_digest", "license",
    }
    if not isinstance(renderer, Mapping) or set(renderer) != renderer_fields:
        raise SchemaValidationError("f4_visual_manifest.renderer no válido")
    if renderer["contract_version"] != "f4-renderer-provenance-v1":
        raise SchemaValidationError("renderer.contract_version no soportada")
    for field in ("renderer_id", "name", "version", "license"):
        _non_empty_string(renderer[field], f"renderer.{field}")
    _logical_path(renderer["configuration_path"], "renderer.configuration_path")
    _sha256(renderer["configuration_sha256"], "renderer.configuration_sha256")
    if renderer["container_image_digest"] is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", renderer["container_image_digest"]):
        raise SchemaValidationError("renderer.container_image_digest no válido")

    style = document["style"]
    style_fields = {
        "style_id", "version", "repository_commit", "compiled_style_path",
        "compiled_style_sha256", "assets_manifest_path", "assets_manifest_sha256",
        "fonts_manifest_path", "fonts_manifest_sha256", "license",
    }
    if not isinstance(style, Mapping) or set(style) != style_fields:
        raise SchemaValidationError("f4_visual_manifest.style no válido")
    for field in ("style_id", "version", "license"):
        _non_empty_string(style[field], f"style.{field}")
    if not isinstance(style["repository_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", style["repository_commit"]):
        raise SchemaValidationError("style.repository_commit no válido")
    for field in ("compiled_style_path", "assets_manifest_path", "fonts_manifest_path"):
        _logical_path(style[field], f"style.{field}")
    for field in ("compiled_style_sha256", "assets_manifest_sha256", "fonts_manifest_sha256"):
        _sha256(style[field], f"style.{field}")

    images = document["images"]
    if not isinstance(images, list) or not 1 <= len(images) <= 1115:
        raise SchemaValidationError("f4_visual_manifest.images debe contener entre 1 y 1115 entradas")
    image_fields = (
        "candidate_id", "latitude", "longitude", "generation_status", "geometry",
        "image_path", "image_sha256", "width_px", "height_px", "color_mode", "format", "error_code",
    )
    seen = set()
    for index, image in enumerate(images):
        label = f"f4_visual_manifest.images[{index}]"
        if not isinstance(image, Mapping):
            raise SchemaValidationError(f"{label} debe ser un objeto")
        _required(image, image_fields, label)
        _no_unknown(image, set(image_fields), label)
        _non_empty_string(image["candidate_id"], f"{label}.candidate_id")
        if image["candidate_id"] in seen:
            raise SchemaValidationError(f"{label}.candidate_id duplicado")
        seen.add(image["candidate_id"])
        _finite_number(image["latitude"], f"{label}.latitude")
        _finite_number(image["longitude"], f"{label}.longitude")
        if not -90 <= image["latitude"] <= 90 or not -180 <= image["longitude"] <= 180:
            raise SchemaValidationError(f"{label} contiene coordenadas fuera de rango")
        if image["generation_status"] not in F4_IMAGE_STATUSES:
            raise SchemaValidationError(f"{label}.generation_status no válido")

        geometry = image["geometry"]
        geometry_fields = {
            "center_x", "center_y", "global_pixel_x", "global_pixel_y", "request_bbox",
            "source_mosaic_bbox", "output_bbox", "tile_min_x", "tile_min_y", "tile_max_x",
            "tile_max_y", "mosaic_width_px", "mosaic_height_px", "candidate_pixel_x",
            "candidate_pixel_y", "crop_left_px", "crop_top_px", "native_meters_per_pixel",
            "output_meters_per_pixel",
        }
        if not isinstance(geometry, Mapping) or set(geometry) != geometry_fields:
            raise SchemaValidationError(f"{label}.geometry no válida")
        for field in ("center_x", "center_y", "global_pixel_x", "global_pixel_y", "candidate_pixel_x", "candidate_pixel_y", "crop_left_px", "crop_top_px", "native_meters_per_pixel", "output_meters_per_pixel"):
            _finite_number(geometry[field], f"{label}.geometry.{field}")
        for field in ("request_bbox", "source_mosaic_bbox", "output_bbox"):
            _validate_render_bbox(geometry[field], f"{label}.geometry.{field}")
        for field in ("tile_min_x", "tile_min_y", "tile_max_x", "tile_max_y"):
            _non_negative_integer(geometry[field], f"{label}.geometry.{field}")
        for field in ("mosaic_width_px", "mosaic_height_px"):
            _positive_id(geometry[field], f"{label}.geometry.{field}")

        generated = image["generation_status"] == "generated"
        generated_fields = ("image_path", "image_sha256", "width_px", "height_px", "color_mode", "format")
        if generated:
            if any(image[field] is None for field in generated_fields) or image["error_code"] is not None:
                raise SchemaValidationError(f"{label} generado tiene metadatos incompletos")
            _logical_path(image["image_path"], f"{label}.image_path")
            _sha256(image["image_sha256"], f"{label}.image_sha256")
            if image["width_px"] != 512 or image["height_px"] != 512:
                raise SchemaValidationError(f"{label} debe medir 512 x 512")
            if image["color_mode"] != "RGB" or image["format"] != "PNG":
                raise SchemaValidationError(f"{label} debe ser PNG RGB")
        else:
            if any(image[field] is not None for field in generated_fields):
                raise SchemaValidationError(f"{label} fallido no debe declarar artefactos generados")
            if image["error_code"] not in {
                "source_does_not_cover_output_bbox", "renderer_failed", "invalid_rendered_mosaic",
            }:
                raise SchemaValidationError(f"{label}.error_code no válido")


def _validate_f4_embedding_manifest(document: Mapping[str, Any]) -> None:
    context = "f4_embedding_manifest"
    fields = ("schema_version", "embedding_dataset_id", "contract_version", "generator_version", "generator_source_sha256", "visual_dataset", "model", "checkpoint", "preprocessing", "environment", "embedding")
    _required(document, fields, context)
    _no_unknown(document, set(fields), context)
    if document["schema_version"] != "2.0":
        raise SchemaValidationError("f4_embedding_manifest.schema_version debe ser '2.0'")
    if document["contract_version"] != F4_EMBEDDING_CONTRACT_VERSION:
        raise SchemaValidationError("f4_embedding_manifest.contract_version no soportada")
    if document["generator_version"] != "phase4-crosstext2loc-embeddings-v1":
        raise SchemaValidationError("f4_embedding_manifest.generator_version no soportada")
    _sha256(document["generator_source_sha256"], "f4_embedding_manifest.generator_source_sha256")
    if not isinstance(document["embedding_dataset_id"], str) or not re.fullmatch(r"f4-madrid-embeddings-sha256-[0-9a-f]{64}", document["embedding_dataset_id"]):
        raise SchemaValidationError("f4_embedding_manifest.embedding_dataset_id no válido")
    visual = document["visual_dataset"]
    if not isinstance(visual, Mapping) or set(visual) != {"visual_dataset_id", "manifest_sha256"}:
        raise SchemaValidationError("f4_embedding_manifest.visual_dataset no válido")
    if not re.fullmatch(r"f4-madrid-visual-sha256-[0-9a-f]{64}", visual["visual_dataset_id"]):
        raise SchemaValidationError("referencia visual no válida")
    _sha256(visual["manifest_sha256"], "f4_embedding_manifest.visual_dataset.manifest_sha256")
    model = document["model"]
    expected_model_fields = {"name", "architecture", "cvg_text_commit", "cvg_utils_sha256", "openai_clip_commit", "openai_clip_weights_filename", "openai_clip_weights_sha256", "text_context_length"}
    if not isinstance(model, Mapping) or set(model) != expected_model_fields:
        raise SchemaValidationError("f4_embedding_manifest.model no válido")
    if model["name"] != "CLIP-L/14@336" or model["architecture"] != "ViT-L/14@336px" or model["text_context_length"] != 300:
        raise SchemaValidationError("modelo CrossText2Loc no corresponde al contrato")
    expected_model = {
        "cvg_text_commit": "6910d2747a94fbe985309bde60cd4732bcbbf50f",
        "openai_clip_commit": "dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1",
        "openai_clip_weights_filename": "ViT-L-14-336px.pt",
        "openai_clip_weights_sha256": "3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02",
    }
    if any(model[field] != value for field, value in expected_model.items()):
        raise SchemaValidationError("identidad de OpenAI CLIP/CVG-Text no corresponde al contrato")
    _sha256(model["cvg_utils_sha256"], "f4_embedding_manifest.model.cvg_utils_sha256")
    checkpoint = document["checkpoint"]
    if not isinstance(checkpoint, Mapping) or set(checkpoint) != {"filename", "size_bytes", "sha256", "selection_status"}:
        raise SchemaValidationError("f4_embedding_manifest.checkpoint no válido")
    if checkpoint != {"filename": "long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth", "size_bytes": 1712649548, "sha256": "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d", "selection_status": "provisional_d013"}:
        raise SchemaValidationError("checkpoint debe conservar estado provisional D013")
    if document["preprocessing"] != {"policy": "official_openai_clip_preprocess", "input_width_px": 336, "input_height_px": 336, "image_color_mode": "RGB", "text_tokenizer": "clip.tokenize_context_300", "text_truncation": True}:
        raise SchemaValidationError("preprocessing de embeddings no válido")
    environment = document["environment"]
    environment_fields = {"container_image_id", "python_version", "torch_version", "torchvision_version", "cuda_version", "device_type", "inference_dtype"}
    if not isinstance(environment, Mapping) or set(environment) != environment_fields:
        raise SchemaValidationError("entorno de embeddings no válido")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", environment["container_image_id"]):
        raise SchemaValidationError("container_image_id no válido")
    for field in ("python_version", "torch_version", "torchvision_version", "cuda_version"):
        _non_empty_string(environment[field], f"environment.{field}")
    if environment["device_type"] not in {"cuda", "cpu"} or environment["inference_dtype"] != "float32":
        raise SchemaValidationError("dispositivo o dtype de inferencia no válido")
    embedding = document["embedding"]
    embedding_fields = {"matrix_path", "matrix_sha256", "candidate_ids_path", "candidate_ids_sha256", "candidate_ids_format", "count", "dimension", "dtype", "byte_order", "normalization", "row_order"}
    if not isinstance(embedding, Mapping) or set(embedding) != embedding_fields:
        raise SchemaValidationError("f4_embedding_manifest.embedding no válido")
    for field in ("matrix_path", "candidate_ids_path"):
        _logical_path(embedding[field], f"f4_embedding_manifest.embedding.{field}")
    for field in ("matrix_sha256", "candidate_ids_sha256"):
        _sha256(embedding[field], f"f4_embedding_manifest.embedding.{field}")
    _positive_id(embedding["count"], "f4_embedding_manifest.embedding.count")
    expected_embedding = {"dimension": F4_EMBEDDING_DIMENSION, "dtype": "float32", "byte_order": "little", "normalization": "l2", "row_order": "visual_manifest_order", "candidate_ids_format": "jsonl_object_candidate_id_v1"}
    if any(embedding[field] != value for field, value in expected_embedding.items()):
        raise SchemaValidationError("representación de embeddings no válida")


def _validate_f4_visual_selection(document: Mapping[str, Any]) -> None:
    common = {"schema_version", "selection_id", "selection_policy", "source_manifest_id", "source_manifest_sha256", "evaluation_use", "text_or_ground_truth_used"}
    fixture = common | {"candidates"}
    full = common | {"candidate_count", "order"}
    if frozenset(document) not in {frozenset(fixture), frozenset(full)}:
        raise SchemaValidationError("f4_visual_selection incompatible")
    _non_empty_string(document["source_manifest_id"], "selection.source_manifest_id")
    _sha256(document["source_manifest_sha256"], "selection.source_manifest_sha256")
    if document["evaluation_use"] is not False or document["text_or_ground_truth_used"] is not False:
        raise SchemaValidationError("la selección F4 no puede depender de evaluación, texto o ground truth")
    if document["selection_id"] in {"f4-full-50m-gallery-v1", "f4-full-25m-gallery-v1"}:
        expected_count = 253 if document["selection_id"] == "f4-full-50m-gallery-v1" else 1115
        if document["schema_version"] != "2.0" or document["selection_policy"] != "full_verified_catalog_order_v1" or document["candidate_count"] != expected_count or document["order"] != "catalog_manifest_order":
            raise SchemaValidationError("selección de galería completa F4 no soportada")
        return
    if document["schema_version"] != "1.0" or document["selection_id"] != "f4-nine-candidates-v1" or document["selection_policy"] != "fixed_spatial_coverage_v1":
        raise SchemaValidationError("política de selección F4 no soportada")
    candidates = document["candidates"]
    if not isinstance(candidates, list) or len(candidates) != 9:
        raise SchemaValidationError("la fixture F4 debe contener nueve candidatos")
    seen = set()
    for item in candidates:
        if not isinstance(item, Mapping) or set(item) != {"candidate_id", "role"}:
            raise SchemaValidationError("entrada de selección F4 no válida")
        _non_empty_string(item["candidate_id"], "selection.candidate_id")
        _non_empty_string(item["role"], "selection.role")
        if item["candidate_id"] in seen:
            raise SchemaValidationError("candidate_id duplicado en selección F4")
        seen.add(item["candidate_id"])


def _validate_f4_assets_manifest(document: Mapping[str, Any]) -> None:
    if set(document) != {"schema_version", "manifest_id", "kind", "files"} or document["schema_version"] != "1.0":
        raise SchemaValidationError("f4_assets_manifest incompatible")
    _non_empty_string(document["manifest_id"], "assets.manifest_id")
    if document["kind"] not in {"renderer_assets", "fonts"}:
        raise SchemaValidationError("assets.kind no válido")
    files = document["files"]
    if not isinstance(files, list) or not files:
        raise SchemaValidationError("assets.files debe ser una lista no vacía")
    seen = set()
    for item in files:
        if not isinstance(item, Mapping) or set(item) != {"logical_path", "sha256", "size_bytes", "source", "license"}:
            raise SchemaValidationError("entrada de assets no válida")
        _logical_path(item["logical_path"], "assets.logical_path")
        if item["logical_path"] in seen:
            raise SchemaValidationError("path duplicado en assets")
        seen.add(item["logical_path"])
        _sha256(item["sha256"], "assets.sha256")
        _positive_id(item["size_bytes"], "assets.size_bytes")
        _non_empty_string(item["source"], "assets.source")
        _non_empty_string(item["license"], "assets.license")


def _validate_f4_osm_source(document: Mapping[str, Any]) -> None:
    fields = {
        "contract_version", "source_id", "source_type", "data_path", "data_sha256",
        "provenance_path", "provenance_sha256", "coverage_bbox_wgs84",
        "coverage_bbox_epsg3857", "selection", "closure", "license", "attribution",
    }
    if set(document) != fields or document["contract_version"] != "f4-osm-source-v1":
        raise SchemaValidationError("f4_osm_source incompatible")
    for field in ("source_id", "license", "attribution"):
        _non_empty_string(document[field], f"source.{field}")
    if document["source_type"] not in {"osm_snapshot", "osm_render_extract", "synthetic_fixture"}:
        raise SchemaValidationError("source.source_type no válido")
    for field in ("data_path", "provenance_path"):
        _logical_path(document[field], f"source.{field}")
    for field in ("data_sha256", "provenance_sha256"):
        _sha256(document[field], f"source.{field}")
    _validate_bbox(document["coverage_bbox_wgs84"], "source.coverage_bbox_wgs84")
    _validate_render_bbox(document["coverage_bbox_epsg3857"], "source.coverage_bbox_epsg3857")
    if not isinstance(document["selection"], Mapping) or not isinstance(document["closure"], Mapping):
        raise SchemaValidationError("source requiere selection y closure")


def _validate_f4_renderer_provenance(document: Mapping[str, Any]) -> None:
    if set(document) != {"renderer", "style"}:
        raise SchemaValidationError("f4_renderer_provenance incompatible")
    renderer = document["renderer"]
    renderer_fields = {"contract_version", "renderer_id", "name", "version", "configuration_path", "configuration_sha256", "container_image_digest", "license"}
    if not isinstance(renderer, Mapping) or set(renderer) != renderer_fields or renderer["contract_version"] != "f4-renderer-provenance-v1":
        raise SchemaValidationError("renderer provenance no válida")
    for field in ("renderer_id", "name", "version", "license"):
        _non_empty_string(renderer[field], f"renderer.{field}")
    _logical_path(renderer["configuration_path"], "renderer.configuration_path")
    _sha256(renderer["configuration_sha256"], "renderer.configuration_sha256")
    if renderer["container_image_digest"] is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", renderer["container_image_digest"]):
        raise SchemaValidationError("renderer.container_image_digest no válido")
    style = document["style"]
    style_fields = {"style_id", "version", "repository_commit", "compiled_style_path", "compiled_style_sha256", "assets_manifest_path", "assets_manifest_sha256", "fonts_manifest_path", "fonts_manifest_sha256", "license"}
    if not isinstance(style, Mapping) or set(style) != style_fields:
        raise SchemaValidationError("style provenance no válida")
    for field in ("style_id", "version", "license"):
        _non_empty_string(style[field], f"style.{field}")
    if not isinstance(style["repository_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", style["repository_commit"]):
        raise SchemaValidationError("style.repository_commit no válido")
    for field in ("compiled_style_path", "assets_manifest_path", "fonts_manifest_path"):
        _logical_path(style[field], f"style.{field}")
    for field in ("compiled_style_sha256", "assets_manifest_sha256", "fonts_manifest_sha256"):
        _sha256(style[field], f"style.{field}")


def _validate_f4_retrieval_result(document: Mapping[str, Any]) -> None:
    context = "f4_retrieval_result"
    fields = ("schema_version", "contract_version", "query", "embedding_dataset_id", "checkpoint_sha256", "ranking_method", "tie_break", "gallery_count", "requested_k", "effective_k", "results", "timings_ms")
    _required(document, fields, context)
    _no_unknown(document, set(fields), context)
    if document["schema_version"] != "2.0":
        raise SchemaValidationError("f4_retrieval_result.schema_version debe ser '2.0'")
    if document["contract_version"] != F4_RETRIEVAL_CONTRACT_VERSION or document["ranking_method"] != "exhaustive_cosine":
        raise SchemaValidationError("contrato o método de ranking F4 no soportado")
    if not isinstance(document["embedding_dataset_id"], str) or not re.fullmatch(r"f4-madrid-embeddings-sha256-[0-9a-f]{64}", document["embedding_dataset_id"]):
        raise SchemaValidationError("embedding_dataset_id de retrieval no válido")
    query = document["query"]
    if not isinstance(query, Mapping) or set(query) != {"query_id", "text", "language"}:
        raise SchemaValidationError("f4_retrieval_result.query no válido")
    for field in ("query_id", "text", "language"):
        _non_empty_string(query[field], f"f4_retrieval_result.query.{field}")
    if len(query["language"]) < 2:
        raise SchemaValidationError("f4_retrieval_result.query.language no válido")
    _positive_id(document["requested_k"], "f4_retrieval_result.requested_k")
    if document["checkpoint_sha256"] != "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d" or document["tie_break"] != "candidate_id_ascending" or not 1 <= document["gallery_count"] <= 1115:
        raise SchemaValidationError("identidad o política de ranking no válida")
    results = document["results"]
    expected_k = min(document["requested_k"], document["gallery_count"])
    if not isinstance(results, list) or len(results) != expected_k or document["effective_k"] != expected_k:
        raise SchemaValidationError("número de resultados no corresponde a K y galería")
    seen = set()
    for index, result in enumerate(results, start=1):
        if not isinstance(result, Mapping) or set(result) != {"rank", "candidate_id", "latitude", "longitude", "score"}:
            raise SchemaValidationError("resultado Top-K no válido")
        if result["rank"] != index:
            raise SchemaValidationError("ranks Top-K deben ser consecutivos desde 1")
        _non_empty_string(result["candidate_id"], "resultado.candidate_id")
        if result["candidate_id"] in seen:
            raise SchemaValidationError("candidate_id duplicado en Top-K")
        seen.add(result["candidate_id"])
        for field in ("latitude", "longitude", "score"):
            _finite_number(result[field], f"resultado.{field}")
        if not -90 <= result["latitude"] <= 90 or not -180 <= result["longitude"] <= 180 or not -1 <= result["score"] <= 1:
            raise SchemaValidationError("resultado Top-K fuera de rango")
        if index > 1:
            previous = results[index - 2]
            if result["score"] > previous["score"] or (result["score"] == previous["score"] and result["candidate_id"] < previous["candidate_id"]):
                raise SchemaValidationError("resultado Top-K no respeta score y desempate")
    timings = document["timings_ms"]
    if not isinstance(timings, Mapping) or set(timings) != {"text_encoding", "ranking", "total"}:
        raise SchemaValidationError("f4_retrieval_result.timings_ms no válido")
    for field, value in timings.items():
        _finite_number(value, f"f4_retrieval_result.timings_ms.{field}", minimum=0)
    if timings["total"] < timings["text_encoding"] + timings["ranking"]:
        raise SchemaValidationError("tiempo total menor que sus componentes")


def validate_document(document: Any, schema_name: str) -> None:
    if not isinstance(document, Mapping):
        raise SchemaValidationError("el documento raíz debe ser un objeto")
    validators = {
        "region_config": _validate_region_config,
        "llm_geo_query": _validate_llm,
        "evaluation_example": _validate_evaluation,
        "f4_query_dataset": _validate_f4_query_dataset,
        "f4_evaluation_result": _validate_f4_evaluation_result,
        "f4_ranking_set": _validate_f4_ranking_set,
        "f4_gallery_comparison": _validate_f4_gallery_comparison,
        "f4_linguistic_query_set": _validate_f4_linguistic_query_set,
        "f4_linguistic_robustness_result": _validate_f4_linguistic_robustness_result,
        "crosstext2loc_retrieval_request": _validate_crosstext2loc_retrieval_request,
        "crosstext2loc_retrieval_response": _validate_crosstext2loc_retrieval_response,
        "manifest": _validate_manifest,
        "osm_snapshot": _validate_osm_snapshot,
        "f3_osm_object": _validate_f3_osm_object,
        "f3_association": _validate_f3_association,
        "f3_relation_context": _validate_f3_relation_context,
        "f3_provenance": _validate_f3_provenance,
        "f4_visual_manifest": _validate_f4_visual_manifest,
        "f4_visual_selection": _validate_f4_visual_selection,
        "f4_assets_manifest": _validate_f4_assets_manifest,
        "f4_osm_source": _validate_f4_osm_source,
        "f4_renderer_provenance": _validate_f4_renderer_provenance,
        "f4_embedding_manifest": _validate_f4_embedding_manifest,
        "f4_retrieval_result": _validate_f4_retrieval_result,
        "experiment_parameters": _validate_experiment,
    }
    try:
        validator = validators[schema_name]
    except KeyError as exc:
        raise ValueError(f"schema no soportado por el validador básico: {schema_name}") from exc
    validator(document)
