"""Evaluación F5.7 con referencias Street View aproximadas, nunca GT oficial."""

from __future__ import annotations

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
from .f5_textual_variants import source_query_input_sha256, textual_variant_dataset_id


EVALUATION_PREFIX = "f57-experimental-evaluation-sha256-"
RANKING_PREFIX = "f57-provisional-rankings-sha256-"
KINDS = ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved", "en_cartographic")
GALLERIES = ("madrid-25m", "madrid-50m")
COORD_RE = re.compile(r"(?<!\w)[+-]?\d{1,3}[.,]\d{3,}")
INTERNAL_RE = re.compile(r"(?:MADP_|candidate|panorama|__TOPONYM_|[A-Za-z0-9_-]{18,})", re.I)
NEG_ES = re.compile(r"\b(?:no|sin|ningun[oa]s?|nunca)\b", re.I)
NEG_EN = re.compile(r"\b(?:no|not|without|none|never)\b", re.I)
RELATIONS = {
    "left": (r"\bizquierda\b", r"\bleft\b"),
    "right": (r"\bderecha\b", r"\bright\b"),
    "front": (r"\bdelante\b", r"\b(?:ahead|in front)\b"),
    "behind": (r"\bdetr[aá]s\b", r"\bbehind\b"),
}


class F57Error(ValueError):
    pass


def prepare_variant_inputs(streetview: Mapping[str, Any], catalog50: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if streetview.get("dataset_id") != "f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a":
        raise F57Error("F5.7 exige el dataset F5.6 canónico 575695ca")
    queries, observations = [], []
    for row in streetview["observations"]:
        qid, text = row["observation_id"], row["description"]["text"]
        if COORD_RE.search(text) or row["provenance"]["panorama_id"] in text:
            raise F57Error("la descripción F5.6 contiene una fuga")
        query = {
            "query_id": qid,
            "location_id": f"documentary-{qid}",
            "derivation_group_id": f"documentary-{qid}",
            "partition": "development",
            "description": {"text": text, "language": "es", "contains_coordinates": False},
            "provenance": {
                "source_type": "existing_dataset",
                "description": "Descripción documental F5.6; referencia aproximada reservada para F5.7.",
                "independent_environment_observation": False,
                "instructions_version": "f57-provisional-v1",
                "collected_at_utc": None,
            },
            "reference": {"status": "pending", "latitude": None, "longitude": None, "crs": None, "capture_method": None, "reported_accuracy_m": None, "validation_method": None, "catalog_assignment": None},
            "ambiguity": {"status": "unreviewed", "notes": "La coordenada de enlace no forma parte de la entrada del modelo."},
            "validation_status": "pending",
        }
        queries.append(query)

        def pending(kind: str, language: str) -> dict[str, Any]:
            return {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": language, "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}

        original = {"variant_id": f"{qid}-es-original-f57-v1", "kind": "es_original", "status": "reviewed", "text": text, "language": "es", "generation": {"method": "original", "tool_or_model": "manual", "version": "f56-canonical", "configuration_or_prompt": "copy-from-f56", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        relative = any(re.search(pattern, text, re.I) for patterns in RELATIONS.values() for pattern in patterns)
        observations.append({
            "source_query_id": qid,
            "source_input_sha256": "0" * 64,
            "partition": "development",
            "location_id": f"documentary-{qid}",
            "derivation_group_id": f"documentary-{qid}",
            "toponyms": [],
            "orientation": {"status": "reported", "cardinal": None, "bearing_degrees": row["view"]["heading_degrees"], "bearing_convention": "degrees_clockwise_from_true_north", "method": "streetview_url_heading_unverified", "uncertainty_degrees": 180.0, "provenance": "f56_documentary_url", "verification_status": "pending", "relative_relations_present": relative, "notes": "Heading de cámara; no orientación corporal verificada."},
            "variants": [original, pending("es_cartographic", "es"), pending("en_conventional", "en"), pending("en_toponym_preserved", "en"), pending("en_cartographic", "en")],
            "notes": "F5.7 provisional; revisión humana F5.6 pendiente.",
        })

    dataset = {
        "schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "", "dataset_version": "f57-streetview-provisional-v1",
        "region": {"region_id": catalog50.region_id, "bbox_wgs84": dict(catalog50.region_bbox_wgs84)},
        "catalog": {"manifest_id": catalog50.manifest_id, "manifest_sha256": catalog50.sha256, "candidate_count": len(catalog50.candidates), "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"},
        "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": 0.8},
        "queries": queries,
    }
    dataset["dataset_id"] = query_dataset_id(dataset)
    query_by = {query["query_id"]: query for query in queries}
    for observation in observations:
        observation["source_input_sha256"] = source_query_input_sha256(query_by[observation["source_query_id"]])
    template_path = Path(__file__).resolve().parents[2] / "config/madrid_f53b_textual_variants_template.json"
    sidecar = json.loads(template_path.read_text(encoding="utf-8"))
    sidecar["dataset_version"] = "f57-streetview-provisional-v1"
    source_raw = canonical_bytes(dataset) + b"\n"
    sidecar["source_query_dataset"] = {"dataset_id": dataset["dataset_id"], "sha256": hashlib.sha256(source_raw).hexdigest()}
    sidecar["observations"] = observations
    sidecar["dataset_id"] = textual_variant_dataset_id(sidecar)
    return dataset, sidecar


def audit_variants(sidecar: Mapping[str, Any], run: Mapping[str, Any]) -> dict[str, Any]:
    records = {(row["source_query_id"], row["kind"]): row for row in run["records"]}
    issues, eligible = [], []
    for observation in sidecar["observations"]:
        original = next(value for value in observation["variants"] if value["kind"] == "es_original")
        for variant in observation["variants"]:
            text, codes = variant["text"] or "", []
            if COORD_RE.search(text):
                codes.append("coordinate_leak")
            if variant["kind"] != "es_original" and INTERNAL_RE.search(text):
                codes.append("internal_or_panorama_id_leak")
            if variant["kind"] != "es_original":
                record = records.get((observation["source_query_id"], variant["kind"]))
                if record is None or record["output_text_sha256"] != _sha256_text(text):
                    codes.append("transformation_record_mismatch")
                elif not record["validation"]["structurally_valid"]:
                    codes.append("automatic_validation_failed")
                if bool(NEG_ES.search(original["text"])) != bool(NEG_ES.search(text) or NEG_EN.search(text)):
                    codes.append("negation_changed")
                for name, patterns in RELATIONS.items():
                    if re.search(patterns[0], original["text"], re.I) and not any(re.search(pattern, text, re.I) for pattern in patterns):
                        codes.append(f"relation_lost:{name}")
            allowed = not codes and variant["status"] in {"reviewed", "generated"} and bool(text)
            if allowed:
                eligible.append({"source_query_id": observation["source_query_id"], "variant_kind": variant["kind"]})
            issues.append({"source_query_id": observation["source_query_id"], "variant_id": variant["variant_id"], "variant_kind": variant["kind"], "description_review_status": "reviewed" if variant["kind"] == "es_original" else "pending", "automatic_checks_passed": not codes, "experimental_execution_allowed": allowed, "official_evaluation_eligible": False, "issue_codes": codes})
    return {"schema_version": "1.0", "contract_version": "f57-variant-audit-v1", "issues": issues, "eligible_pairs": eligible, "limitations": ["automatic_checks_do_not_replace_human_semantic_review", "provisional_execution_only", "not_f54_ground_truth"]}


def run_provisional_rankings(sidecar: Mapping[str, Any], audit: Mapping[str, Any], retriever: Any, *, gallery_ids: Sequence[str], top_k: int = 10) -> dict[str, Any]:
    if tuple(sorted(gallery_ids)) != GALLERIES or top_k != 10:
        raise F57Error("F5.7 exige ambas galerías y Top-10")
    eligible = {(row["source_query_id"], row["variant_kind"]) for row in audit["eligible_pairs"]}
    rows, checkpoint = [], None
    for observation in sidecar["observations"]:
        for variant in observation["variants"]:
            if (observation["source_query_id"], variant["kind"]) not in eligible:
                continue
            started=time.perf_counter(); response = retriever.retrieve_many(gallery_ids=gallery_ids, query_id=variant["variant_id"], text=variant["text"], language=variant["language"], k=top_k); elapsed=(time.perf_counter()-started)*1000
            current = response["model"]["checkpoint_sha256"]
            checkpoint = current if checkpoint is None else checkpoint
            if checkpoint != current:
                raise F57Error("checkpoint cambió durante rankings")
            for retrieval in response["retrievals"]:
                _validate_ranking_results(retrieval)
                rows.append({"source_query_id": observation["source_query_id"], "variant_id": variant["variant_id"], "variant_kind": variant["kind"], "language": variant["language"], "text_sha256": _sha256_text(variant["text"]), "gallery_id": retrieval["gallery_id"], "top_k": 10, "results": retrieval["results"], "retrieval_ms": response["timings_ms"]["total"], "pipeline_elapsed_ms": elapsed})
    document = {"schema_version": "1.0", "contract_version": "f57-provisional-rankings-v1", "ranking_id": RANKING_PREFIX + "0" * 64, "checkpoint_sha256": checkpoint or "0" * 64, "gallery_ids": list(gallery_ids), "ranking_method": "exhaustive_cosine", "top_k": 10, "rows": rows, "limitations": ["unreviewed_model_variants_included_only_after_automatic_checks", "no_official_ground_truth", "coordinates_not_used_for_retrieval"]}
    document["ranking_id"] = ranking_id(document)
    return document


def ranking_id(document: Mapping[str, Any]) -> str:
    semantic_rows = list(document["rows"])
    identity = {key: document[key] for key in ("contract_version", "checkpoint_sha256", "gallery_ids", "ranking_method", "top_k", "limitations")}
    identity["rows"] = semantic_rows
    return RANKING_PREFIX + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def evaluate_approximate(streetview: Mapping[str, Any], rankings: Mapping[str, Any], *, streetview_sha256: str, variants_sha256: str, rankings_sha256: str) -> dict[str, Any]:
    if rankings.get("ranking_id") != ranking_id(rankings):
        raise F57Error("identidad de rankings inválida")
    references = {row["observation_id"]: row for row in streetview["observations"]}
    indexed = {(row["source_query_id"], row["variant_kind"], row["gallery_id"]): row for row in rankings["rows"]}
    per_observation = []
    for qid, reference in sorted(references.items()):
        for kind in KINDS:
            for gallery in GALLERIES:
                ranking = indexed.get((qid, kind, gallery))
                assignment = reference["geography"]["link_point_assignments"][gallery]
                candidate = assignment.get("candidate_id")
                if assignment.get("status") != "assigned" or not candidate:
                    raise F57Error("referencia aproximada sin asignación inequívoca")
                if ranking is None:
                    per_observation.append({"source_query_id": qid, "variant_kind": kind, "gallery_id": gallery, "status": "missing_or_invalid_variant", "reference_candidate_id": candidate})
                    continue
                _validate_row(ranking)
                exact_rank = next((row["rank"] for row in ranking["results"] if row["candidate_id"] == candidate), None)
                distances = [haversine_m(reference["link_coordinate"]["latitude"], reference["link_coordinate"]["longitude"], row["latitude"], row["longitude"]) for row in ranking["results"]]
                per_observation.append({"source_query_id": qid, "variant_kind": kind, "gallery_id": gallery, "status": "evaluated_experimental_approximate_reference", "reference_candidate_id": candidate, "exact_rank": exact_rank, "hits_at_k": {str(k): exact_rank is not None and exact_rank <= k for k in (1, 5, 10)}, "top1_error_m": distances[0], "minimum_error_at_k_m": {str(k): min(distances[:k]) for k in (1, 5, 10)}, "geo_hits": {str(k): {str(threshold): min(distances[:k]) <= threshold for threshold in (25, 50, 100)} for k in (1, 5, 10)}, "top10_ids": [row["candidate_id"] for row in ranking["results"]], "retrieval_ms": ranking["retrieval_ms"], "pipeline_elapsed_ms": ranking["pipeline_elapsed_ms"]})
    metrics = [aggregate_metric(gallery, kind, [row for row in per_observation if row["gallery_id"] == gallery and row["variant_kind"] == kind and row["status"].startswith("evaluated")]) for gallery in GALLERIES for kind in KINDS]
    document = {
        "schema_version": "1.0", "contract_version": "f57-experimental-approximate-evaluation-v1", "evaluation_id": EVALUATION_PREFIX + "0" * 64,
        "protocol": {"reference_kind": "experimental_approximate_reference", "official_f54_evaluation": False, "ks": [1, 5, 10], "geo_thresholds_m": [25, 50, 100], "sample_size": 4, "recall_increment_per_hit": 0.25, "coordinates_used_for_retrieval": False},
        "inputs": {"streetview_dataset_id": streetview["dataset_id"], "streetview_sha256": streetview_sha256, "variants_sha256": variants_sha256, "rankings_sha256": rankings_sha256},
        "coverage": {"observations": 4, "expected_rankings": 40, "observed_rankings": len(rankings["rows"]), "officially_evaluable": 0},
        "metrics": metrics, "paired_comparisons": paired_comparisons(per_observation), "per_observation": per_observation,
        "limitations": ["approximate_link_coordinates_unknown_uncertainty", "not_official_ground_truth", "not_f54_metrics", "small_non_independent_sample", "unreviewed_qwen_variants_excluded_from_official_conclusions", "no_vlm", "no_finetuning", "frozen_embeddings"],
    }
    document["evaluation_id"] = evaluation_id(document)
    return document


def aggregate_metric(gallery: str, kind: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count, errors = len(rows), [row["top1_error_m"] for row in rows]
    return {"gallery_id": gallery, "variant_kind": kind, "evaluated_count": count, "recall_at_k": {str(k): {"hits": sum(row["hits_at_k"][str(k)] for row in rows), "total": count, "value": sum(row["hits_at_k"][str(k)] for row in rows) / count if count else None} for k in (1, 5, 10)}, "geo_recall_at_k": {str(k): {str(threshold): sum(row["geo_hits"][str(k)][str(threshold)] for row in rows) / count if count else None for threshold in (25, 50, 100)} for k in (1, 5, 10)}, "top1_error_m": {"mean": statistics.fmean(errors) if errors else None, "median": statistics.median(errors) if errors else None}, "minimum_top10_error_m": {"mean": statistics.fmean(row["minimum_error_at_k_m"]["10"] for row in rows) if rows else None, "median": statistics.median(row["minimum_error_at_k_m"]["10"] for row in rows) if rows else None}, "retrieval_latency_ms":{"mean":statistics.fmean(row["retrieval_ms"] for row in rows) if rows else None,"median":statistics.median(row["retrieval_ms"] for row in rows) if rows else None},"pipeline_elapsed_ms":{"mean":statistics.fmean(row["pipeline_elapsed_ms"] for row in rows) if rows else None,"median":statistics.median(row["pipeline_elapsed_ms"] for row in rows) if rows else None}}


def paired_comparisons(per_observation: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    index = {(row["source_query_id"], row["gallery_id"], row["variant_kind"]): row for row in per_observation if row["status"].startswith("evaluated")}
    output = []
    for gallery in GALLERIES:
        for kind in KINDS[1:]:
            cases = []
            for qid in sorted({key[0] for key in index}):
                anchor, variant = index.get((qid, gallery, "es_original")), index.get((qid, gallery, kind))
                if not anchor or not variant:
                    continue
                left, right = set(anchor["top10_ids"]), set(variant["top10_ids"])
                cases.append({"source_query_id": qid, "top1_agreement": anchor["top10_ids"][0] == variant["top10_ids"][0], "jaccard_at_10": len(left & right) / len(left | right), "top1_error_delta_m": variant["top1_error_m"] - anchor["top1_error_m"]})
            output.append({"gallery_id": gallery, "variant_kind": kind, "paired_count": len(cases), "top1_agreement_rate": statistics.fmean(case["top1_agreement"] for case in cases) if cases else None, "mean_jaccard_at_10": statistics.fmean(case["jaccard_at_10"] for case in cases) if cases else None, "mean_top1_error_delta_m": statistics.fmean(case["top1_error_delta_m"] for case in cases) if cases else None, "cases": cases})
    return output


def render_html(document: Mapping[str, Any], output: Path) -> None:
    rows = []
    for metric in document["metrics"]:
        recall = metric["recall_at_k"]
        mean = metric["top1_error_m"]["mean"]
        latency=metric["retrieval_latency_ms"]
        rows.append(f"<tr><td>{escape(metric['gallery_id'])}</td><td>{escape(metric['variant_kind'])}</td><td>{metric['evaluated_count']}</td><td>{recall['1']['hits']}/{recall['1']['total']} ({_pct(recall['1']['value'])})</td><td>{recall['5']['hits']}/{recall['5']['total']} ({_pct(recall['5']['value'])})</td><td>{recall['10']['hits']}/{recall['10']['total']} ({_pct(recall['10']['value'])})</td><td>{_pct(metric['geo_recall_at_k']['10']['50'])}</td><td>{_pct(metric['geo_recall_at_k']['10']['100'])}</td><td>{mean:.2f} m</td><td>{metric['minimum_top10_error_m']['mean']:.2f} m</td><td>{latency['mean']:.2f}/{latency['median']:.2f} ms</td></tr>" if mean is not None else f"<tr><td>{escape(metric['gallery_id'])}</td><td>{escape(metric['variant_kind'])}</td><td>0</td><td colspan=8>no disponible</td></tr>")
    individual=[]
    for row in document["per_observation"]:
        if not row["status"].startswith("evaluated"): continue
        individual.append(f"<tr><td>{escape(row['source_query_id'])}</td><td>{escape(row['gallery_id'])}</td><td>{escape(row['variant_kind'])}</td><td>{escape(str(row['exact_rank']))}</td><td>{row['top1_error_m']:.2f} m</td><td>{row['minimum_error_at_k_m']['10']:.2f} m</td><td>{row['retrieval_ms']:.2f} ms</td></tr>")
    paired=[]
    for row in document["paired_comparisons"]:
        paired.append(f"<tr><td>{escape(row['gallery_id'])}</td><td>{escape(row['variant_kind'])}</td><td>{row['paired_count']}</td><td>{_pct(row['top1_agreement_rate'])}</td><td>{row['mean_jaccard_at_10']:.3f}</td><td>{row['mean_top1_error_delta_m']:.2f} m</td></tr>")
    html = f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>F5.7 experimental</title><style>body{{font:16px system-ui;max-width:1400px;margin:auto;padding:2rem;background:#f3efe7;color:#172121}}h1{{border-bottom:5px solid #b34b24}}table{{border-collapse:collapse;width:100%;background:white;margin-bottom:2rem}}th,td{{padding:.5rem;border:1px solid #bbb;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}.warning{{padding:1rem;background:#ffe1b8;border-left:6px solid #b34b24}}code{{overflow-wrap:anywhere}}</style></head><body><h1>F5.7: evaluación experimental aproximada</h1><p class='warning'><strong>No son métricas oficiales F5.4.</strong> La referencia es una coordenada de enlace Street View con incertidumbre desconocida. No se utilizó para retrieval.</p><p>Rankings observados: {document['coverage']['observed_rankings']}/40. Casos oficialmente evaluables: 0. Cada acierto equivale a 25 puntos porcentuales.</p><h2>Agregados</h2><table><thead><tr><th>Galería</th><th>Variante</th><th>n</th><th>Recall@1 aprox.</th><th>Recall@5 aprox.</th><th>Recall@10 aprox.</th><th>Geo@10 50 m</th><th>Geo@10 100 m</th><th>Error Top-1 medio</th><th>Mínimo Top-10 medio</th><th>Latencia media/mediana</th></tr></thead><tbody>{''.join(rows)}</tbody></table><h2>Comparación frente a es_original</h2><table><thead><tr><th>Galería</th><th>Variante</th><th>n pareado</th><th>Acuerdo Top-1</th><th>Jaccard@10</th><th>Delta error Top-1</th></tr></thead><tbody>{''.join(paired)}</tbody></table><h2>Resultados individuales</h2><table><thead><tr><th>Observación</th><th>Galería</th><th>Variante</th><th>Rango celda</th><th>Error Top-1</th><th>Mínimo Top-10</th><th>Latencia</th></tr></thead><tbody>{''.join(individual)}</tbody></table><p><code>{escape(document['evaluation_id'])}</code></p></body></html>"
    output.write_text(html, encoding="utf-8")


def evaluation_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "protocol", "inputs", "coverage", "metrics", "paired_comparisons", "per_observation", "limitations")}
    return EVALUATION_PREFIX + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def _validate_ranking_results(retrieval: Mapping[str, Any]) -> None:
    if retrieval.get("effective_k") != 10 or retrieval.get("ranking_method") != "exhaustive_cosine" or retrieval.get("tie_break") != "candidate_id_ascending":
        raise F57Error("ranking provisional incompatible")
    results = retrieval.get("results", [])
    if len(results) != 10 or [row.get("rank") for row in results] != list(range(1, 11)) or len({row.get("candidate_id") for row in results}) != 10:
        raise F57Error("ranking Top-10 incompleto, duplicado o desordenado")
    for previous, current in zip(results, results[1:]):
        if current["cosine_similarity"] > previous["cosine_similarity"] or (current["cosine_similarity"] == previous["cosine_similarity"] and current["candidate_id"] < previous["candidate_id"]):
            raise F57Error("ranking no respeta score/desempate")


def _validate_row(row: Mapping[str, Any]) -> None:
    if row.get("top_k") != 10 or row.get("gallery_id") not in GALLERIES or not math.isfinite(row.get("retrieval_ms",float("nan"))) or not math.isfinite(row.get("pipeline_elapsed_ms",float("nan"))):
        raise F57Error("fila de ranking incompatible")
    results = row.get("results", [])
    if len(results) != 10 or [value.get("rank") for value in results] != list(range(1, 11)) or len({value.get("candidate_id") for value in results}) != 10:
        raise F57Error("ranking Top-10 incompleto")
    if any(not math.isfinite(value[field]) for value in results for field in ("latitude", "longitude", "cosine_similarity")):
        raise F57Error("ranking contiene valores no finitos")


def _pct(value: float | None) -> str:
    return "no disponible" if value is None else f"{100 * value:.1f} %"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
