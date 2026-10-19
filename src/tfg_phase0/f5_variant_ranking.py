"""Rankings independientes y comparación descriptiva de variantes F5.2."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from typing import Any, Mapping, Protocol, Sequence

from .f4_evaluation import haversine_m
from .f5_textual_variants import F5ValidationError


REPORT_PREFIX = "f5-variant-ranking-report-sha256-"


class VariantRetriever(Protocol):
    @property
    def gallery_ids(self) -> tuple[str, ...]: ...
    def retrieve_many(self, *, gallery_ids: Sequence[str], query_id: str, text: str, language: str, k: int) -> dict[str, Any]: ...


def run_variant_rankings(
    sidecar: Mapping[str, Any],
    retriever: VariantRetriever,
    *,
    sidecar_sha256: str,
    gallery_ids: Sequence[str],
    top_k: int,
    transformation_run: Mapping[str, Any] | None = None,
    allow_unreviewed_technical: bool = False,
) -> dict[str, Any]:
    if top_k < 2 or top_k > 10:
        raise F5ValidationError("F5.2 requiere K entre 2 y 10")
    if not gallery_ids or len(set(gallery_ids)) != len(gallery_ids) or any(gallery not in retriever.gallery_ids for gallery in gallery_ids):
        raise F5ValidationError("galerías F5.2 inválidas")
    transform_times = {}
    if transformation_run is not None:
        transform_times = {(row["source_query_id"], row["variant_id"]): row["duration_ms"] for row in transformation_run["records"] if row["variant_id"] is not None}

    ranking_rows = []
    checkpoint_sha256 = None
    for observation in sidecar["observations"]:
        for variant in observation["variants"]:
            eligible = variant["status"] == "reviewed" or (allow_unreviewed_technical and variant["status"] == "generated")
            if not eligible or not variant["text"] or not variant["variant_id"]:
                continue
            started = time.perf_counter()
            response = retriever.retrieve_many(
                gallery_ids=gallery_ids,
                query_id=variant["variant_id"],
                text=variant["text"],
                language=variant["language"],
                k=top_k,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            response_checkpoint = response["model"]["checkpoint_sha256"]
            if checkpoint_sha256 is None:
                checkpoint_sha256 = response_checkpoint
            elif checkpoint_sha256 != response_checkpoint:
                raise F5ValidationError("los rankings F5.2 usan checkpoints distintos")
            for retrieval in response["retrievals"]:
                if retrieval["gallery_id"] not in gallery_ids or retrieval["effective_k"] != top_k or retrieval["ranking_method"] != "exhaustive_cosine" or retrieval["tie_break"] != "candidate_id_ascending":
                    raise F5ValidationError("respuesta del recuperador incompatible con F5.2")
                results = [dict(row) for row in retrieval["results"]]
                ranking_rows.append({
                    "source_query_id": observation["source_query_id"], "partition": observation["partition"],
                    "variant_id": variant["variant_id"], "kind": variant["kind"], "review_status": variant["review_status"],
                    "gallery_id": retrieval["gallery_id"], "top_k": top_k, "results": results,
                    "top1_margin": results[0]["cosine_similarity"] - results[1]["cosine_similarity"],
                    "spatial_dispersion_m": spatial_dispersion_m(results),
                    "transformation_ms": transform_times.get((observation["source_query_id"], variant["variant_id"]), 0.0 if variant["kind"] == "es_original" else None),
                    "retrieval_ms": response["timings_ms"]["total"], "pipeline_elapsed_ms": elapsed_ms,
                })

    comparisons = paired_comparisons(ranking_rows)
    cross_gallery = cross_gallery_comparisons(ranking_rows)
    report = {
        "schema_version": "1.0", "contract_version": "f5-variant-ranking-report-v1", "report_id": REPORT_PREFIX + "0" * 64,
        "sidecar": {"dataset_id": sidecar["dataset_id"], "sha256": sidecar_sha256, "transformation_run_id": transformation_run["run_id"] if transformation_run else None},
        "retrieval": {"checkpoint_sha256": checkpoint_sha256 or "0" * 64, "gallery_ids": list(gallery_ids), "top_k": top_k, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "scores_fused": False, "coordinates_fused": False},
        "rankings": ranking_rows, "comparisons": comparisons, "cross_gallery": cross_gallery,
        "geographic_accuracy_available": False,
        "limitations": ["no_ground_truth_accuracy_metrics", "descriptive_stability_only", "no_score_fusion", "no_coordinate_fusion", "no_osm_preselection_or_reranking"],
    }
    report["report_id"] = variant_ranking_report_id(report)
    return report


def paired_comparisons(rankings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rankings:
        groups.setdefault((row["source_query_id"], row["gallery_id"]), []).append(row)
    output = []
    for (source_query_id, gallery_id), rows in sorted(groups.items()):
        anchors = [row for row in rows if row["kind"] == "es_original"]
        if len(anchors) != 1:
            continue
        anchor = anchors[0]
        for variant in sorted((row for row in rows if row is not anchor), key=lambda row: row["kind"]):
            output.append(compare_two_rankings(source_query_id, gallery_id, anchor, variant))
    return output


def compare_two_rankings(source_query_id: str, gallery_id: str, anchor: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    left, right = anchor["results"], variant["results"]
    k = min(len(left), len(right))
    left_ids, right_ids = [row["candidate_id"] for row in left[:k]], [row["candidate_id"] for row in right[:k]]
    left_pos, right_pos = {value: index for index, value in enumerate(left_ids, 1)}, {value: index for index, value in enumerate(right_ids, 1)}
    shared = sorted(set(left_ids) & set(right_ids))
    overlap = len(shared)
    return {
        "source_query_id": source_query_id, "gallery_id": gallery_id, "anchor_variant_id": anchor["variant_id"],
        "variant_id": variant["variant_id"], "variant_kind": variant["kind"], "top_k": k,
        "top1_agreement": left_ids[0] == right_ids[0], "top_k_overlap": overlap,
        "jaccard_at_k": overlap / len(set(left_ids) | set(right_ids)),
        "top1_output_distance_m": haversine_m(left[0]["latitude"], left[0]["longitude"], right[0]["latitude"], right[0]["longitude"]),
        "mean_shared_rank_shift": statistics.fmean(abs(left_pos[value] - right_pos[value]) for value in shared) if shared else None,
        "anchor_top1_margin": anchor["top1_margin"], "variant_top1_margin": variant["top1_margin"],
        "anchor_dispersion_m": anchor["spatial_dispersion_m"], "variant_dispersion_m": variant["spatial_dispersion_m"],
        "transformation_ms": variant["transformation_ms"], "retrieval_ms": variant["retrieval_ms"],
        "total_variant_latency_ms": (variant["transformation_ms"] + variant["retrieval_ms"]) if variant["transformation_ms"] is not None else None,
    }


def spatial_dispersion_m(results: Sequence[Mapping[str, Any]]) -> float:
    if not results:
        raise F5ValidationError("no se puede calcular dispersión sin candidatos")
    sums = []
    for candidate in results:
        total = sum(haversine_m(candidate["latitude"], candidate["longitude"], other["latitude"], other["longitude"]) for other in results)
        sums.append(total)
    medoid = results[min(range(len(results)), key=lambda index: (sums[index], results[index]["candidate_id"]))]
    return statistics.fmean(haversine_m(medoid["latitude"], medoid["longitude"], candidate["latitude"], candidate["longitude"]) for candidate in results)


def cross_gallery_comparisons(rankings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rankings:
        groups.setdefault((row["source_query_id"], row["variant_id"]), []).append(row)
    output = []
    for (source_query_id, variant_id), rows in sorted(groups.items()):
        by_gallery = {row["gallery_id"]: row for row in rows}
        if set(by_gallery) != {"madrid-25m", "madrid-50m"}:
            continue
        left, right = by_gallery["madrid-25m"], by_gallery["madrid-50m"]
        distances = [haversine_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"]) for a in left["results"] for b in right["results"]]
        output.append({
            "source_query_id": source_query_id, "variant_id": variant_id, "variant_kind": left["kind"],
            "top1_distance_m": haversine_m(left["results"][0]["latitude"], left["results"][0]["longitude"], right["results"][0]["latitude"], right["results"][0]["longitude"]),
            "minimum_top_k_distance_m": min(distances), "candidate_ids_compared_as_equal": False,
        })
    return output


def variant_ranking_report_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "sidecar", "retrieval", "rankings", "comparisons", "cross_gallery", "geographic_accuracy_available", "limitations")}
    return REPORT_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
