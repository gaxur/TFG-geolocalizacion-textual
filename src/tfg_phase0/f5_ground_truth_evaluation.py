"""Contrato y evaluación F5.4 para Ground Truth madrileño y cinco variantes."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import PurePosixPath
import statistics
from typing import Any, Mapping, Sequence

from .f4_evaluation import assign_reference, haversine_m, percentile
from .f5_textual_variants import VARIANT_KINDS_V2


GT_PREFIX = "f5-madrid-ground-truth-sha256-"
EVALUATION_PREFIX = "f54-geographic-evaluation-sha256-"
GALLERY_IDS = ("madrid-25m", "madrid-50m")


class F54ValidationError(ValueError):
    pass


def ground_truth_dataset_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "dataset_version", "source_query_dataset", "catalogs", "collection_protocol", "observations")}
    return GT_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def geographic_evaluation_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "protocol", "inputs", "coverage", "metrics", "variant_comparisons", "per_query", "osm_future_baseline")}
    return EVALUATION_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def validate_ground_truth_dataset(document: Mapping[str, Any], source_dataset: Mapping[str, Any], catalogs: Mapping[str, Any], *, source_sha256: str) -> dict[str, Any]:
    from .validation import validate_document
    from .f4_evaluation import validate_query_dataset

    validate_document(document, "f5_ground_truth_dataset")
    if document["dataset_id"] != ground_truth_dataset_id(document):
        raise F54ValidationError("dataset_id F5.4 no corresponde al contenido")
    expected_source = {"dataset_id": source_dataset["dataset_id"], "sha256": source_sha256}
    if document["source_query_dataset"] != expected_source:
        raise F54ValidationError("sidecar F5.4 no corresponde al dataset F4.3")
    if set(catalogs) != set(GALLERY_IDS):
        raise F54ValidationError("F5.4 requiere catálogos 25 m y 50 m")
    validate_query_dataset(source_dataset, catalogs["madrid-50m"])
    for gallery_id, catalog in catalogs.items():
        expected = {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": len(catalog.candidates), "cell_size_m": catalog.cell_size_m}
        if document["catalogs"][gallery_id] != expected:
            raise F54ValidationError(f"catálogo F5.4 incompatible: {gallery_id}")
    source_queries = {query["query_id"]: query for query in source_dataset["queries"]}
    seen, locations = set(), {}
    status_counts, assignment_counts = Counter(), {gallery: Counter() for gallery in GALLERY_IDS}
    for observation in document["observations"]:
        query_id = observation["source_query_id"]
        if query_id in seen or query_id not in source_queries:
            raise F54ValidationError(f"observación F5.4 duplicada o sin fuente: {query_id}")
        seen.add(query_id)
        source = source_queries[query_id]
        if observation["description_profile"] == "complete_observation" and observation["comparison_parent_query_id"] is not None:
            raise F54ValidationError("una observación completa no debe declarar parent")
        if observation["description_profile"] == "controlled_simplification":
            parent_id = observation["comparison_parent_query_id"]
            if parent_id not in source_queries or source_queries[parent_id]["derivation_group_id"] != source["derivation_group_id"] or source_queries[parent_id]["partition"] != source["partition"]:
                raise F54ValidationError("simplificación controlada sin parent del mismo grupo y partición")
        for field in ("location_id", "derivation_group_id", "partition"):
            if observation[field] != source[field]:
                raise F54ValidationError(f"{field} F5.4 no corresponde a F4.3: {query_id}")
        location = observation["location_id"]
        if location is not None:
            previous = locations.setdefault(location, observation["partition"])
            if previous != observation["partition"]:
                raise F54ValidationError("location_id F5.4 cruza particiones")
        reference = observation["observer_reference"]
        status_counts[reference["status"]] += 1
        if reference["status"] == "validated":
            if source["reference"]["status"] != "validated" or source["validation_status"] != "validated":
                raise F54ValidationError("GT F5.4 validado sin referencia F4.3 validada")
            if source["provenance"]["source_type"] not in {"human_in_situ", "existing_dataset"} or source["provenance"]["independent_environment_observation"] is not True:
                raise F54ValidationError("GT F5.4 validado requiere observación real independiente")
            if source["description"]["language"] != "es" or source["description"]["contains_coordinates"] is not False:
                raise F54ValidationError("GT F5.4 requiere descripción española sin coordenadas")
            for field in ("latitude", "longitude", "crs", "capture_method", "reported_accuracy_m", "validation_method"):
                if reference[field] != source["reference"][field]:
                    raise F54ValidationError(f"GT F5.4 no coincide con F4.3: {field}")
            if not reference["evidence"] or any(row["review_status"] != "reviewed" for row in reference["evidence"]):
                raise F54ValidationError("GT validado requiere evidencia revisada")
            if observation["description_review_status"] != "reviewed":
                raise F54ValidationError("GT validado requiere descripción revisada")
            evidence_ids = {row["evidence_id"] for row in reference["evidence"]}
            if len(evidence_ids) != len(reference["evidence"]):
                raise F54ValidationError("evidence_id F5.4 duplicado")
            for evidence in reference["evidence"]:
                path = PurePosixPath(evidence["logical_reference"])
                if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                    raise F54ValidationError("referencia lógica de evidencia no válida")
                if len(evidence["sha256"]) != 64 or any(value not in "0123456789abcdef" for value in evidence["sha256"]):
                    raise F54ValidationError("hash de evidencia no válido")
                if not evidence["captured_at_utc"].endswith("Z"):
                    raise F54ValidationError("fecha de evidencia debe estar en UTC")
            _validate_orientation(observation["orientation"], evidence_ids)
            for gallery_id, catalog in catalogs.items():
                expected = assign_reference(reference["latitude"], reference["longitude"], catalog, reported_accuracy_m=reference["reported_accuracy_m"])
                if observation["catalog_assignments"][gallery_id] != expected:
                    raise F54ValidationError(f"asignación {gallery_id} no corresponde al GT")
                assignment_counts[gallery_id][expected["status"]] += 1
        else:
            if any(reference[field] is not None for field in ("latitude", "longitude", "crs", "capture_method", "reported_accuracy_m", "validation_method")) or reference["evidence"] or any(value is not None for value in observation["catalog_assignments"].values()):
                raise F54ValidationError("GT pendiente/rechazado contiene referencia o asignación")
            _validate_orientation(observation["orientation"], set())
    return {
        "dataset_id": document["dataset_id"], "observation_count": len(document["observations"]),
        "validated_count": status_counts["validated"], "pending_count": status_counts["pending"], "rejected_count": status_counts["rejected"],
        "assignment_status_counts": {gallery: dict(sorted(counts.items())) for gallery, counts in assignment_counts.items()},
        "geographic_evaluation_ready": status_counts["validated"] > 0,
    }


def _validate_orientation(orientation: Mapping[str, Any], evidence_ids: set[str]) -> None:
    status = orientation["status"]
    cardinal, bearing = orientation["cardinal"], orientation["bearing_degrees"]
    if status == "absent":
        if any(value is not None for value in (cardinal, bearing, orientation["uncertainty_degrees"])) or orientation["evidence_ids"]:
            raise F54ValidationError("orientación ausente contiene datos")
        return
    if (cardinal is None) == (bearing is None) or orientation["uncertainty_degrees"] is None:
        raise F54ValidationError("orientación debe declarar cardinal o bearing")
    if not orientation["evidence_ids"] or not set(orientation["evidence_ids"]) <= evidence_ids:
        raise F54ValidationError("orientación reportada/verificada sin evidencia enlazada")
    if status == "verified" and orientation["verification_method"] is None:
        raise F54ValidationError("orientación verificada sin método")


def evaluate_variant_rankings(gt_dataset: Mapping[str, Any], variant_sidecar: Mapping[str, Any], ranking_report: Mapping[str, Any], *, gt_sha256: str, variant_sha256: str, ranking_sha256: str, distance_thresholds_m: Sequence[float] = (25, 50, 100, 500)) -> dict[str, Any]:
    thresholds = _validate_thresholds(distance_thresholds_m)
    if variant_sidecar["contract_version"] != "f5-textual-variant-dataset-v2":
        raise F54ValidationError("evaluación F5.4 requiere sidecar textual v2")
    if variant_sidecar["source_query_dataset"] != gt_dataset["source_query_dataset"]:
        raise F54ValidationError("GT y variantes no referencian el mismo dataset F4.3")
    if ranking_report["sidecar"]["dataset_id"] != variant_sidecar["dataset_id"] or ranking_report["sidecar"]["sha256"] != variant_sha256:
        raise F54ValidationError("ranking F5.4 no corresponde al sidecar revisado")
    if ranking_report["retrieval"]["top_k"] != 10 or set(ranking_report["retrieval"]["gallery_ids"]) != set(GALLERY_IDS) or ranking_report["retrieval"]["scores_fused"] or ranking_report["retrieval"]["coordinates_fused"]:
        raise F54ValidationError("ranking F5.4 no es el baseline exhaustivo Top-10 de ambas galerías")
    observations = {row["source_query_id"]: row for row in gt_dataset["observations"]}
    variants_by_query = {row["source_query_id"]: {variant["kind"]: variant for variant in row["variants"]} for row in variant_sidecar["observations"]}
    ranking_rows = {(row["source_query_id"], row["kind"], row["gallery_id"]): row for row in ranking_report["rankings"]}
    if len(ranking_rows) != len(ranking_report["rankings"]):
        raise F54ValidationError("ranking F5.4 contiene filas duplicadas")
    per_query, observation_excluded, row_statuses = [], Counter(), Counter()
    aggregates: dict[tuple[str, str], list[dict[str, Any]]] = {(gallery, kind): [] for gallery in GALLERY_IDS for kind in VARIANT_KINDS_V2}
    for query_id, observation in sorted(observations.items()):
        reference = observation["observer_reference"]
        if reference["status"] != "validated":
            observation_excluded[f"reference_{reference['status']}"] += 1
            continue
        variants = variants_by_query.get(query_id)
        if variants is None or set(variants) != set(VARIANT_KINDS_V2):
            observation_excluded["five_variants_unavailable"] += 1
            continue
        for kind in VARIANT_KINDS_V2:
            variant = variants[kind]
            if variant["status"] != "reviewed" or variant["review_status"] != "reviewed":
                observation_excluded["variant_not_reviewed"] += 1
                continue
            for gallery in GALLERY_IDS:
                assignment = observation["catalog_assignments"][gallery]
                ranking = ranking_rows.get((query_id, kind, gallery))
                row = _evaluate_one(query_id, kind, gallery, reference, assignment, ranking, thresholds)
                row["description_profile"] = observation["description_profile"]
                row["comparison_parent_query_id"] = observation["comparison_parent_query_id"]
                per_query.append(row)
                row_statuses[row["status"]] += 1
                if row["status"] != "outside_region":
                    aggregates[(gallery, kind)].append(row)
    metrics = []
    for gallery in GALLERY_IDS:
        for kind in VARIANT_KINDS_V2:
            rows = aggregates[(gallery, kind)]
            metrics.append(_aggregate_rows(gallery, kind, rows, thresholds))
    comparisons = _variant_comparisons(per_query)
    document = {
        "schema_version": "1.0", "contract_version": "f54-geographic-evaluation-v1", "evaluation_id": EVALUATION_PREFIX + "0" * 64,
        "protocol": {"version": "f54-five-variant-exhaustive-v1", "gallery_ids": list(GALLERY_IDS), "variant_kinds": list(VARIANT_KINDS_V2), "ks": [1, 5, 10], "distance_thresholds_m": list(thresholds), "distance": "haversine_mean_earth_radius_6371008.8m", "ground_truth_ranking_use": False, "prefiltering": False, "reranking": False},
        "inputs": {"ground_truth_dataset_id": gt_dataset["dataset_id"], "ground_truth_sha256": gt_sha256, "variant_dataset_id": variant_sidecar["dataset_id"], "variant_sha256": variant_sha256, "ranking_report_id": ranking_report["report_id"], "ranking_sha256": ranking_sha256},
        "coverage": {"ground_truth_observations": len(observations), "validated_ground_truth": sum(row["observer_reference"]["status"] == "validated" for row in observations.values()), "observation_excluded_counts": dict(sorted(observation_excluded.items())), "variant_gallery_rows": len(per_query), "row_status_counts": dict(sorted(row_statuses.items())), "geographic_accuracy_available": any(item["rankings_observed"] > 0 for item in metrics)},
        "metrics": metrics, "variant_comparisons": comparisons, "per_query": per_query,
        "osm_future_baseline": {"configuration": "A_crosstext2loc_original", "prefilter_gt_coverage": None, "prefilter_gt_elimination_rate": None, "post_rerank_recall_at_k": None, "post_rerank_error_m": None, "qwen_latency_ms": None, "osm_latency_ms": None, "paired_baseline_comparison": None, "absence_of_osm_data_is_contradiction": False},
    }
    document["evaluation_id"] = geographic_evaluation_id(document)
    return document


def _evaluate_one(query_id: str, kind: str, gallery: str, reference: Mapping[str, Any], assignment: Mapping[str, Any], ranking: Mapping[str, Any] | None, thresholds: tuple[float, ...]) -> dict[str, Any]:
    base = {"source_query_id": query_id, "variant_kind": kind, "gallery_id": gallery, "assignment_status": assignment["status"], "ground_truth_candidate_id": assignment.get("candidate_id")}
    if assignment["status"] == "outside_region":
        return {**base, "status": "outside_region"}
    if ranking is None:
        return {**base, "status": "missing_ranking"}
    if ranking["top_k"] < 10 or len(ranking["results"]) < 10:
        raise F54ValidationError("F5.4 requiere rankings Top-10")
    ranked = ranking["results"]
    exact_rank = next((row["rank"] for row in ranked if row["candidate_id"] == assignment.get("candidate_id")), None) if assignment["status"] == "assigned" else None
    distances = [haversine_m(reference["latitude"], reference["longitude"], row["latitude"], row["longitude"]) for row in ranked]
    minimums = {str(k): min(distances[:k]) for k in (1, 5, 10)}
    return {**base, "status": "evaluated", "exact_rank": exact_rank, "top1_error_m": distances[0], "minimum_error_at_k_m": minimums, "geo_hits": {str(k): {str(value): minimums[str(k)] <= value for value in thresholds} for k in (1, 5, 10)}, "retrieval_ms": ranking["retrieval_ms"]}


def _aggregate_rows(gallery: str, kind: str, rows: Sequence[Mapping[str, Any]], thresholds: tuple[float, ...]) -> dict[str, Any]:
    exact_rows = [row for row in rows if row["assignment_status"] in {"assigned", "outside_catalog_coverage"}]
    evaluated = [row for row in rows if row["status"] == "evaluated"]
    errors = [row["top1_error_m"] for row in evaluated]
    return {
        "gallery_id": gallery, "variant_kind": kind, "effective_queries": len(rows), "rankings_observed": len(evaluated), "exact_denominator": len(exact_rows),
        "recall_at_k": {str(k): sum(row.get("exact_rank") is not None and row["exact_rank"] <= k for row in exact_rows) / len(exact_rows) if exact_rows else None for k in (1, 5, 10)},
        "top1_error_m": _summary(errors),
        "minimum_error_at_k_m": {str(k): _summary([row["minimum_error_at_k_m"][str(k)] for row in evaluated]) for k in (1, 5, 10)},
        "geo_recall_at_k": {str(k): {str(value): sum(row["geo_hits"][str(k)][str(value)] for row in evaluated) / len(rows) if rows else None for value in thresholds} for k in (1, 5, 10)},
        "retrieval_latency_ms": _summary([row["retrieval_ms"] for row in evaluated]),
    }


def _variant_comparisons(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(row["source_query_id"], row["gallery_id"], row["variant_kind"]): row for row in rows if row["status"] == "evaluated"}
    output = []
    query_gallery = sorted({(query_id, gallery) for query_id, gallery, kind in indexed if kind == "es_original"})
    for gallery in GALLERY_IDS:
        for kind in VARIANT_KINDS_V2:
            if kind == "es_original":
                continue
            deltas = []
            cases = []
            for query_id, row_gallery in query_gallery:
                if row_gallery != gallery:
                    continue
                anchor = indexed[(query_id, gallery, "es_original")]
                variant = indexed.get((query_id, gallery, kind))
                if variant is None:
                    continue
                delta = variant["top1_error_m"] - anchor["top1_error_m"]
                outcome = "improved" if delta < -1e-9 else ("worsened" if delta > 1e-9 else "tied")
                deltas.append(delta); cases.append({"source_query_id": query_id, "outcome": outcome, "top1_error_delta_m": delta})
            output.append({"gallery_id": gallery, "variant_kind": kind, "compared_queries": len(deltas), "improved": sum(row["outcome"] == "improved" for row in cases), "worsened": sum(row["outcome"] == "worsened" for row in cases), "tied": sum(row["outcome"] == "tied" for row in cases), "mean_top1_error_delta_m": statistics.fmean(deltas) if deltas else None, "cases": cases})
    return output


def _summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p90": None, "p95": None, "percentiles_available": False}
    enough = len(values) >= 20
    return {"count": len(values), "mean": statistics.fmean(values), "median": statistics.median(values), "p90": percentile(values, .9) if enough else None, "p95": percentile(values, .95) if enough else None, "percentiles_available": enough}


def _validate_thresholds(values: Sequence[float]) -> tuple[float, ...]:
    output = tuple(float(value) for value in values)
    if not output or any(not math.isfinite(value) or value <= 0 for value in output) or tuple(sorted(set(output))) != output:
        raise F54ValidationError("umbrales GeoRecall deben ser positivos, únicos y crecientes")
    return output


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
