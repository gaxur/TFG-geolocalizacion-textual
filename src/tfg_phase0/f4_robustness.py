"""Contratos y métricas descriptivas de robustez lingüística F4.5."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .f4_evaluation import haversine_m
from .f4_validation import F4ValidationError


QUERY_SET_PREFIX = "f4-madrid-linguistic-queries-sha256-"
RESULT_PREFIX = "f4-madrid-linguistic-robustness-sha256-"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def linguistic_query_set_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "protocol_version", "partition", "provenance", "groups")}
    return QUERY_SET_PREFIX + hashlib.sha256(_canonical(identity)).hexdigest()


def robustness_result_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "query_set_id", "query_set_sha256", "gallery", "checkpoint_sha256", "ranking_set_id", "ranking_set_sha256", "top_k", "comparisons", "aggregates", "geographic_accuracy_available", "limitations")}
    return RESULT_PREFIX + hashlib.sha256(_canonical(identity)).hexdigest()


def linguistic_query_inputs(document: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"query_id": variant["query_id"], "partition": document["partition"], "text": variant["text"], "language": variant["language"]}
        for group in document["groups"] for variant in group["variants"]
    ]


def linguistic_query_inputs_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(linguistic_query_inputs(document))).hexdigest()


def validate_linguistic_query_set(document: Mapping[str, Any]) -> None:
    from .validation import SchemaValidationError, validate_document

    try:
        validate_document(document, "f4_linguistic_query_set")
    except SchemaValidationError as error:
        raise F4ValidationError("dataset lingüístico F4.5 inválido") from error
    if document["query_set_id"] != linguistic_query_set_id(document):
        raise F4ValidationError("query_set_id lingüístico no corresponde al contenido")
    group_ids = set()
    query_ids = set()
    for group in document["groups"]:
        if group["group_id"] in group_ids:
            raise F4ValidationError("group_id lingüístico duplicado")
        group_ids.add(group["group_id"])
        units = set(group["semantic_units"])
        anchors = [variant for variant in group["variants"] if variant["transformation"] == "anchor"]
        if len(anchors) != 1 or anchors[0]["language"] != "en" or anchors[0]["parent_query_id"] is not None:
            raise F4ValidationError("cada grupo requiere un único anchor inglés")
        anchor_id = anchors[0]["query_id"]
        for variant in group["variants"]:
            if variant["query_id"] in query_ids:
                raise F4ValidationError("query_id lingüístico duplicado")
            query_ids.add(variant["query_id"])
            if variant["word_count"] != len(variant["text"].split()) or variant["character_count"] != len(variant["text"]):
                raise F4ValidationError(f"conteos textuales incorrectos: {variant['query_id']}")
            if variant["attribute_count"] != len(variant["preserved_units"]) + len(variant["changed_units"]):
                raise F4ValidationError(f"attribute_count incorrecto: {variant['query_id']}")
            changed_from = {change["from"] for change in variant["changed_units"]}
            preserved = set(variant["preserved_units"])
            removed = set(variant["removed_units"])
            if not preserved <= units or not removed <= units or not changed_from <= units:
                raise F4ValidationError("unidades semánticas ajenas al grupo")
            if preserved & removed or preserved & changed_from or not (preserved | removed | changed_from) <= units:
                raise F4ValidationError("unidades semánticas solapadas")
            if preserved | removed | changed_from != units:
                raise F4ValidationError("la anotación no cubre todas las unidades semánticas")
            if variant["transformation"] != "anchor" and variant["parent_query_id"] != anchor_id:
                raise F4ValidationError("variante no referencia al anchor de su grupo")
            expected_relations = {
                "anchor": "reference", "paraphrase": "approximately_equivalent", "synonym_substitution": "approximately_equivalent",
                "detail_expansion": "approximately_equivalent", "translation": "approximately_equivalent",
                "shortening": "information_loss", "attribute_removal": "information_loss", "ambiguity_increase": "information_loss",
                "contradiction": "semantic_change",
            }
            if variant["semantic_relation"] != expected_relations[variant["transformation"]]:
                raise F4ValidationError("transformación y relación semántica incompatibles")
            if variant["semantic_relation"] in {"reference", "approximately_equivalent"} and (variant["removed_units"] or variant["changed_units"]):
                raise F4ValidationError("variante equivalente declara pérdida o cambio")
            if variant["semantic_relation"] == "information_loss" and (not variant["removed_units"] or variant["changed_units"]):
                raise F4ValidationError("pérdida de información mal etiquetada")
            if variant["semantic_relation"] == "semantic_change" and not variant["changed_units"]:
                raise F4ValidationError("cambio semántico sin cambio declarado")


def compare_rankings(anchor: Mapping[str, Any], variant: Mapping[str, Any], *, k: int = 10) -> dict[str, Any]:
    if k < 1 or len(anchor["results"]) < k or len(variant["results"]) < k:
        raise F4ValidationError("rankings incompletos para estabilidad")
    left = anchor["results"][:k]
    right = variant["results"][:k]
    if [row["rank"] for row in left] != list(range(1, k + 1)) or [row["rank"] for row in right] != list(range(1, k + 1)):
        raise F4ValidationError("ranks no consecutivos en comparación de estabilidad")
    left_ids = [row["candidate_id"] for row in left]
    right_ids = [row["candidate_id"] for row in right]
    if len(set(left_ids)) != k or len(set(right_ids)) != k:
        raise F4ValidationError("ranking con candidatos duplicados")
    left_positions = {candidate_id: index for index, candidate_id in enumerate(left_ids, 1)}
    right_positions = {candidate_id: index for index, candidate_id in enumerate(right_ids, 1)}
    shared = sorted(set(left_ids) & set(right_ids))
    score_left = {row["candidate_id"]: float(row["score"]) for row in left}
    score_right = {row["candidate_id"]: float(row["score"]) for row in right}
    for value in [*score_left.values(), *score_right.values()]:
        if not math.isfinite(value):
            raise F4ValidationError("score no finito")
    top1_distance = haversine_m(left[0]["latitude"], left[0]["longitude"], right[0]["latitude"], right[0]["longitude"])
    overlap5 = len(set(left_ids[:5]) & set(right_ids[:5]))
    overlap10 = len(shared)
    anchor_top1_variant_rank = right_positions.get(left_ids[0])
    shifts = [abs(left_positions[candidate_id] - right_positions[candidate_id]) for candidate_id in shared]
    score_deltas = [abs(score_left[candidate_id] - score_right[candidate_id]) for candidate_id in shared]
    return {
        "top1_agreement": left_ids[0] == right_ids[0],
        "top5_overlap_count": overlap5,
        "top10_overlap_count": overlap10,
        "jaccard_at_5": overlap5 / len(set(left_ids[:5]) | set(right_ids[:5])),
        "jaccard_at_10": overlap10 / len(set(left_ids) | set(right_ids)),
        "top1_geographic_distance_m": top1_distance,
        "anchor_top1_rank_in_variant_top10": anchor_top1_variant_rank,
        "anchor_top1_reciprocal_rank": 1 / anchor_top1_variant_rank if anchor_top1_variant_rank else 0.0,
        "shared_candidate_count": len(shared),
        "mean_absolute_rank_shift_shared": sum(shifts) / len(shifts) if shifts else None,
        "mean_absolute_score_delta_shared": sum(score_deltas) / len(score_deltas) if score_deltas else None,
        "top1_score_delta": float(right[0]["score"]) - float(left[0]["score"]),
        "top1_margin_delta": (float(right[0]["score"]) - float(right[1]["score"])) - (float(left[0]["score"]) - float(left[1]["score"])),
    }


def aggregate_comparisons(comparisons: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in comparisons:
        for dimension in ("language", "transformation", "semantic_relation", "length_bucket", "attribute_count"):
            groups[(dimension, str(row[dimension]))].append(row)
    output = []
    for (dimension, value), rows in sorted(groups.items()):
        output.append({
            "dimension": dimension, "value": value, "count": len(rows),
            "top1_agreement_rate": sum(row["metrics"]["top1_agreement"] for row in rows) / len(rows),
            "mean_jaccard_at_5": sum(row["metrics"]["jaccard_at_5"] for row in rows) / len(rows),
            "mean_jaccard_at_10": sum(row["metrics"]["jaccard_at_10"] for row in rows) / len(rows),
            "mean_top1_geographic_distance_m": sum(row["metrics"]["top1_geographic_distance_m"] for row in rows) / len(rows),
        })
    return output


def length_bucket(word_count: int) -> str:
    if word_count <= 5:
        return "short_1_5"
    if word_count <= 10:
        return "medium_6_10"
    return "long_11_plus"


def validate_robustness_result(document: Mapping[str, Any]) -> None:
    from .validation import SchemaValidationError, validate_document

    try:
        validate_document(document, "f4_linguistic_robustness_result")
    except SchemaValidationError as error:
        raise F4ValidationError("resultado de robustez F4.5 inválido") from error
    if document["aggregates"] != aggregate_comparisons(document["comparisons"]):
        raise F4ValidationError("agregados de robustez no corresponden a comparaciones")
    if document["robustness_result_id"] != robustness_result_id(document):
        raise F4ValidationError("robustness_result_id no corresponde al contenido")
    seen_pairs = set()
    for row in document["comparisons"]:
        required = {"group_id", "anchor_query_id", "variant_query_id", "language", "transformation", "semantic_relation", "word_count", "attribute_count", "length_bucket", "metrics"}
        if set(row) != required or (row["anchor_query_id"], row["variant_query_id"]) in seen_pairs:
            raise F4ValidationError("comparación lingüística duplicada o mal formada")
        seen_pairs.add((row["anchor_query_id"], row["variant_query_id"]))
        metrics = row["metrics"]
        expected_metric_fields = {"top1_agreement", "top5_overlap_count", "top10_overlap_count", "jaccard_at_5", "jaccard_at_10", "top1_geographic_distance_m", "anchor_top1_rank_in_variant_top10", "anchor_top1_reciprocal_rank", "shared_candidate_count", "mean_absolute_rank_shift_shared", "mean_absolute_score_delta_shared", "top1_score_delta", "top1_margin_delta"}
        if set(metrics) != expected_metric_fields:
            raise F4ValidationError("payload de métricas incompleto")
        for field in ("jaccard_at_5", "jaccard_at_10", "anchor_top1_reciprocal_rank"):
            if not 0 <= metrics[field] <= 1:
                raise F4ValidationError("métrica de estabilidad fuera de rango")
        if not 0 <= metrics["top5_overlap_count"] <= 5 or not 0 <= metrics["top10_overlap_count"] <= 10:
            raise F4ValidationError("overlap fuera de rango")
        if metrics["shared_candidate_count"] != metrics["top10_overlap_count"]:
            raise F4ValidationError("shared_candidate_count inconsistente")
        expected_j5 = metrics["top5_overlap_count"] / (10 - metrics["top5_overlap_count"])
        expected_j10 = metrics["top10_overlap_count"] / (20 - metrics["top10_overlap_count"])
        if not math.isclose(metrics["jaccard_at_5"], expected_j5) or not math.isclose(metrics["jaccard_at_10"], expected_j10):
            raise F4ValidationError("Jaccard inconsistente con overlaps")
        rank = metrics["anchor_top1_rank_in_variant_top10"]
        if rank is not None and (isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= 10):
            raise F4ValidationError("rango censurado fuera de 1..10")
        expected_rr = 1 / rank if rank else 0.0
        if metrics["anchor_top1_reciprocal_rank"] != expected_rr:
            raise F4ValidationError("reciprocal rank inconsistente")
        for field in ("mean_absolute_rank_shift_shared", "mean_absolute_score_delta_shared", "top1_score_delta", "top1_margin_delta"):
            if metrics[field] is not None and not math.isfinite(metrics[field]):
                raise F4ValidationError("métrica no finita")
        for field in ("mean_absolute_rank_shift_shared", "mean_absolute_score_delta_shared"):
            if metrics[field] is not None and metrics[field] < 0:
                raise F4ValidationError("métrica absoluta negativa")
        if metrics["top1_geographic_distance_m"] < 0 or not math.isfinite(metrics["top1_geographic_distance_m"]):
            raise F4ValidationError("distancia de salida no válida")
