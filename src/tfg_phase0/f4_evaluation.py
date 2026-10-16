"""Dataset, asignación geográfica y métricas independientes para F4.3."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import unicodedata
from typing import Any, Mapping, Sequence

from .crs import wgs84_to_epsg25830
from .f3_inputs import CatalogInput
from .f4_validation import F4ValidationError


QUERY_DATASET_PREFIX = "f4-madrid-queries-sha256-"
EVALUATION_PREFIX = "f4-madrid-evaluation-sha256-"
RANKING_SET_PREFIX = "f4-madrid-rankings-sha256-"
COMPARISON_PREFIX = "f4-madrid-gallery-comparison-sha256-"
EARTH_MEAN_RADIUS_M = 6_371_008.8
BOUNDARY_TOLERANCE_M = 1e-6


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def query_dataset_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: document[key] for key in ("contract_version", "dataset_version", "region", "catalog", "partition_policy", "queries")}


def query_dataset_id(document: Mapping[str, Any]) -> str:
    return QUERY_DATASET_PREFIX + hashlib.sha256(_canonical_bytes(query_dataset_identity(document))).hexdigest()


def evaluation_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: document[key] for key in ("contract_version", "protocol", "inputs", "coverage", "metrics", "per_query")}


def evaluation_id(document: Mapping[str, Any]) -> str:
    return EVALUATION_PREFIX + hashlib.sha256(_canonical_bytes(evaluation_identity(document))).hexdigest()


def query_inputs_sha256(document: Mapping[str, Any], partition: str) -> str:
    inputs = [
        {"query_id": query["query_id"], "partition": query["partition"], "text": query["description"]["text"], "language": query["description"]["language"]}
        for query in document["queries"] if query["partition"] == partition
    ]
    return hashlib.sha256(_canonical_bytes(inputs)).hexdigest()


def ranking_set_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "query_inputs_sha256", "embedding_dataset_id", "checkpoint_sha256", "partition", "frozen_before_reference_access", "rankings")}
    return RANKING_SET_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def gallery_comparison_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "query_inputs_sha256", "checkpoint_sha256", "galleries", "queries", "empirical_metrics_available", "limitations")}
    return COMPARISON_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def normalize_description(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    value = " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))
    return " ".join(value.split())


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(normalize_description(left).split())
    right_tokens = set(normalize_description(right).split())
    if not left_tokens and not right_tokens:
        return 1.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def validate_query_dataset(document: Mapping[str, Any], catalog: CatalogInput) -> dict[str, Any]:
    from .validation import SchemaValidationError, validate_document

    try:
        validate_document(document, "f4_query_dataset")
    except SchemaValidationError as error:
        raise F4ValidationError("dataset de consultas F4.3 inválido") from error
    if document["dataset_id"] != query_dataset_id(document):
        raise F4ValidationError("dataset_id de consultas no corresponde al contenido")
    expected_catalog = {
        "manifest_id": catalog.manifest_id,
        "manifest_sha256": catalog.sha256,
        "candidate_count": len(catalog.candidates),
        "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1",
    }
    if document["catalog"] != expected_catalog:
        raise F4ValidationError("dataset de consultas referencia otro catálogo F1")
    if document["region"] != {"region_id": catalog.region_id, "bbox_wgs84": dict(catalog.region_bbox_wgs84)}:
        raise F4ValidationError("región del dataset de consultas no corresponde a F1")
    queries = document["queries"]
    ids = [query["query_id"] for query in queries]
    if len(ids) != len(set(ids)):
        raise F4ValidationError("query_id duplicado")
    normalized: dict[str, str] = {}
    group_partitions: dict[tuple[str, str], str] = {}
    suspicious = []
    threshold = document["partition_policy"]["near_duplicate_token_jaccard_threshold"]
    for query in queries:
        if query["partition"] == "evaluation" and query["location_id"] is None:
            raise F4ValidationError("toda consulta evaluation debe declarar location_id")
        text = query["description"]["text"]
        normalized_text = normalize_description(text)
        if not normalized_text:
            raise F4ValidationError("descripción vacía tras normalización")
        previous = normalized.get(normalized_text)
        if previous is not None:
            raise F4ValidationError(f"descripción duplicada: {previous} y {query['query_id']}")
        normalized[normalized_text] = query["query_id"]
        for group_name in ("location_id", "derivation_group_id"):
            value = query[group_name]
            if value is None:
                continue
            key = (group_name, value)
            previous_partition = group_partitions.setdefault(key, query["partition"])
            if previous_partition != query["partition"]:
                raise F4ValidationError(f"{group_name} cruza particiones: {value}")
        _validate_reference_state(query)
        reference = query["reference"]
        if reference["status"] == "validated":
            expected_assignment = assign_reference(
                reference["latitude"], reference["longitude"], catalog,
                reported_accuracy_m=reference["reported_accuracy_m"],
            )
            if reference["catalog_assignment"] != expected_assignment:
                raise F4ValidationError(f"asignación F1 no corresponde a la referencia: {query['query_id']}")
    for index, left in enumerate(queries):
        for right in queries[index + 1:]:
            if left["partition"] == right["partition"]:
                continue
            similarity = token_jaccard(left["description"]["text"], right["description"]["text"])
            if similarity >= threshold:
                suspicious.append({"left": left["query_id"], "right": right["query_id"], "token_jaccard": similarity})
    if suspicious:
        raise F4ValidationError("posibles paráfrasis cruzan development/evaluation")
    return {"exact_duplicates": 0, "cross_partition_near_duplicates": suspicious, "checked_pairs": len(queries) * (len(queries) - 1) // 2}


def _validate_reference_state(query: Mapping[str, Any]) -> None:
    reference = query["reference"]
    coordinates = (reference["latitude"], reference["longitude"], reference["crs"])
    if reference["status"] == "validated":
        if query["validation_status"] != "validated" or query["location_id"] is None or any(value is None for value in coordinates):
            raise F4ValidationError("referencia validada incompleta")
        if not reference["capture_method"] or not reference["validation_method"] or reference["reported_accuracy_m"] is None or reference["catalog_assignment"] is None:
            raise F4ValidationError("referencia validada sin método documentado")
        if query["ambiguity"]["status"] == "unreviewed":
            raise F4ValidationError("consulta validada sin revisión de ambigüedad")
    elif reference["catalog_assignment"] is not None:
        raise F4ValidationError("referencia no validada no puede declarar asignación F1")
    elif any(value is not None for value in coordinates):
        raise F4ValidationError("referencia pendiente o rechazada no debe declarar coordenadas parciales")
    elif any(reference[field] is not None for field in ("capture_method", "reported_accuracy_m", "validation_method")):
        raise F4ValidationError("referencia no validada no debe declarar metadatos de captura")
    elif query["validation_status"] != reference["status"]:
        raise F4ValidationError("validation_status no corresponde al estado de referencia")


def assign_reference(
    latitude: float,
    longitude: float,
    catalog: CatalogInput,
    *,
    reported_accuracy_m: float | None = None,
) -> dict[str, Any]:
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise F4ValidationError("coordenada de referencia no válida")
    bbox = catalog.region_bbox_wgs84
    if not (bbox["south"] <= latitude <= bbox["north"] and bbox["west"] <= longitude <= bbox["east"]):
        return {"status": "outside_region", "candidate_id": None, "center_distance_m": None, "distance_to_cell_boundary_m": None, "boundary_ambiguous": False}
    x, y = wgs84_to_epsg25830(latitude, longitude)
    half = catalog.cell_size_m / 2
    interior = []
    boundary = []
    for candidate in catalog.candidates:
        dx = abs(x - candidate.center_easting_m)
        dy = abs(y - candidate.center_northing_m)
        if dx < half - BOUNDARY_TOLERANCE_M and dy < half - BOUNDARY_TOLERANCE_M:
            interior.append(candidate)
        elif dx <= half + BOUNDARY_TOLERANCE_M and dy <= half + BOUNDARY_TOLERANCE_M:
            boundary.append(candidate)
    if boundary or len(interior) > 1:
        ids = sorted(candidate.candidate_id for candidate in boundary + interior)
        return {"status": "boundary_ambiguous", "candidate_id": None, "candidate_ids": ids, "center_distance_m": None, "distance_to_cell_boundary_m": 0.0, "boundary_ambiguous": True}
    if not interior:
        return {"status": "outside_catalog_coverage", "candidate_id": None, "center_distance_m": None, "distance_to_cell_boundary_m": None, "boundary_ambiguous": False}
    candidate = interior[0]
    dx = abs(x - candidate.center_easting_m)
    dy = abs(y - candidate.center_northing_m)
    distance_to_boundary = min(half - dx, half - dy)
    if reported_accuracy_m is not None:
        if not math.isfinite(reported_accuracy_m) or reported_accuracy_m < 0:
            raise F4ValidationError("precisión reportada no válida")
        if reported_accuracy_m >= distance_to_boundary:
            return {
                "status": "accuracy_insufficient",
                "candidate_id": None,
                "candidate_ids": [candidate.candidate_id],
                "center_distance_m": round(math.hypot(dx, dy), 6),
                "distance_to_cell_boundary_m": round(distance_to_boundary, 6),
                "boundary_ambiguous": True,
            }
    return {
        "status": "assigned",
        "candidate_id": candidate.candidate_id,
        "center_distance_m": round(math.hypot(dx, dy), 6),
        "distance_to_cell_boundary_m": round(distance_to_boundary, 6),
        "boundary_ambiguous": False,
    }


def haversine_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    values = (latitude_a, longitude_a, latitude_b, longitude_b)
    if not all(math.isfinite(value) for value in values):
        raise F4ValidationError("coordenadas no finitas")
    if not (-90 <= latitude_a <= 90 and -90 <= latitude_b <= 90 and -180 <= longitude_a <= 180 and -180 <= longitude_b <= 180):
        raise F4ValidationError("coordenadas fuera de rango")
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    hav = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return 2 * EARTH_MEAN_RADIUS_M * math.asin(min(1.0, math.sqrt(hav)))


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise F4ValidationError("percentil sin valores")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def evaluate_rankings(
    dataset: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    catalog: CatalogInput,
    *,
    partition: str,
    dataset_sha256: str,
    visual_dataset_id: str,
    visual_manifest_sha256: str,
    embedding_dataset_id: str,
    embedding_manifest_sha256: str,
    checkpoint_sha256: str,
    ranking_artifacts: Sequence[Mapping[str, Any]],
    ranking_set_id_value: str,
    ranking_set_sha256: str,
    rankings_frozen_before_reference_access: bool,
) -> dict[str, Any]:
    if partition == "evaluation" and dataset["partition_policy"]["evaluation_frozen"] is not True:
        raise F4ValidationError("la partición evaluation debe estar congelada antes de evaluarse")
    queries = [query for query in dataset["queries"] if query["partition"] == partition]
    rows = []
    exact_hits = {1: 0, 5: 0, 10: 0}
    top1_errors = []
    min_errors = {1: [], 5: [], 10: []}
    thresholds = (25, 50, 100, 500)
    geohits = {(k, threshold): 0 for k in (1, 5, 10) for threshold in thresholds}
    exact_denominator = 0
    geographic_denominator = 0
    ranking_hashes = {item["query_id"]: item for item in ranking_artifacts}
    if len(ranking_hashes) != len(ranking_artifacts):
        raise F4ValidationError("artefacto de ranking duplicado")
    for query in queries:
        reference = query["reference"]
        if reference["status"] != "validated" or query["validation_status"] != "validated":
            rows.append({"query_id": query["query_id"], "status": "reference_unavailable"})
            continue
        assignment = assign_reference(
            reference["latitude"], reference["longitude"], catalog,
            reported_accuracy_m=reference["reported_accuracy_m"],
        )
        if assignment["status"] == "outside_region":
            rows.append({"query_id": query["query_id"], "status": "outside_region"})
            continue
        geographic_denominator += 1
        exact_eligible = assignment["status"] in {"assigned", "outside_catalog_coverage"}
        exact_denominator += exact_eligible
        stored = reference["catalog_assignment"]
        if stored != assignment:
            raise F4ValidationError(f"asignación F1 almacenada inconsistente: {query['query_id']}")
        result = results.get(query["query_id"])
        if result is None:
            rows.append({"query_id": query["query_id"], "status": "missing_ranking", "assignment_status": assignment["status"], "ground_truth_candidate_id": assignment.get("candidate_id")})
            continue
        ranking_artifact = ranking_hashes.get(query["query_id"])
        if ranking_artifact is None:
            raise F4ValidationError(f"falta hash del ranking: {query['query_id']}")
        if result["query"] != {"query_id": query["query_id"], "text": query["description"]["text"], "language": query["description"]["language"]}:
            raise F4ValidationError(f"ranking no corresponde a la consulta: {query['query_id']}")
        if result["effective_k"] < 10 or len(result["results"]) < 10:
            raise F4ValidationError(f"evaluación formal requiere Top-10: {query['query_id']}")
        ranked = result["results"]
        rank = next((row["rank"] for row in ranked if row["candidate_id"] == assignment.get("candidate_id")), None) if assignment["status"] == "assigned" else None
        distances = [haversine_m(reference["latitude"], reference["longitude"], row["latitude"], row["longitude"]) for row in ranked]
        top1 = distances[0]
        top1_errors.append(top1)
        minimums = {}
        for k in (1, 5, 10):
            if exact_eligible:
                exact_hits[k] += rank is not None and rank <= k
            available = distances[:min(k, len(distances))]
            minimum = min(available) if available else None
            minimums[str(k)] = minimum
            if minimum is not None:
                min_errors[k].append(minimum)
                for threshold in thresholds:
                    geohits[(k, threshold)] += minimum <= threshold
        rows.append({"query_id": query["query_id"], "status": "evaluated", "assignment_status": assignment["status"], "ground_truth_candidate_id": assignment.get("candidate_id"), "exact_rank": rank, "top1_error_m": top1, "min_distance_at_k_m": minimums, "ranking_sha256": ranking_artifact["sha256"]})
    exact_available = exact_denominator > 0
    geographic_available = geographic_denominator > 0
    metrics = {
        "exact_available": exact_available,
        "geographic_available": geographic_available,
        "exact_recall_at_k": {str(k): exact_hits[k] / exact_denominator if exact_available else None for k in (1, 5, 10)},
        "top1_error_m_conditional_on_ranking": _distance_summary(top1_errors, geographic_denominator),
        "minimum_error_at_k_m_conditional_on_ranking": {str(k): _distance_summary(min_errors[k], geographic_denominator) for k in (1, 5, 10)},
        "geo_recall_at_k": {str(k): {str(threshold): geohits[(k, threshold)] / geographic_denominator if geographic_available else None for threshold in thresholds} for k in (1, 5, 10)},
    }
    document = {
        "schema_version": "1.0", "contract_version": "f4-evaluation-result-v1",
        "evaluation_id": EVALUATION_PREFIX + "0" * 64,
        "protocol": {"version": "f4-madrid-exhaustive-evaluation-v1", "partition": partition, "exact_match": "assigned_f1_candidate_id_with_catalog_gaps_as_failures", "distance": "haversine_mean_earth_radius_6371008.8m", "distance_summary_scope": "conditional_on_ranking", "percentile_method": "linear_n_minus_1", "percentile_minimum_sample": 20, "ks": [1, 5, 10], "distance_thresholds_m": list(thresholds), "ground_truth_ranking_use": False, "ranking_validation": "producer_contract_and_artifact_sha256"},
        "inputs": {"query_dataset_id": dataset["dataset_id"], "query_dataset_sha256": dataset_sha256, "catalog_manifest_id": catalog.manifest_id, "catalog_manifest_sha256": catalog.sha256, "visual_dataset_id": visual_dataset_id, "visual_manifest_sha256": visual_manifest_sha256, "embedding_dataset_id": embedding_dataset_id, "embedding_manifest_sha256": embedding_manifest_sha256, "checkpoint_sha256": checkpoint_sha256, "ranking_set_id": ranking_set_id_value, "ranking_set_sha256": ranking_set_sha256, "rankings_frozen_before_reference_access": rankings_frozen_before_reference_access, "ranking_artifacts": sorted((dict(item) for item in ranking_artifacts), key=lambda item: item["query_id"])},
        "coverage": {"partition_queries": len(queries), "validated_references": sum(query["reference"]["status"] == "validated" for query in queries), "exact_denominator": exact_denominator, "geographic_denominator": geographic_denominator, "rankings_found": sum(query["query_id"] in results for query in queries), "rankings_top10_ready": sum(result.get("effective_k", 0) >= 10 for result in results.values()), "exact_metrics_available": exact_available, "geographic_metrics_available": geographic_available},
        "metrics": metrics, "per_query": sorted(rows, key=lambda row: row["query_id"]),
    }
    document["evaluation_id"] = evaluation_id(document)
    return document


def _distance_summary(values: Sequence[float], eligible_count: int) -> dict[str, Any]:
    if not values:
        return {"eligible_count": eligible_count, "observed_count": 0, "missing_count": eligible_count, "mean": None, "median": None, "p90": None, "p95": None, "percentiles_available": False}
    sufficient = len(values) >= 20
    return {"eligible_count": eligible_count, "observed_count": len(values), "missing_count": eligible_count - len(values), "mean": statistics.fmean(values), "median": statistics.median(values), "p90": percentile(values, 0.9) if sufficient else None, "p95": percentile(values, 0.95) if sufficient else None, "percentiles_available": sufficient}


def validate_evaluation_result(document: Mapping[str, Any]) -> None:
    """Valida contrato, identidad y coherencia entre filas y agregados."""
    from .validation import SchemaValidationError, validate_document

    try:
        validate_document(document, "f4_evaluation_result")
    except SchemaValidationError as error:
        raise F4ValidationError("resultado de evaluación F4.3 inválido") from error
    coverage = document["coverage"]
    metrics = document["metrics"]
    if metrics["exact_available"] != (coverage["exact_denominator"] > 0):
        raise F4ValidationError("disponibilidad de Recall exacto inconsistente")
    if metrics["geographic_available"] != (coverage["geographic_denominator"] > 0):
        raise F4ValidationError("disponibilidad de métricas geográficas inconsistente")
    if not metrics["exact_available"] and any(value is not None for value in metrics["exact_recall_at_k"].values()):
        raise F4ValidationError("Recall exacto debe ser null sin denominador")
    if not metrics["geographic_available"] and any(value is not None for values in metrics["geo_recall_at_k"].values() for value in values.values()):
        raise F4ValidationError("GeoRecall debe ser null sin denominador")
    summaries = [metrics["top1_error_m_conditional_on_ranking"], *metrics["minimum_error_at_k_m_conditional_on_ranking"].values()]
    if any(summary["eligible_count"] != coverage["geographic_denominator"] for summary in summaries):
        raise F4ValidationError("denominador de resúmenes geográficos inconsistente")
    if document["evaluation_id"] != evaluation_id(document):
        raise F4ValidationError("evaluation_id no corresponde al contenido")
    exact_rows = [row for row in document["per_query"] if row.get("assignment_status") in {"assigned", "outside_catalog_coverage"}]
    geographic_rows = [row for row in document["per_query"] if row.get("assignment_status") in {"assigned", "outside_catalog_coverage", "boundary_ambiguous", "accuracy_insufficient"}]
    if len(exact_rows) != coverage["exact_denominator"] or len(geographic_rows) != coverage["geographic_denominator"]:
        raise F4ValidationError("denominadores no corresponden a per_query")
    for k in (1, 5, 10):
        expected_exact = sum(row.get("exact_rank") is not None and row["exact_rank"] <= k for row in exact_rows)
        expected_recall = expected_exact / len(exact_rows) if exact_rows else None
        if metrics["exact_recall_at_k"][str(k)] != expected_recall:
            raise F4ValidationError("Recall exacto no corresponde a per_query")
        observed = [row["min_distance_at_k_m"][str(k)] for row in geographic_rows if row["status"] == "evaluated"]
        if metrics["minimum_error_at_k_m_conditional_on_ranking"][str(k)] != _distance_summary(observed, len(geographic_rows)):
            raise F4ValidationError("resumen mínimo de distancia no corresponde a per_query")
        for threshold in (25, 50, 100, 500):
            expected_geohit = sum(value <= threshold for value in observed) / len(geographic_rows) if geographic_rows else None
            if metrics["geo_recall_at_k"][str(k)][str(threshold)] != expected_geohit:
                raise F4ValidationError("GeoRecall no corresponde a per_query")
    observed_top1 = [row["top1_error_m"] for row in geographic_rows if row["status"] == "evaluated"]
    if metrics["top1_error_m_conditional_on_ranking"] != _distance_summary(observed_top1, len(geographic_rows)):
        raise F4ValidationError("resumen Top-1 no corresponde a per_query")
