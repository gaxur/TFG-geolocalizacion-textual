"""Auditoría y evaluación provisional del benchmark sintético OSM F5.5c."""

from __future__ import annotations

from collections import Counter
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import statistics
import time
from typing import Any, Mapping, Sequence

from .f4_evaluation import haversine_m, query_dataset_id
from .f5_synthetic_osm_benchmark import build_description, validate_synthetic_benchmark
from .f5_textual_variants import source_query_input_sha256, textual_variant_dataset_id
from .f57_experimental_evaluation import COORD_RE, INTERNAL_RE, canonical_bytes


KINDS = ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved", "en_cartographic")
GALLERIES = ("madrid-25m", "madrid-50m")
EVALUATION_PREFIX = "f55c-exploratory-evaluation-sha256-"
RANKING_PREFIX = "f55c-exploratory-rankings-sha256-"
VISUAL_OR_ORIENTATION_RE = re.compile(r"\b(?:veo|visible|mirando|izquierda|derecha|delante|detr[aá]s|fachada|color|alto|alta|see|visible|looking|left|right|ahead|behind|facade|colour|color|tall)\b", re.I)
DIRECT_LOCATION_RE = re.compile(r"\b(?:se encuentra en|ubicaci[oó]n es|located at|location is|coordinates?|coordenadas?)\b", re.I)
EXACT_DISTANCE_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:m|metros?|meters?)\b", re.I)
TYPE_PATTERNS = {
    "square": (r"\bplaza\b", r"\bsquare\b"),
    "park": (r"\b(?:parque|jard[ií]n)\b", r"\b(?:park|garden)\b"),
    "church": (r"\b(?:lugar de culto|iglesia|templo)\b", r"\b(?:place of worship|church|temple)\b"),
    "monument": (r"\b(?:monumento|elemento hist[oó]rico)\b", r"\b(?:monument|historic(?:al)? (?:element|feature))\b"),
    "street": (r"\b(?:v[ií]a|calle)\b", r"\b(?:road|street|way)\b"),
    "building": (r"\bedificios?\b", r"\bbuildings?\b"),
    "commercial": (r"\b(?:actividades|equipamientos?) urbanos?\b", r"\b(?:urban activities|urban facilities|amenities|facilities)\b"),
}
RELATION_PATTERNS = {
    "inside_cell": (r"\bdentro de\b", r"\b(?:within|inside)\b"),
    "crosses_cell": (r"\b(?:cruza[n]?|atraviesa[n]?)\b", r"\bcross(?:es)?\b"),
    "contains_cell": (r"\bcontiene[n]?\b", r"\bcontain(?:s)?\b"),
    "overlaps_cell": (r"\bse (?:solapa[n]?|superpone[n]?)\b", r"\boverlap(?:s)?\b"),
    "touches_cell_boundary": (r"\btoca[n]? el borde\b", r"\btouch(?:es)? the (?:boundary|edge)\b"),
    "intersects_cell": (r"\bpr[oó]ximo\b", r"\bnear(?:by)?\b"),
}


class F55cEvaluationError(ValueError):
    pass


def audit_benchmark(document: Mapping[str, Any]) -> dict[str, Any]:
    """Produce controles individuales que no cambian ni interpretan la revisión humana."""
    summary = validate_synthetic_benchmark(document)
    normalized = Counter(_normalize(row["description"]["text"]) for row in document["observations"])
    signatures = Counter(_semantic_signature(row) for row in document["observations"])
    rows = []
    for row in document["observations"]:
        text = row["description"]["text"]
        rebuilt, used = build_description(row["evidence"])
        evidence_refs = [item["osm_ref"] for item in row["evidence"]]
        checks = {
            "entities_exist_in_frozen_evidence": len(evidence_refs) == len(set(evidence_refs)) and len(evidence_refs) >= 3,
            "semantic_types_supported": all(item["semantic_type"] in TYPE_PATTERNS for item in row["evidence"]),
            "topological_predicates_supported": all(item["relation"] in RELATION_PATTERNS for item in row["evidence"]),
            "distances_and_associations_frozen": all(isinstance(item["center_distance_m"], (int, float)) and math.isfinite(item["center_distance_m"]) and item["center_distance_m"] >= 0 for item in row["evidence"]),
            "description_reconstructed_from_evidence": rebuilt == text and [item["osm_ref"] for item in used] == evidence_refs,
            "no_coordinate_or_internal_id_leak": not COORD_RE.search(text) and not INTERNAL_RE.search(text),
            "no_exact_distance_leak": not EXACT_DISTANCE_RE.search(text),
            "no_visual_or_orientation_claim": not VISUAL_OR_ORIENTATION_RE.search(text),
            "no_exact_text_duplicate": normalized[_normalize(text)] == 1,
            "no_semantic_signature_duplicate": signatures[_semantic_signature(row)] == 1,
            "informative": row["quality"]["entity_count"] >= 3 and len(row["quality"]["semantic_types"]) >= 2 and len(text) >= 120,
        }
        rows.append({
            "observation_id": row["observation_id"], "partition": row["partition"],
            "review_status": row["review"]["status"], "checks": checks,
            "automatic_audit_passed": all(checks.values()),
            "issue_codes": [name for name, passed in checks.items() if not passed],
        })
    return {
        "schema_version": "1.0", "contract_version": "f55c-automatic-benchmark-audit-v1",
        "benchmark_id": document["benchmark_id"], "ground_truth_kind": "synthetic_osm", "real_ground_truth": False,
        "summary": {**summary, "passed": sum(row["automatic_audit_passed"] for row in rows), "failed": sum(not row["automatic_audit_passed"] for row in rows), "pending_human_review": sum(row["review_status"] == "pending" for row in rows)},
        "observations": rows,
        "limitations": ["automatic_audit_does_not_approve_human_review", "f3_equality_must_be_validated_separately", "synthetic_osm_not_human_observation"],
    }


def human_review_template(document: Mapping[str, Any]) -> dict[str, Any]:
    validate_synthetic_benchmark(document)
    return {
        "contract_version": "f55c-synthetic-review-decisions-v1", "reviewer": "<nombre-del-revisor>",
        "reviewed_at_utc": "<AAAA-MM-DDTHH:MM:SSZ>",
        "decisions": [{"observation_id": row["observation_id"], "decision": "<approve|reject>", "notes": "<justificación humana obligatoria>"} for row in document["observations"]],
    }


def prepare_variant_inputs(benchmark: Mapping[str, Any], catalog50: Any, audit: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_synthetic_benchmark(benchmark)
    passed = {row["observation_id"] for row in audit["observations"] if row["automatic_audit_passed"]}
    queries, observations = [], []
    for row in benchmark["observations"]:
        if row["observation_id"] not in passed:
            continue
        qid, text = row["observation_id"], row["description"]["text"]
        query = {
            "query_id": qid, "location_id": row["location_id"], "derivation_group_id": row["derivation_group_id"], "partition": row["partition"],
            "description": {"text": text, "language": "es", "contains_coordinates": False},
            "provenance": {"source_type": "synthetic", "description": "Texto sintético OSM F5.5c; coordenada reservada exclusivamente para evaluación posterior.", "independent_environment_observation": False, "instructions_version": "f55c-synthetic-osm-v2", "collected_at_utc": None},
            "reference": {"status": "pending", "latitude": None, "longitude": None, "crs": None, "capture_method": None, "reported_accuracy_m": None, "validation_method": None, "catalog_assignment": None},
            "ambiguity": {"status": "unreviewed", "notes": "Pendiente de revisión humana; ejecución exploratoria separada."}, "validation_status": "pending",
        }
        queries.append(query)
        def pending(kind: str, language: str) -> dict[str, Any]:
            return {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": language, "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        original = {"variant_id": f"{qid}-es-original-f55c-v1", "kind": "es_original", "status": "reviewed", "text": text, "language": "es", "generation": {"method": "original", "tool_or_model": "deterministic_osm_evidence_templates_v1", "version": "f55c-synthetic-osm-v2", "configuration_or_prompt": "copy-frozen-benchmark-text", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        observations.append({"source_query_id": qid, "source_input_sha256": "0" * 64, "partition": row["partition"], "location_id": row["location_id"], "derivation_group_id": row["derivation_group_id"], "toponyms": [], "orientation": {"status": "absent", "cardinal": None, "bearing_degrees": None, "bearing_convention": None, "method": None, "uncertainty_degrees": None, "provenance": None, "verification_status": "not_applicable", "relative_relations_present": False, "notes": "No se infiere orientación desde OSM."}, "variants": [original, pending("es_cartographic", "es"), pending("en_conventional", "en"), pending("en_toponym_preserved", "en"), pending("en_cartographic", "en")], "notes": "F5.5c exploratorio; benchmark y variantes derivados pendientes de revisión humana."})
    # Los textos proceden de una plantilla cerrada y comparten vocabulario por diseño;
    # la auditoría anterior exige unicidad exacta y de firma semántica.
    dataset = {"schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "", "dataset_version": "f55c-synthetic-exploratory-v1", "region": {"region_id": catalog50.region_id, "bbox_wgs84": dict(catalog50.region_bbox_wgs84)}, "catalog": {"manifest_id": catalog50.manifest_id, "manifest_sha256": catalog50.sha256, "candidate_count": len(catalog50.candidates), "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"}, "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": True, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": 1.0}, "queries": queries}
    dataset["dataset_id"] = query_dataset_id(dataset)
    query_by = {row["query_id"]: row for row in queries}
    for row in observations: row["source_input_sha256"] = source_query_input_sha256(query_by[row["source_query_id"]])
    template = json.loads((Path(__file__).resolve().parents[2] / "config/madrid_f53b_textual_variants_template.json").read_text(encoding="utf-8"))
    template["dataset_version"] = "f55c-synthetic-exploratory-v1"
    raw = canonical_bytes(dataset) + b"\n"
    template["source_query_dataset"] = {"dataset_id": dataset["dataset_id"], "sha256": hashlib.sha256(raw).hexdigest()}
    template["observations"] = observations
    template["dataset_id"] = textual_variant_dataset_id(template)
    return dataset, template


def audit_variants(sidecar: Mapping[str, Any], run: Mapping[str, Any], benchmark: Mapping[str, Any]) -> dict[str, Any]:
    records = {(row["source_query_id"], row["kind"]): row for row in run["records"]}
    evidence_names = {row["observation_id"]: sorted({item["name"] for item in row["evidence"] if item.get("name")}, key=len, reverse=True) for row in benchmark["observations"]}
    issues, eligible = [], []
    for observation in sidecar["observations"]:
        original = next(row for row in observation["variants"] if row["kind"] == "es_original")
        original_types = _detected(TYPE_PATTERNS, original["text"])
        original_relations = _detected(RELATION_PATTERNS, original["text"])
        for variant in observation["variants"]:
            text, codes = variant.get("text") or "", []
            if COORD_RE.search(text): codes.append("coordinate_leak")
            if INTERNAL_RE.search(text): codes.append("internal_identifier_leak")
            if EXACT_DISTANCE_RE.search(text): codes.append("exact_distance_introduced")
            if VISUAL_OR_ORIENTATION_RE.search(text): codes.append("visual_or_orientation_claim")
            if DIRECT_LOCATION_RE.search(text): codes.append("direct_location_answer")
            introduced_names = [name for name in evidence_names[observation["source_query_id"]] if name.casefold() in text.casefold() and name.casefold() not in original["text"].casefold()]
            if introduced_names: codes.append("osm_toponym_introduced")
            if variant["kind"] != "es_original":
                record = records.get((observation["source_query_id"], variant["kind"]))
                if record is None or record.get("output_text_sha256") != _sha256_text(text): codes.append("transformation_record_mismatch")
                elif not record["validation"]["structurally_valid"]: codes.append("automatic_validation_failed")
                missing_types = original_types - _detected(TYPE_PATTERNS, text)
                missing_relations = original_relations - _detected(RELATION_PATTERNS, text)
                if missing_types: codes.extend(f"entity_lost:{value}" for value in sorted(missing_types))
                if missing_relations: codes.extend(f"relation_lost:{value}" for value in sorted(missing_relations))
            allowed = not codes and variant["status"] in {"reviewed", "generated"} and bool(text)
            if allowed: eligible.append({"source_query_id": observation["source_query_id"], "variant_kind": variant["kind"], "partition": observation["partition"]})
            issues.append({"source_query_id": observation["source_query_id"], "partition": observation["partition"], "variant_id": variant.get("variant_id"), "variant_kind": variant["kind"], "variant_review_status": variant["review_status"], "benchmark_review_status": next(row["review"]["status"] for row in benchmark["observations"] if row["observation_id"] == observation["source_query_id"]), "automatic_checks_passed": not codes, "exploratory_execution_allowed": allowed, "official_evaluation_eligible": False, "introduced_osm_names": introduced_names, "issue_codes": codes})
    return {"schema_version": "1.0", "contract_version": "f55c-exploratory-variant-audit-v1", "ground_truth_kind": "synthetic_osm", "real_ground_truth": False, "issues": issues, "eligible_pairs": eligible, "limitations": ["automatic_checks_do_not_replace_human_semantic_review", "pending_benchmark_review", "pending_qwen_variant_review", "provisional_execution_only", "never_merge_with_real_f54_metrics"]}


def run_rankings(sidecar: Mapping[str, Any], audit: Mapping[str, Any], retriever: Any, *, gallery_ids: Sequence[str] = GALLERIES, top_k: int = 10) -> dict[str, Any]:
    if set(gallery_ids) != set(GALLERIES) or top_k != 10: raise F55cEvaluationError("F5.5c exige ambas galerías y Top-10")
    eligible = {(row["source_query_id"], row["variant_kind"]) for row in audit["eligible_pairs"]}
    rows, checkpoint = [], None
    for observation in sidecar["observations"]:
        for variant in observation["variants"]:
            if (observation["source_query_id"], variant["kind"]) not in eligible: continue
            started = time.perf_counter()
            response = retriever.retrieve_many(gallery_ids=gallery_ids, query_id=variant["variant_id"], text=variant["text"], language=variant["language"], k=top_k)
            elapsed = (time.perf_counter() - started) * 1000
            current = response["model"]["checkpoint_sha256"]
            checkpoint = current if checkpoint is None else checkpoint
            if checkpoint != current: raise F55cEvaluationError("el checkpoint cambió durante la campaña")
            for retrieval in response["retrievals"]:
                _validate_results(retrieval["results"])
                if retrieval.get("gallery_count") not in {None, 1115 if retrieval["gallery_id"] == "madrid-25m" else 253}: raise F55cEvaluationError("tamaño de galería inesperado")
                rows.append({"source_query_id": observation["source_query_id"], "partition": observation["partition"], "variant_id": variant["variant_id"], "variant_kind": variant["kind"], "language": variant["language"], "text_sha256": _sha256_text(variant["text"]), "gallery_id": retrieval["gallery_id"], "gallery_count": 1115 if retrieval["gallery_id"] == "madrid-25m" else 253, "top_k": 10, "results": retrieval["results"], "retrieval_ms": response["timings_ms"]["total"], "pipeline_elapsed_ms": elapsed})
    document = {"schema_version": "1.0", "contract_version": "f55c-exploratory-rankings-v1", "ranking_id": "", "checkpoint_sha256": checkpoint or "0" * 64, "gallery_ids": list(gallery_ids), "ranking_method": "exhaustive_cosine", "top_k": 10, "rows": rows, "limitations": ["pending_human_review", "synthetic_osm", "coordinates_not_used_for_retrieval", "no_prefiltering", "no_reranking", "frozen_embeddings"]}
    document["ranking_id"] = ranking_id(document)
    return document


def ranking_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "checkpoint_sha256", "gallery_ids", "ranking_method", "top_k", "rows", "limitations")}
    return RANKING_PREFIX + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def evaluate(benchmark: Mapping[str, Any], rankings: Mapping[str, Any], *, benchmark_sha256: str, variants_sha256: str, rankings_sha256: str) -> dict[str, Any]:
    if rankings["ranking_id"] != ranking_id(rankings): raise F55cEvaluationError("identidad de rankings inválida")
    references = {row["observation_id"]: row for row in benchmark["observations"]}
    indexed = {(row["source_query_id"], row["variant_kind"], row["gallery_id"]): row for row in rankings["rows"]}
    per_observation = []
    for qid, reference in sorted(references.items()):
        for kind in KINDS:
            for gallery in GALLERIES:
                ranking = indexed.get((qid, kind, gallery))
                assignment = reference["reference"][gallery]
                if ranking is None:
                    per_observation.append({"source_query_id": qid, "partition": reference["partition"], "variant_kind": kind, "gallery_id": gallery, "status": "excluded_or_missing_variant", "reference_candidate_id": assignment["candidate_id"]})
                    continue
                _validate_results(ranking["results"])
                exact_rank = next((item["rank"] for item in ranking["results"] if item["candidate_id"] == assignment["candidate_id"]), None)
                distances = [haversine_m(reference["reference"]["latitude"], reference["reference"]["longitude"], item["latitude"], item["longitude"]) for item in ranking["results"]]
                minimums = {str(k): min(distances[:k]) for k in (1, 5, 10)}
                per_observation.append({"source_query_id": qid, "partition": reference["partition"], "variant_kind": kind, "gallery_id": gallery, "status": "evaluated_exploratory_synthetic_osm", "reference_candidate_id": assignment["candidate_id"], "exact_rank": exact_rank, "hits_at_k": {str(k): exact_rank is not None and exact_rank <= k for k in (1, 5, 10)}, "top1_error_m": distances[0], "minimum_error_at_k_m": minimums, "geo_hits": {str(k): {str(radius): minimums[str(k)] <= radius for radius in (25, 50, 100)} for k in (1, 5, 10)}, "top10_ids": [item["candidate_id"] for item in ranking["results"]], "retrieval_ms": ranking["retrieval_ms"], "pipeline_elapsed_ms": ranking["pipeline_elapsed_ms"]})
    metrics = []
    for partition in ("all", "development", "evaluation"):
        for gallery in GALLERIES:
            for kind in KINDS:
                rows = [row for row in per_observation if row["status"].startswith("evaluated") and row["gallery_id"] == gallery and row["variant_kind"] == kind and (partition == "all" or row["partition"] == partition)]
                metrics.append(_aggregate(partition, gallery, kind, rows))
    document = {"schema_version": "1.0", "contract_version": "f55c-exploratory-synthetic-evaluation-v1", "evaluation_id": "", "protocol": {"reference_kind": "synthetic_osm", "real_ground_truth": False, "official_f54_evaluation": False, "provisional_execution": True, "ks": [1, 5, 10], "geo_thresholds_m": [25, 50, 100], "coordinates_used_for_retrieval": False, "evaluation_partition_used_for_tuning": False, "prefiltering": False, "reranking": False, "vlm": False, "fine_tuning": False}, "inputs": {"benchmark_id": benchmark["benchmark_id"], "benchmark_sha256": benchmark_sha256, "variants_sha256": variants_sha256, "rankings_sha256": rankings_sha256}, "coverage": {"observations": len(references), "pending_human_review": sum(row["review"]["status"] == "pending" for row in references.values()), "expected_rankings_if_all_eligible": len(references) * len(KINDS) * len(GALLERIES), "observed_rankings": len(rankings["rows"]), "officially_evaluable": 0}, "metrics": metrics, "paired_comparisons": _paired(per_observation), "per_observation": per_observation, "limitations": ["synthetic_osm_not_human_ground_truth", "osm_source_overlap", "pending_human_review", "pending_qwen_semantic_review", "not_f54_metrics", "never_merge_with_f57_or_f54", "zero_shot_madrid_exploratory"]}
    document["evaluation_id"] = EVALUATION_PREFIX + hashlib.sha256(canonical_bytes({key: document[key] for key in document if key != "evaluation_id"})).hexdigest()
    return document


def render_html(document: Mapping[str, Any], output: Path) -> None:
    rows = []
    for metric in document["metrics"]:
        if metric["partition"] != "all": continue
        r = metric["recall_at_k"]
        rows.append(f"<tr><td>{escape(metric['gallery_id'])}</td><td>{escape(metric['variant_kind'])}</td><td>{metric['evaluated_count']}</td><td>{_pct(r['1'])}</td><td>{_pct(r['5'])}</td><td>{_pct(r['10'])}</td><td>{_pct(metric['geo_recall_at_k']['10']['50'])}</td><td>{_pct(metric['geo_recall_at_k']['10']['100'])}</td><td>{metric['top1_error_m']['mean']:.2f}</td><td>{metric['minimum_error_at_k_m']['10']['mean']:.2f}</td></tr>")
    html = f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>F5.5c exploratorio</title><style>body{{font:16px system-ui;max-width:1250px;margin:auto;padding:2rem;background:#eef2e8}}.warning{{background:#ffe4b8;border-left:6px solid #9d4b16;padding:1rem}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{border:1px solid #aaa;padding:.45rem;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}</style></head><body><h1>F5.5c: evaluación exploratoria synthetic_osm</h1><p class='warning'><strong>No es Ground Truth humano ni evaluación oficial F5.4.</strong> Las 35 descripciones y las variantes Qwen continúan pendientes de revisión humana. OSM es fuente del texto y de la galería cartográfica.</p><p>Rankings reales: {document['coverage']['observed_rankings']}/{document['coverage']['expected_rankings_if_all_eligible']}. Casos oficialmente evaluables: 0.</p><table><thead><tr><th>Galería</th><th>Variante</th><th>n</th><th>R@1</th><th>R@5</th><th>R@10</th><th>Geo@10 50m</th><th>Geo@10 100m</th><th>Error Top-1 medio</th><th>Mín. Top-10 medio</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p><code>{escape(document['evaluation_id'])}</code></p></body></html>"
    output.write_text(html, encoding="utf-8")


def _aggregate(partition: str, gallery: str, kind: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def summary(values):
        return {"count": len(values), "mean": statistics.fmean(values) if values else None, "median": statistics.median(values) if values else None}
    count = len(rows)
    return {"partition": partition, "gallery_id": gallery, "variant_kind": kind, "evaluated_count": count, "recall_at_k": {str(k): sum(row["hits_at_k"][str(k)] for row in rows) / count if count else None for k in (1, 5, 10)}, "geo_recall_at_k": {str(k): {str(radius): sum(row["geo_hits"][str(k)][str(radius)] for row in rows) / count if count else None for radius in (25, 50, 100)} for k in (1, 5, 10)}, "top1_error_m": summary([row["top1_error_m"] for row in rows]), "minimum_error_at_k_m": {str(k): summary([row["minimum_error_at_k_m"][str(k)] for row in rows]) for k in (5, 10)}, "retrieval_latency_ms": summary([row["retrieval_ms"] for row in rows])}


def _paired(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    index = {(row["source_query_id"], row["gallery_id"], row["variant_kind"]): row for row in rows if row["status"].startswith("evaluated")}
    output = []
    for partition in ("all", "development", "evaluation"):
        for gallery in GALLERIES:
            for kind in KINDS[1:]:
                cases = []
                for qid in sorted({key[0] for key in index}):
                    anchor, variant = index.get((qid, gallery, "es_original")), index.get((qid, gallery, kind))
                    if not anchor or not variant or (partition != "all" and anchor["partition"] != partition): continue
                    delta = variant["top1_error_m"] - anchor["top1_error_m"]
                    cases.append({"source_query_id": qid, "outcome": "improved" if delta < -1e-9 else "worsened" if delta > 1e-9 else "tied", "top1_error_delta_m": delta})
                output.append({"partition": partition, "gallery_id": gallery, "variant_kind": kind, "paired_count": len(cases), "improved": sum(row["outcome"] == "improved" for row in cases), "worsened": sum(row["outcome"] == "worsened" for row in cases), "tied": sum(row["outcome"] == "tied" for row in cases), "mean_top1_error_delta_m": statistics.fmean(row["top1_error_delta_m"] for row in cases) if cases else None, "cases": cases})
    return output


def _validate_results(results: Sequence[Mapping[str, Any]]) -> None:
    if len(results) != 10 or [row.get("rank") for row in results] != list(range(1, 11)) or len({row.get("candidate_id") for row in results}) != 10: raise F55cEvaluationError("ranking Top-10 incompleto")
    for row in results:
        if any(not math.isfinite(row[field]) for field in ("latitude", "longitude", "cosine_similarity")): raise F55cEvaluationError("ranking no finito")


def _detected(patterns: Mapping[str, Sequence[str]], text: str) -> set[str]:
    return {name for name, expressions in patterns.items() if any(re.search(expression, text, re.I) for expression in expressions)}


def _normalize(text: str) -> str: return " ".join(re.findall(r"[^\W_]+", text.casefold(), re.UNICODE))
def _semantic_signature(row: Mapping[str, Any]) -> tuple: return tuple(sorted((item["semantic_type"], item["relation"]) for item in row["evidence"]))
def _sha256_text(text: str) -> str: return hashlib.sha256(text.encode("utf-8")).hexdigest()
def _pct(value: float | None) -> str: return "n/d" if value is None else f"{100 * value:.1f}%"
