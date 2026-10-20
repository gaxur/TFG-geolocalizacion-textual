"""Contrato sidecar F5.1 para topónimos, orientación y variantes textuales."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .f4_evaluation import validate_query_dataset
from .f4_validation import F4ValidationError


DATASET_PREFIX = "f5-madrid-textual-variants-sha256-"
VARIANT_KINDS_V1 = ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved")
VARIANT_KINDS_V2 = (*VARIANT_KINDS_V1, "en_cartographic")
VARIANT_KINDS = VARIANT_KINDS_V2
LANGUAGE_BY_KIND = {kind: "es" if kind.startswith("es_") else "en" for kind in VARIANT_KINDS_V2}


class F5ValidationError(ValueError):
    """El sidecar F5.1 no cumple el contrato o no corresponde a F4.3."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def textual_variant_dataset_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: document[key] for key in ("contract_version", "dataset_version", "source_query_dataset", "protocol", "comparison_protocol", "observations")}


def textual_variant_dataset_id(document: Mapping[str, Any]) -> str:
    return DATASET_PREFIX + hashlib.sha256(_canonical_bytes(textual_variant_dataset_identity(document))).hexdigest()


def source_query_input_sha256(query: Mapping[str, Any]) -> str:
    payload = {
        "query_id": query["query_id"],
        "partition": query["partition"],
        "location_id": query["location_id"],
        "derivation_group_id": query["derivation_group_id"],
        "text": query["description"]["text"],
        "language": query["description"]["language"],
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def source_dataset_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_textual_variant_dataset(
    document: Mapping[str, Any],
    source_dataset: Mapping[str, Any],
    *,
    source_sha256: str,
    catalog,
) -> dict[str, Any]:
    from .validation import SchemaValidationError, validate_document

    try:
        validate_document(document, "f5_textual_variant_dataset")
        validate_query_dataset(source_dataset, catalog)
    except (SchemaValidationError, F4ValidationError) as error:
        raise F5ValidationError("dataset F5.1 o fuente F4.3 inválidos") from error
    if document["dataset_id"] != textual_variant_dataset_id(document):
        raise F5ValidationError("dataset_id F5.1 no corresponde al contenido")
    if document["source_query_dataset"] != {"dataset_id": source_dataset["dataset_id"], "sha256": source_sha256}:
        raise F5ValidationError("referencia F5.1 al dataset F4.3 no corresponde")

    source_queries = {query["query_id"]: query for query in source_dataset["queries"]}
    seen_queries = set()
    variant_ids = set()
    generated_texts: dict[str, tuple[str, str]] = {}
    expected_kinds = variant_kinds_for_contract(document["contract_version"])
    if tuple(document["protocol"]["variant_kinds"]) != expected_kinds:
        raise F5ValidationError("variant_kinds no corresponde a la versión del contrato F5")
    variant_counts = {kind: {"pending": 0, "generated": 0, "reviewed": 0, "rejected": 0} for kind in expected_kinds}
    validated_references = 0
    proper_toponyms = 0
    reference_statuses = Counter()
    assignment_statuses = Counter()

    for observation in document["observations"]:
        query_id = observation["source_query_id"]
        if query_id in seen_queries:
            raise F5ValidationError(f"observación F5.1 duplicada: {query_id}")
        seen_queries.add(query_id)
        try:
            source = source_queries[query_id]
        except KeyError as error:
            raise F5ValidationError(f"consulta F5.1 ausente de F4.3: {query_id}") from error
        if observation["source_input_sha256"] != source_query_input_sha256(source):
            raise F5ValidationError(f"hash de input F4.3 no corresponde: {query_id}")
        for field in ("partition", "location_id", "derivation_group_id"):
            if observation[field] != source[field]:
                raise F5ValidationError(f"{field} F5.1 no corresponde a F4.3: {query_id}")
        if source["description"]["language"] != "es":
            raise F5ValidationError(f"F5.1 requiere una observación original española: {query_id}")
        reference_status = source["reference"]["status"]
        reference_statuses[reference_status] += 1
        validated_references += reference_status == "validated"
        assignment = source["reference"]["catalog_assignment"]
        assignment_statuses[assignment["status"] if assignment is not None else "unavailable"] += 1
        _validate_toponyms(observation, source)
        proper_names = {item["mention"] for item in observation["toponyms"] if item["name_kind"] == "proper_name" and item["review_status"] == "reviewed"}
        proper_toponyms += len(proper_names)
        _validate_orientation(observation["orientation"])
        variants = observation["variants"]
        if tuple(variant["kind"] for variant in variants) != expected_kinds:
            raise F5ValidationError(f"orden o tipos de variantes F5.1 inválidos: {query_id}")
        for variant in variants:
            _validate_variant(variant, source, proper_names)
            variant_counts[variant["kind"]][variant["status"]] += 1
            if variant["variant_id"] is not None:
                if variant["variant_id"] in variant_ids:
                    raise F5ValidationError("variant_id F5.1 duplicado")
                variant_ids.add(variant["variant_id"])
            if variant["text"] is not None:
                normalized = " ".join(variant["text"].casefold().split())
                previous = generated_texts.setdefault(normalized, (query_id, source["partition"]))
                if previous[0] != query_id and previous[1] != source["partition"]:
                    raise F5ValidationError("variante textual duplicada cruza particiones")

    source_partitions = {query_id: source_queries[query_id]["partition"] for query_id in seen_queries}
    for query_id, partition in source_partitions.items():
        source = source_queries[query_id]
        for other_id, other_partition in source_partitions.items():
            if query_id >= other_id or partition == other_partition:
                continue
            if source["location_id"] is not None and source["location_id"] == source_queries[other_id]["location_id"]:
                raise F5ValidationError("location_id F5.1 cruza particiones")
            if source["derivation_group_id"] == source_queries[other_id]["derivation_group_id"]:
                raise F5ValidationError("derivation_group_id F5.1 cruza particiones")

    complete = sum(all(variant["status"] == "reviewed" for variant in observation["variants"]) for observation in document["observations"])
    comparison_ready = sum(len([variant for variant in observation["variants"] if variant["status"] == "reviewed"]) >= 2 for observation in document["observations"])
    return {
        "dataset_id": document["dataset_id"],
        "source_query_dataset_id": source_dataset["dataset_id"],
        "observation_count": len(document["observations"]),
        "development_count": sum(observation["partition"] == "development" for observation in document["observations"]),
        "evaluation_count": sum(observation["partition"] == "evaluation" for observation in document["observations"]),
        "validated_ground_truth_count": validated_references,
        "proper_toponym_count": proper_toponyms,
        "complete_observation_count": complete,
        "paired_comparison_ready_count": comparison_ready,
        "reference_status_counts": dict(sorted(reference_statuses.items())),
        "catalog_assignment_status_counts": dict(sorted(assignment_statuses.items())),
        "variant_status_counts": variant_counts,
        "precision_metrics_available": validated_references > 0,
        "osm_preselection_status": document["protocol"]["osm_preselection_status"],
    }


def variant_kinds_for_contract(contract_version: str) -> tuple[str, ...]:
    if contract_version == "f5-textual-variant-dataset-v1":
        return VARIANT_KINDS_V1
    if contract_version == "f5-textual-variant-dataset-v2":
        return VARIANT_KINDS_V2
    raise F5ValidationError(f"versión de contrato F5 no soportada: {contract_version}")


def paired_variant_plan(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Devuelve inputs emparejados revisados; no ejecuta ni fusiona rankings."""
    plan = []
    for observation in document["observations"]:
        reviewed = [variant for variant in observation["variants"] if variant["status"] == "reviewed"]
        for left_index, left in enumerate(reviewed):
            for right in reviewed[left_index + 1:]:
                plan.append({
                    "source_query_id": observation["source_query_id"],
                    "partition": observation["partition"],
                    "left_variant_id": left["variant_id"],
                    "left_kind": left["kind"],
                    "right_variant_id": right["variant_id"],
                    "right_kind": right["kind"],
                })
    return plan


def _validate_toponyms(observation: Mapping[str, Any], source: Mapping[str, Any]) -> None:
    text = source["description"]["text"]
    spans = set()
    for item in observation["toponyms"]:
        start, end = item["span"]["start"], item["span"]["end"]
        if start >= end or end > len(text) or text[start:end] != item["mention"]:
            raise F5ValidationError(f"span de topónimo no corresponde al original: {observation['source_query_id']}")
        span = (start, end)
        if span in spans or any(start < other_end and other_start < end for other_start, other_end in spans):
            raise F5ValidationError("spans de topónimos duplicados o solapados")
        spans.add(span)
        if len(item["aliases"]) != len(set(alias.casefold() for alias in item["aliases"])):
            raise F5ValidationError("aliases de topónimo duplicados")


def _validate_orientation(orientation: Mapping[str, Any]) -> None:
    status = orientation["status"]
    cardinal, bearing = orientation["cardinal"], orientation["bearing_degrees"]
    if bearing is not None and (not math.isfinite(bearing) or not 0 <= bearing < 360):
        raise F5ValidationError("rumbo no válido")
    if status == "absent":
        nullable = (cardinal, bearing, orientation["bearing_convention"], orientation["method"], orientation["uncertainty_degrees"], orientation["provenance"])
        if any(value is not None for value in nullable) or orientation["verification_status"] != "not_applicable":
            raise F5ValidationError("orientación ausente contiene valores inventados")
    else:
        if (cardinal is None) == (bearing is None):
            raise F5ValidationError("orientación debe declarar cardinal o rumbo, no ambos")
        if bearing is not None and orientation["bearing_convention"] != "degrees_clockwise_from_true_north":
            raise F5ValidationError("rumbo sin convención")
        if bearing is None and orientation["bearing_convention"] is not None:
            raise F5ValidationError("convención de rumbo sin rumbo")
        if not orientation["method"] or not orientation["provenance"] or orientation["uncertainty_degrees"] is None:
            raise F5ValidationError("orientación declarada sin método, procedencia o incertidumbre")
        if status == "verified" and orientation["verification_status"] != "verified":
            raise F5ValidationError("orientación verificada con estado incompatible")
        if status == "reported" and orientation["verification_status"] not in {"pending", "rejected"}:
            raise F5ValidationError("orientación reportada con estado incompatible")


def _validate_variant(variant: Mapping[str, Any], source: Mapping[str, Any], proper_names: set[str]) -> None:
    kind, status = variant["kind"], variant["status"]
    if variant["language"] != LANGUAGE_BY_KIND[kind]:
        raise F5ValidationError(f"idioma incompatible con variante {kind}")
    pending_fields = (variant["variant_id"], variant["text"], variant["generation"]["tool_or_model"], variant["generation"]["version"], variant["generation"]["configuration_or_prompt"], variant["generation"]["transformation_time_ms"])
    if status == "pending":
        if kind == "es_original":
            raise F5ValidationError("es_original debe materializar la observación F4.3")
        if any(value is not None for value in pending_fields) or variant["generation"]["method"] != "pending" or variant["review_status"] != "pending":
            raise F5ValidationError("variante pendiente contiene generación fabricada")
        if any(variant[field] for field in ("transformations", "preserved_elements", "removed_elements", "modified_elements", "protected_toponyms")):
            raise F5ValidationError("variante pendiente contiene anotaciones")
        return
    if variant["variant_id"] is None or variant["text"] is None or variant["generation"]["method"] == "pending":
        raise F5ValidationError("variante materializada incompleta")
    if status == "reviewed" and variant["review_status"] != "reviewed":
        raise F5ValidationError("variante revisada con review_status incompatible")
    if status == "generated" and variant["review_status"] != "pending":
        raise F5ValidationError("variante generada con review_status incompatible")
    if status == "rejected" and variant["review_status"] != "rejected":
        raise F5ValidationError("variante rechazada con review_status incompatible")
    if kind == "es_original":
        if source["description"]["language"] != "es" or variant["text"] != source["description"]["text"] or variant["generation"]["method"] != "original":
            raise F5ValidationError("es_original no conserva la descripción española F4.3")
        if variant["transformations"] != ["preserve_original"] or variant["removed_elements"] or variant["modified_elements"]:
            raise F5ValidationError("es_original declara transformaciones")
    elif kind == "es_cartographic" and variant["generation"]["method"] not in {"manual_cartographic_rewrite", "model_assisted_cartographic_rewrite"}:
        raise F5ValidationError("es_cartographic requiere un método de reescritura declarado")
    elif kind in {"en_conventional", "en_toponym_preserved", "en_cartographic"} and variant["generation"]["method"] not in {"manual_translation", "automatic_translation", "model_assisted_translation"}:
        raise F5ValidationError("variante inglesa sin método de traducción")
    if kind in {"en_toponym_preserved", "en_cartographic"}:
        if set(variant["protected_toponyms"]) != proper_names:
            raise F5ValidationError("en_toponym_preserved no protege todos los topónimos propios revisados")
        if not proper_names <= set(variant["text"].split()) and any(name not in variant["text"] for name in proper_names):
            raise F5ValidationError("topónimo protegido no aparece literalmente en la traducción")
    elif variant["protected_toponyms"]:
        raise F5ValidationError("protected_toponyms solo se admite en variantes inglesas protegidas")
