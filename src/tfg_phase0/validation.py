"""Validaciones básicas de los contratos de Fase 0.

No pretende sustituir a un validador JSON Schema completo. Comprueba los
campos y restricciones necesarias para los contratos iniciales y mantiene el
núcleo libre de dependencias externas.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
import urllib.parse
from typing import Any

from .f3_contracts import F3_GEOMETRY_REASONS, F3_INVALID_REASONS, F3_NOT_ASSOCIABLE_REASONS


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
            "shapely_version", "geos_version", "platform_system", "platform_machine",
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
    config_fields = {"logical_path", "schema_version", "file_sha256", "canonical_sha256"}
    if not isinstance(config, Mapping):
        raise SchemaValidationError("f3_provenance.inputs.config debe ser un objeto")
    _required(config, tuple(config_fields), "f3_provenance.inputs.config")
    _no_unknown(config, config_fields, "f3_provenance.inputs.config")
    _logical_path(config["logical_path"], "f3_provenance.inputs.config.logical_path")
    if config["schema_version"] != "1.0":
        raise SchemaValidationError("inputs.config.schema_version no válido")
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
    for field in ("python_implementation", "python_version", "shapely_version", "geos_version", "platform_system", "platform_machine"):
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


def validate_document(document: Any, schema_name: str) -> None:
    if not isinstance(document, Mapping):
        raise SchemaValidationError("el documento raíz debe ser un objeto")
    validators = {
        "region_config": _validate_region_config,
        "llm_geo_query": _validate_llm,
        "evaluation_example": _validate_evaluation,
        "manifest": _validate_manifest,
        "osm_snapshot": _validate_osm_snapshot,
        "f3_osm_object": _validate_f3_osm_object,
        "f3_association": _validate_f3_association,
        "f3_relation_context": _validate_f3_relation_context,
        "f3_provenance": _validate_f3_provenance,
        "experiment_parameters": _validate_experiment,
    }
    try:
        validator = validators[schema_name]
    except KeyError as exc:
        raise ValueError(f"schema no soportado por el validador básico: {schema_name}") from exc
    validator(document)
