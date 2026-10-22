"""Consolidación post hoc F5.10 sobre rankings F5.9 congelados."""

from __future__ import annotations

from collections import Counter
import hashlib
from html import escape
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence

from .f4_evaluation import haversine_m


KINDS = ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved", "en_cartographic")
GALLERIES = ("madrid-25m", "madrid-50m")
PREFIX = "f510-consolidation-sha256-"


class F510Error(ValueError): pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def verify_manifest(path: Path, root: Path) -> dict[str, Any]:
    document = json.loads(path.read_text())
    mismatches = []
    for name, artifact in document.get("artifacts", {}).items():
        target = root / artifact["logical_path"]
        if not target.is_file() or target.stat().st_size != artifact["size_bytes"] or _digest(target) != artifact["sha256"]: mismatches.append(name)
    if mismatches: raise F510Error(f"manifest incompatible: {path}: {mismatches}")
    return {"logical_path": str(path.resolve().relative_to(root)), "sha256": _digest(path), "artifact_count": len(document["artifacts"]), "mismatches": []}


def consolidate(h03_h10: Mapping[str, Any], h01_h10: Mapping[str, Any], f56: Mapping[str, Any], h01_h02_dataset: Mapping[str, Any], h03_h10_dataset: Mapping[str, Any], *, input_hashes: Mapping[str, str]) -> dict[str, Any]:
    subsets = {
        "h03_h10": _consolidate_rows(h03_h10["per_observation"], tuple(f"H{i:02d}" for i in range(3, 11))),
        "h01_h10": _consolidate_rows(h01_h10["per_observation"], tuple(f"H{i:02d}" for i in range(1, 11))),
    }
    overlaps = audit_overlaps(f56, h01_h02_dataset, h03_h10_dataset)
    document = {
        "schema_version": "1.0", "contract_version": "f510-metric-consolidation-v1", "consolidation_id": "",
        "protocol": {"primary_metric_order": ["geo_recall_at_10_50m", "geo_recall_at_10_100m", "recall_at_10_exact", "minimum_top10_error_m"], "baseline": "es_original", "galleries_combined_as_independent_samples": False, "official_f54_evaluation": False, "models_executed": False, "wilson_interval_confidence": 0.95},
        "inputs": dict(input_hashes), "subsets": subsets, "f57_overlap_audit": overlaps,
        "limitations": ["ten_human_observations", "panorama_coordinates_unknown_uncertainty", "h01_not_exactly_assignable", "h01_h10_used_for_development_not_blind_validation", "f57_and_f59_not_independent", "wilson_intervals_descriptive_only", "heading_not_model_input", "qwen_outputs_not_human_semantically_approved"],
    }
    document["consolidation_id"] = PREFIX + hashlib.sha256(canonical_bytes({key: document[key] for key in document if key != "consolidation_id"})).hexdigest()
    return document


def _consolidate_rows(rows: Sequence[Mapping[str, Any]], query_ids: Sequence[str]) -> dict[str, Any]:
    expected = {(qid, gallery, kind) for qid in query_ids for gallery in GALLERIES for kind in KINDS}
    index = {(row["source_query_id"], row["gallery_id"], row["kind"]): row for row in rows if row["kind"] in KINDS}
    if set(index) != expected or len(index) != len([row for row in rows if row["kind"] in KINDS]): raise F510Error("producto cartesiano F5.9 incompleto o duplicado")
    normalized = [_normalize_row(index[key]) for key in sorted(index)]
    return {"observation_ids": list(query_ids), "observation_count": len(query_ids), "metrics": _metrics(normalized), "paired_comparisons": _paired(normalized, query_ids), "individual_comparisons": _individual(normalized, query_ids)}


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    candidates = row["candidates"]
    if len(candidates) != 10 or [item["rank"] for item in candidates] != list(range(1, 11)): raise F510Error("candidatas Top-10 inválidas")
    nearest = min(candidates, key=lambda item: item["distance_to_panorama_reference_m"])
    top1_distance = candidates[0]["distance_to_panorama_reference_m"]
    exact_available = bool(row["exact_recall_available"])
    exact_rank = row.get("exact_rank")
    return {"source_query_id": row["source_query_id"], "gallery_id": row["gallery_id"], "kind": row["kind"], "exact_available": exact_available, "exact_rank": exact_rank, "recall1": exact_rank == 1 if exact_available else None, "recall10": exact_rank is not None and exact_rank <= 10 if exact_available else None, "geo1_50": top1_distance <= 50, "geo1_100": top1_distance <= 100, "geo10_50": nearest["distance_to_panorama_reference_m"] <= 50, "geo10_100": nearest["distance_to_panorama_reference_m"] <= 100, "top1_candidate_id": candidates[0]["candidate_id"], "top1_error_m": top1_distance, "minimum_top10_error_m": nearest["distance_to_panorama_reference_m"], "nearest_candidate_rank": nearest["rank"]}


def _metrics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for gallery in GALLERIES:
        for kind in KINDS:
            selected = [row for row in rows if row["gallery_id"] == gallery and row["kind"] == kind]
            exact = [row for row in selected if row["exact_available"]]
            minimums = [row["minimum_top10_error_m"] for row in selected]
            output.append({"gallery_id": gallery, "kind": kind, "observations": len(selected), "geo_recall_at_10": {"50": _rate(selected, "geo10_50"), "100": _rate(selected, "geo10_100")}, "recall_at_10_exact": _rate(exact, "recall10"), "minimum_top10_error_m": _summary(minimums), "geo_recall_at_1": {"50": _rate(selected, "geo1_50"), "100": _rate(selected, "geo1_100")}, "recall_at_1_exact": _rate(exact, "recall1"), "top1_error_m": _summary([row["top1_error_m"] for row in selected]), "nearest_candidate_rank": {"mean": statistics.fmean(row["nearest_candidate_rank"] for row in selected), "median": statistics.median(row["nearest_candidate_rank"] for row in selected), "histogram": {str(rank): sum(row["nearest_candidate_rank"] == rank for row in selected) for rank in range(1, 11)}}})
    return output


def _paired(rows: Sequence[Mapping[str, Any]], query_ids: Sequence[str]) -> list[dict[str, Any]]:
    index = {(row["source_query_id"], row["gallery_id"], row["kind"]): row for row in rows}; output = []
    for gallery in GALLERIES:
        for kind in KINDS[1:]:
            cases = [_pair_case(index[(qid, gallery, "es_original")], index[(qid, gallery, kind)]) for qid in query_ids]
            output.append({"gallery_id": gallery, "kind": kind, "count": len(cases), "geo_recall_at_10": {radius: _transitions(cases, f"geo10_{radius}") for radius in ("50", "100")}, "minimum_top10_error_m": {"improved": sum(row["minimum_delta_m"] < -1e-9 for row in cases), "worsened": sum(row["minimum_delta_m"] > 1e-9 for row in cases), "tied": sum(abs(row["minimum_delta_m"]) <= 1e-9 for row in cases), "mean_delta_m": statistics.fmean(row["minimum_delta_m"] for row in cases), "deltas_by_query": [{"source_query_id": row["source_query_id"], "delta_m": row["minimum_delta_m"]} for row in cases]}, "recall_at_10_exact": _exact_transitions(cases, "recall10"), "geo_recall_at_1": {radius: _transitions(cases, f"geo1_{radius}") for radius in ("50", "100")}, "recall_at_1_exact": _exact_transitions(cases, "recall1"), "top1": {"candidate_changed": sum(row["top1_candidate_changed"] for row in cases), "candidate_unchanged": sum(not row["top1_candidate_changed"] for row in cases), "error_improved": sum(row["top1_delta_m"] < -1e-9 for row in cases), "error_worsened": sum(row["top1_delta_m"] > 1e-9 for row in cases), "error_tied": sum(abs(row["top1_delta_m"]) <= 1e-9 for row in cases), "mean_error_delta_m": statistics.fmean(row["top1_delta_m"] for row in cases)}, "cases": cases})
    return output


def _pair_case(anchor: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    fields = {name: {"baseline": anchor[name], "variant": variant[name]} for name in ("geo10_50", "geo10_100", "geo1_50", "geo1_100", "recall10", "recall1")}
    return {"source_query_id": anchor["source_query_id"], **fields, "exact_available": anchor["exact_available"] and variant["exact_available"], "minimum_delta_m": variant["minimum_top10_error_m"] - anchor["minimum_top10_error_m"], "top1_candidate_changed": variant["top1_candidate_id"] != anchor["top1_candidate_id"], "top1_delta_m": variant["top1_error_m"] - anchor["top1_error_m"]}


def _individual(rows: Sequence[Mapping[str, Any]], query_ids: Sequence[str]) -> list[dict[str, Any]]:
    index = {(row["source_query_id"], row["gallery_id"], row["kind"]): row for row in rows}; output = []
    for qid in query_ids:
        for gallery in GALLERIES:
            anchor = index[(qid, gallery, "es_original")]
            for kind in KINDS:
                row = index[(qid, gallery, kind)]
                output.append({"source_query_id": qid, "gallery_id": gallery, "kind": kind, "geo10_50": row["geo10_50"], "geo10_100": row["geo10_100"], "recall10": row["recall10"], "minimum_top10_error_m": row["minimum_top10_error_m"], "minimum_delta_vs_original_m": row["minimum_top10_error_m"] - anchor["minimum_top10_error_m"], "geo1_50": row["geo1_50"], "geo1_100": row["geo1_100"], "recall1": row["recall1"], "top1_error_m": row["top1_error_m"], "top1_delta_vs_original_m": row["top1_error_m"] - anchor["top1_error_m"], "nearest_candidate_rank": row["nearest_candidate_rank"]})
    return output


def audit_overlaps(f56: Mapping[str, Any], h01_h02: Mapping[str, Any], h03_h10: Mapping[str, Any]) -> dict[str, Any]:
    old = [{"id": row["observation_id"], "panorama_id": row["provenance"]["panorama_id"], "latitude": row["link_coordinate"]["latitude"], "longitude": row["link_coordinate"]["longitude"]} for row in f56["observations"]]
    new = [{"id": row["observation_id"], "panorama_id": row["panorama"]["panorama_id"], "latitude": row["panorama_coordinate"]["latitude"], "longitude": row["panorama_coordinate"]["longitude"]} for dataset in (h01_h02, h03_h10) for row in dataset["observations"]]
    pairs = []
    for left in old:
        for right in new:
            distance = haversine_m(left["latitude"], left["longitude"], right["latitude"], right["longitude"])
            if left["panorama_id"] == right["panorama_id"] or distance <= 25:
                pairs.append({"f57_observation_id": left["id"], "f59_observation_id": right["id"], "same_panorama": left["panorama_id"] == right["panorama_id"], "distance_m": distance, "independent_evidence": False if left["panorama_id"] == right["panorama_id"] or distance <= 15 else "spatial_proximity_requires_caution"})
    return {"pairs_within_25m_or_same_panorama": pairs, "exact_panorama_duplicates": sum(row["same_panorama"] for row in pairs), "policy": "never_sum_f57_and_f59_denominators_or_present_as_independent_samples"}


def render_html(document: Mapping[str, Any], output: Path) -> None:
    sections = []
    for subset_name, subset in document["subsets"].items():
        rows = []
        for metric in subset["metrics"]:
            rows.append(f"<tr><td>{escape(metric['gallery_id'])}</td><td>{escape(metric['kind'])}</td><td>{_fmt_rate(metric['geo_recall_at_10']['50'])}</td><td>{_fmt_rate(metric['geo_recall_at_10']['100'])}</td><td>{_fmt_rate(metric['recall_at_10_exact'])}</td><td>{metric['minimum_top10_error_m']['mean']:.2f}</td><td>{metric['minimum_top10_error_m']['median']:.2f}</td><td>{_fmt_rate(metric['geo_recall_at_1']['50'])}</td><td>{_fmt_rate(metric['geo_recall_at_1']['100'])}</td><td>{_fmt_rate(metric['recall_at_1_exact'])}</td><td>{metric['top1_error_m']['mean']:.2f}</td></tr>")
        sections.append(f"<h2>{escape(subset_name)}</h2><table><tr><th>Galería</th><th>Variante</th><th>Geo10 50</th><th>Geo10 100</th><th>R10</th><th>Mín10 media</th><th>Mediana</th><th>Geo1 50</th><th>Geo1 100</th><th>R1</th><th>Top1 media</th></tr>{''.join(rows)}</table>")
    output.write_text(f"<!doctype html><html lang='es'><meta charset='utf-8'><title>F5.10</title><style>body{{font:15px system-ui;max-width:1500px;margin:auto;padding:2rem}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #aaa;padding:.35rem}}</style><h1>F5.10: consolidación F5.9</h1><p>No es evaluación F5.4. Las galerías se informan por separado.</p>{''.join(sections)}</html>", encoding="utf-8")


def _rate(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    hits, total = sum(bool(row[field]) for row in rows), len(rows)
    leave_one_out = sorted({(hits - int(bool(row[field]))) / (total - 1) for row in rows}) if total > 1 else []
    return {"hits": hits, "total": total, "value": hits / total if total else None, "wilson_95": _wilson(hits, total), "leave_one_out_range": [min(leave_one_out), max(leave_one_out)] if leave_one_out else None}
def _wilson(hits: int, total: int) -> list[float] | None:
    if not total: return None
    z=1.959963984540054; p=hits/total; den=1+z*z/total; center=(p+z*z/(2*total))/den; half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0.0,center-half),min(1.0,center+half)]
def _summary(values: Sequence[float]) -> dict[str, Any]: return {"count": len(values), "mean": statistics.fmean(values), "median": statistics.median(values), "minimum": min(values), "maximum": max(values), "values": list(values)}
def _transitions(cases, field):
    pairs=[(row[field]["baseline"],row[field]["variant"]) for row in cases]
    return {"failure_to_hit":sum(not a and b for a,b in pairs),"hit_to_failure":sum(a and not b for a,b in pairs),"unchanged":sum(a==b for a,b in pairs),"total":len(pairs)}
def _exact_transitions(cases, field):
    available=[row for row in cases if row["exact_available"]]; result=_transitions(available,field); result["unavailable"]=len(cases)-len(available); return result
def _fmt_rate(rate): return "n/d" if rate["value"] is None else f"{rate['hits']}/{rate['total']} ({rate['value']:.3f})"
def _digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
