"""Extensión F5.9 H03-H10 para descripciones humanas con relaciones egocéntricas."""

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

from .f4_evaluation import assign_reference, haversine_m, query_dataset_id
from .f5_textual_variants import source_query_input_sha256, textual_variant_dataset_id
from .f57_experimental_evaluation import COORD_RE, INTERNAL_RE, RELATIONS, audit_variants, canonical_bytes
from .f59_human_streetview import GALLERIES, _validate_results


KINDS = ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved", "en_cartographic")
DATASET_PREFIX = "f59-oriented-streetview-sha256-"
RANKING_PREFIX = "f59-oriented-rankings-sha256-"
EVALUATION_PREFIX = "f59-oriented-evaluation-sha256-"
COMBINED_PREFIX = "f59-h01-h10-evaluation-sha256-"
RELATION_PATTERNS = {
    "left": (r"\bizquierda\b", r"\bleft\b"),
    "right": (r"\bderecha\b", r"\bright\b"),
    "front": (r"\b(?:delante|frente|en frente)\b", r"\b(?:ahead|front|facing)\b"),
    "behind": (r"\bdetr[aá]s\b", r"\bbehind\b"),
}


class F59ExtensionError(ValueError): pass


def dataset_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "protocol", "catalogs", "observations", "limitations")}
    return DATASET_PREFIX + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def build_dataset(spec: Mapping[str, Any], catalogs: Mapping[str, Any]) -> dict[str, Any]:
    expected = [f"H{index:02d}" for index in range(3, 11)]
    if spec.get("contract_version") != "f59-oriented-streetview-input-v1" or spec.get("reference_policy") != "panorama_coordinate_experimental_unknown_uncertainty" or [row.get("observation_id") for row in spec.get("observations", [])] != expected or set(catalogs) != set(GALLERIES): raise F59ExtensionError("especificación H03-H10 incompatible")
    observations = []
    bbox = next(iter(catalogs.values())).region_bbox_wgs84
    for source in spec["observations"]:
        text, panorama_id = source["spanish_text"], source["panorama_id"]
        if COORD_RE.search(text) or panorama_id in text or INTERNAL_RE.search(text): raise F59ExtensionError("texto orientado contiene fuga")
        coordinate = _coordinate(source["panorama_coordinate"])
        heading, pitch = source["heading_degrees"], source["pitch_degrees"]
        if not _range(heading, 0, 360, False) or not _range(pitch, -90, 90, True): raise F59ExtensionError("heading o pitch inválido")
        toponyms = []
        for item in source["proper_toponyms"]:
            mention = item["mention"]; matches = list(re.finditer(re.escape(mention), text))
            if len(matches) != 1 or item["entity_type"] not in {"poi", "building", "station", "other"}: raise F59ExtensionError("nombre propio ausente, duplicado o mal tipado")
            match = matches[0]; toponyms.append({"mention": mention, "span": {"start": match.start(), "end": match.end()}, "entity_type": item["entity_type"], "name_kind": "proper_name", "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"})
        relations = _relations(text)
        audit = source["osm_carto_audit"]
        documented_relations = {_relation_label(value) for value in audit.get("egocentric_relations_not_encoded", [])}
        if audit.get("classification") not in {"partially_representable", "mostly_visual"} or not audit.get("potentially_representable") or not audit.get("not_guaranteed_in_raster") or documented_relations != relations: raise F59ExtensionError("auditoría OSM Carto u orientación incompatible")
        observations.append({"observation_id": source["observation_id"], "source_type": "human_description_streetview_reference", "texts": {"es_original": {"text": text, "language": "es", "source": "human_tfg_owner", "frozen_before_qwen_and_retrieval": True}}, "toponyms": toponyms, "panorama_coordinate": {**coordinate, "meaning": "coordinate_embedded_in_streetview_link", "camera_position_independently_verified": False, "positional_uncertainty": "unknown"}, "panorama": {"provider": "Google Street View", "panorama_id": panorama_id, "heading_degrees": heading, "pitch_degrees": pitch, "heading_is_camera_not_body_orientation": True}, "orientation_audit": {"relations_in_text": sorted(relations), "heading_recorded_but_not_model_input": True, "cardinal_directions_inferred": False, "visual_consistency_review_status": "pending"}, "osm_carto_audit": audit, "geography": {"experimental_reference_role": "panorama_coordinate", "official_f54_ground_truth": False, "panorama_coordinate_inside_d004": _inside(coordinate, bbox), "panorama_reference_assignments": {gallery: assign_reference(coordinate["latitude"], coordinate["longitude"], catalog) for gallery, catalog in catalogs.items()}}, "review": {"status": "pending", "description_visual_correspondence_verified": False, "egocentric_relations_verified_against_heading": False, "camera_position_verified": False}})
    document = {"schema_version": "1.0", "contract_version": "f59-oriented-streetview-exploratory-v1", "dataset_id": "", "protocol": {"reference_kind": "streetview_panorama_coordinate_unknown_uncertainty", "reference_coordinate_role": "panorama_coordinate", "real_ground_truth": False, "official_f54_evaluation": False, "coordinates_heading_pitch_used_for_qwen_or_retrieval": False, "human_english_control": False}, "catalogs": {gallery: {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": len(catalog.candidates)} for gallery, catalog in catalogs.items()}, "observations": observations, "limitations": ["panorama_camera_position_not_independently_verified", "unknown_positional_uncertainty", "descriptions_pending_visual_and_orientation_review", "eight_case_exploratory_sample", "heading_not_model_input", "not_f54_metrics"]}
    document["dataset_id"] = dataset_id(document); validate_dataset(document, catalogs); return document


def validate_dataset(document: Mapping[str, Any], catalogs: Mapping[str, Any]) -> None:
    if document.get("dataset_id") != dataset_id(document) or len(document["observations"]) != 8: raise F59ExtensionError("identidad H03-H10 inválida")
    for row in document["observations"]:
        if not row["geography"]["panorama_coordinate_inside_d004"] or row["geography"]["official_f54_ground_truth"]: raise F59ExtensionError("observación fuera de D004 o presentada como oficial")
        ref = row["panorama_coordinate"]
        for gallery, catalog in catalogs.items():
            if row["geography"]["panorama_reference_assignments"][gallery] != assign_reference(ref["latitude"], ref["longitude"], catalog): raise F59ExtensionError("asignación H03-H10 inconsistente")


def prepare_variant_inputs(dataset: Mapping[str, Any], catalog50: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    queries, observations = [], []
    for row in dataset["observations"]:
        qid, text = row["observation_id"], row["texts"]["es_original"]["text"]
        queries.append({"query_id": qid, "location_id": f"f59-{qid}", "derivation_group_id": f"f59-{qid}", "partition": "development", "description": {"text": text, "language": "es", "contains_coordinates": False}, "provenance": {"source_type": "existing_dataset", "description": "Descripción humana orientada F5.9; referencia reservada para evaluación.", "independent_environment_observation": False, "instructions_version": "f59-oriented-v1", "collected_at_utc": None}, "reference": {"status": "pending", "latitude": None, "longitude": None, "crs": None, "capture_method": None, "reported_accuracy_m": None, "validation_method": None, "catalog_assignment": None}, "ambiguity": {"status": "unreviewed", "notes": "Coordenada, heading, pitch y auditoría OSM excluidos del modelo."}, "validation_status": "pending"})
        def pending(kind, language): return {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": language, "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        original = {"variant_id": f"{qid}-es-original-f59-oriented-v1", "kind": "es_original", "status": "reviewed", "text": text, "language": "es", "generation": {"method": "original", "tool_or_model": "human_tfg_owner", "version": "f59-oriented-v1", "configuration_or_prompt": "copy-frozen-human-description", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        observations.append({"source_query_id": qid, "source_input_sha256": "0" * 64, "partition": "development", "location_id": f"f59-{qid}", "derivation_group_id": f"f59-{qid}", "toponyms": row["toponyms"], "orientation": {"status": "reported", "cardinal": None, "bearing_degrees": row["panorama"]["heading_degrees"], "bearing_convention": "degrees_clockwise_from_true_north", "method": "streetview_link_heading_unverified", "uncertainty_degrees": 180.0, "provenance": "f59_streetview_metadata", "verification_status": "pending", "relative_relations_present": bool(row["orientation_audit"]["relations_in_text"]), "notes": "Heading documental excluido del modelo; no se infieren cardinales."}, "variants": [original, pending("es_cartographic", "es"), pending("en_conventional", "en"), pending("en_toponym_preserved", "en"), pending("en_cartographic", "en")], "notes": "F5.9 H03-H10; cinco variantes oficiales, sin traducción humana."})
    queries_doc = {"schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "", "dataset_version": "f59-oriented-provisional-v1", "region": {"region_id": catalog50.region_id, "bbox_wgs84": dict(catalog50.region_bbox_wgs84)}, "catalog": {"manifest_id": catalog50.manifest_id, "manifest_sha256": catalog50.sha256, "candidate_count": len(catalog50.candidates), "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"}, "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": 0.8}, "queries": queries}
    queries_doc["dataset_id"] = query_dataset_id(queries_doc); query_by = {row["query_id"]: row for row in queries}
    for row in observations: row["source_input_sha256"] = source_query_input_sha256(query_by[row["source_query_id"]])
    sidecar = json.loads((Path(__file__).resolve().parents[2] / "config/madrid_f53b_textual_variants_template.json").read_text()); sidecar["dataset_version"] = "f59-oriented-provisional-v1"; raw = canonical_bytes(queries_doc) + b"\n"; sidecar["source_query_dataset"] = {"dataset_id": queries_doc["dataset_id"], "sha256": hashlib.sha256(raw).hexdigest()}; sidecar["observations"] = observations; sidecar["dataset_id"] = textual_variant_dataset_id(sidecar)
    return queries_doc, sidecar


def build_plan(dataset: Mapping[str, Any], sidecar: Mapping[str, Any], run: Mapping[str, Any]) -> dict[str, Any]:
    base_audit = audit_variants(sidecar, run); base_issues = {(row["source_query_id"], row["variant_kind"]): row["issue_codes"] for row in base_audit["issues"]}; source = {row["observation_id"]: row for row in dataset["observations"]}; controls, audit_rows = [], []
    for observation in sidecar["observations"]:
        qid = observation["source_query_id"]
        for variant in observation["variants"]:
            codes = list(base_issues[(qid, variant["kind"])]); text = variant["text"] or ""
            codes.extend(_leak_codes(text, source[qid]))
            original_relations = set(source[qid]["orientation_audit"]["relations_in_text"]); output_relations = _relations(text)
            codes.extend(f"relation_lost:{name}" for name in sorted(original_relations - output_relations))
            missing_names = [item["mention"] for item in source[qid]["toponyms"] if item["mention"] not in text]
            modified_names = list(missing_names) if variant["kind"] == "en_conventional" else []
            if variant["kind"] in {"en_toponym_preserved", "en_cartographic"}: codes.extend(f"proper_name_lost:{name}" for name in missing_names)
            codes = sorted(set(codes)); allowed = not codes and bool(text)
            audit_rows.append({"source_query_id": qid, "kind": variant["kind"], "relations_original": sorted(original_relations), "relations_output": sorted(output_relations), "proper_names": [item["mention"] for item in source[qid]["toponyms"]], "proper_names_modified_by_conventional_translation": modified_names, "automatic_checks_passed": allowed, "issue_codes": codes})
            if allowed: controls.append({"source_query_id": qid, "control_id": variant["variant_id"], "kind": variant["kind"], "language": variant["language"], "text": text, "text_sha256": _sha(text), "source": "human_original" if variant["kind"] == "es_original" else "qwen"})
    if len(controls) != 40: raise F59ExtensionError(f"solo {len(controls)}/40 variantes orientadas superan auditoría")
    return {"schema_version": "1.0", "contract_version": "f59-oriented-five-variant-plan-v1", "dataset_id": dataset["dataset_id"], "controls": controls, "audit": audit_rows, "coordinates_heading_pitch_present": False, "limitations": ["automatic_checks_do_not_replace_human_review", "heading_not_model_input"]}


def run_rankings(plan: Mapping[str, Any], retriever: Any) -> dict[str, Any]:
    rows, checkpoint = [], None
    for control in plan["controls"]:
        started = time.perf_counter(); response = retriever.retrieve_many(gallery_ids=GALLERIES, query_id=control["control_id"], text=control["text"], language=control["language"], k=10); elapsed = (time.perf_counter() - started) * 1000; current = response["model"]["checkpoint_sha256"]; checkpoint = current if checkpoint is None else checkpoint
        if checkpoint != current: raise F59ExtensionError("checkpoint cambió")
        for retrieval in response["retrievals"]: _validate_results(retrieval["results"]); rows.append({"source_query_id": control["source_query_id"], "control_id": control["control_id"], "kind": control["kind"], "source": control["source"], "language": control["language"], "text_sha256": control["text_sha256"], "gallery_id": retrieval["gallery_id"], "top_k": 10, "results": retrieval["results"], "retrieval_ms": response["timings_ms"]["total"], "pipeline_elapsed_ms": elapsed})
    expected = {(f"H{i:02d}", kind, gallery) for i in range(3, 11) for kind in KINDS for gallery in GALLERIES}; observed = {(row["source_query_id"], row["kind"], row["gallery_id"]) for row in rows}
    if observed != expected or len(rows) != len(observed): raise F59ExtensionError("producto cartesiano de rankings incompleto")
    doc = {"schema_version": "1.0", "contract_version": "f59-oriented-rankings-v1", "ranking_id": "", "checkpoint_sha256": checkpoint, "gallery_ids": list(GALLERIES), "ranking_method": "exhaustive_cosine", "top_k": 10, "rows": rows, "limitations": ["coordinates_heading_pitch_not_used_for_retrieval", "no_prefiltering", "no_reranking", "frozen_embeddings"]}; doc["ranking_id"] = ranking_id(doc); return doc


def ranking_id(document: Mapping[str, Any]) -> str: return RANKING_PREFIX + hashlib.sha256(canonical_bytes({key: document[key] for key in document if key != "ranking_id"})).hexdigest()


def evaluate(dataset: Mapping[str, Any], rankings: Mapping[str, Any], *, dataset_sha256: str, plan_sha256: str, rankings_sha256: str) -> dict[str, Any]:
    if rankings["ranking_id"] != ranking_id(rankings) or len(rankings["rows"]) != 80: raise F59ExtensionError("rankings orientados incompatibles")
    refs = {row["observation_id"]: row for row in dataset["observations"]}; rows = []
    for ranking in rankings["rows"]:
        ref = refs[ranking["source_query_id"]]; coordinate = ref["panorama_coordinate"]; assignment = ref["geography"]["panorama_reference_assignments"][ranking["gallery_id"]]; candidates = []
        for candidate in ranking["results"]:
            distance = haversine_m(coordinate["latitude"], coordinate["longitude"], candidate["latitude"], candidate["longitude"]); candidates.append({**candidate, "distance_to_panorama_reference_m": distance, "is_reference_cell": candidate["candidate_id"] == assignment.get("candidate_id"), "within_50m": distance <= 50, "within_100m": distance <= 100})
        available = assignment["status"] == "assigned" and bool(assignment.get("candidate_id")); exact_rank = next((row["rank"] for row in candidates if row["is_reference_cell"]), None) if available else None; nearest = min(candidates, key=lambda row: row["distance_to_panorama_reference_m"])
        rows.append({"source_query_id": ranking["source_query_id"], "kind": ranking["kind"], "gallery_id": ranking["gallery_id"], "reference_assignment_status": assignment["status"], "reference_candidate_id": assignment.get("candidate_id"), "exact_recall_available": available, "exact_rank": exact_rank, "recall_at_10": (exact_rank is not None) if available else None, "top1_error_m": candidates[0]["distance_to_panorama_reference_m"], "minimum_top10_error_m": nearest["distance_to_panorama_reference_m"], "nearest_candidate_rank": nearest["rank"], "geo_recall_at_10": {"50": nearest["distance_to_panorama_reference_m"] <= 50, "100": nearest["distance_to_panorama_reference_m"] <= 100}, "relations_in_original": ref["orientation_audit"]["relations_in_text"], "proper_names": [item["mention"] for item in ref["toponyms"]], "osm_carto_audit": ref["osm_carto_audit"], "retrieval_ms": ranking["retrieval_ms"], "candidates": candidates})
    metrics = aggregate(rows, KINDS)
    doc = {"schema_version": "1.0", "contract_version": "f59-oriented-evaluation-v1", "evaluation_id": "", "protocol": {"reference_kind": "streetview_panorama_coordinate_unknown_uncertainty", "official_f54_evaluation": False, "coordinates_heading_pitch_used_for_retrieval": False, "sample_size": 8, "variant_kinds": list(KINDS), "geo_thresholds_m": [50, 100]}, "inputs": {"dataset_id": dataset["dataset_id"], "dataset_sha256": dataset_sha256, "plan_sha256": plan_sha256, "rankings_sha256": rankings_sha256}, "coverage": {"observations": 8, "expected_rankings": 80, "observed_rankings": len(rows), "officially_evaluable": 0}, "metrics": metrics, "paired_comparisons": paired(rows), "per_observation": rows, "limitations": ["panorama_coordinates_unknown_uncertainty", "not_official_ground_truth", "eight_case_exploratory_sample", "unreviewed_qwen_variants", "heading_not_model_input", "no_vlm", "no_finetuning"]}; doc["evaluation_id"] = EVALUATION_PREFIX + hashlib.sha256(canonical_bytes({key: doc[key] for key in doc if key != "evaluation_id"})).hexdigest(); return doc


def combine(h01_h02: Mapping[str, Any], h03_h10: Mapping[str, Any], *, left_sha256: str, right_sha256: str) -> dict[str, Any]:
    rows = [row for row in h01_h02["per_observation"] if row["kind"] in KINDS] + list(h03_h10["per_observation"]); expected = {(f"H{i:02d}", kind, gallery) for i in range(1, 11) for kind in KINDS for gallery in GALLERIES}; observed = {(row["source_query_id"], row["kind"], row["gallery_id"]) for row in rows}
    if expected != observed or len(rows) != 100: raise F59ExtensionError("agregado H01-H10 incompleto")
    doc = {"schema_version": "1.0", "contract_version": "f59-h01-h10-common-evaluation-v1", "evaluation_id": "", "protocol": {"exploratory": True, "official_f54_evaluation": False, "common_variant_kinds": list(KINDS), "sample_size": 10, "human_english_control_excluded": True}, "inputs": {"h01_h02_evaluation_sha256": left_sha256, "h03_h10_evaluation_sha256": right_sha256}, "metrics": aggregate(rows, KINDS), "paired_comparisons": paired(rows), "per_observation": rows, "limitations": ["panorama_coordinates_unknown_uncertainty", "not_official_ground_truth", "mixed_exploratory_human_sample", "heading_not_model_input"]}; doc["evaluation_id"] = COMBINED_PREFIX + hashlib.sha256(canonical_bytes({key: doc[key] for key in doc if key != "evaluation_id"})).hexdigest(); return doc


def render_html(document: Mapping[str, Any], output: Path, title: str) -> None:
    metrics = []
    for row in document["metrics"]:
        recall = "n/d" if row["recall_at_10"] is None else f"{row['recall_at_10']:.3f}"
        metrics.append(f"<tr><td>{escape(row['gallery_id'])}</td><td>{escape(row['kind'])}</td><td>{row['count']}</td><td>{row['geo_recall_at_10']['50']:.3f}</td><td>{row['geo_recall_at_10']['100']:.3f}</td><td>{recall}</td><td>{row['minimum_top10_error_m']['mean']:.2f}</td><td>{row['minimum_top10_error_m']['median']:.2f}</td></tr>")
    individual = []
    for row in document["per_observation"]:
        individual.append(f"<tr><td>{escape(row['source_query_id'])}</td><td>{escape(row['gallery_id'])}</td><td>{escape(row['kind'])}</td><td>{escape(str(row['exact_rank']))}</td><td>{row['geo_recall_at_10']['50']}</td><td>{row['geo_recall_at_10']['100']}</td><td>{row['top1_error_m']:.2f}</td><td>{row['minimum_top10_error_m']:.2f}</td></tr>")
    output.write_text(f"<!doctype html><html lang='es'><meta charset='utf-8'><title>{escape(title)}</title><style>body{{font:16px system-ui;max-width:1400px;margin:auto;padding:2rem}}table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}th,td{{border:1px solid #aaa;padding:.4rem}}</style><h1>{escape(title)}</h1><p><strong>Exploratorio:</strong> referencias de panorama con incertidumbre desconocida; heading no usado por el modelo.</p><h2>Agregados</h2><table><tr><th>Galería</th><th>Variante</th><th>n</th><th>Geo50</th><th>Geo100</th><th>R@10</th><th>Mín. Top-10 medio</th><th>Mediana</th></tr>{''.join(metrics)}</table><h2>Resultados individuales</h2><table><tr><th>Caso</th><th>Galería</th><th>Variante</th><th>Rango exacto</th><th>Geo50</th><th>Geo100</th><th>Top-1</th><th>Mín. Top-10</th></tr>{''.join(individual)}</table></html>", encoding="utf-8")


def aggregate(rows: Sequence[Mapping[str, Any]], kinds: Sequence[str]) -> list[dict[str, Any]]:
    output = []
    for gallery in GALLERIES:
        for kind in kinds:
            selected = [row for row in rows if row["gallery_id"] == gallery and row["kind"] == kind]; exact = [row["recall_at_10"] for row in selected if row["exact_recall_available"]]; mins = [row["minimum_top10_error_m"] for row in selected]
            output.append({"gallery_id": gallery, "kind": kind, "count": len(selected), "exact_recall_count": len(exact), "recall_at_10": statistics.fmean(exact) if exact else None, "geo_recall_at_10": {radius: statistics.fmean(row["geo_recall_at_10"][radius] for row in selected) for radius in ("50", "100")}, "top1_error_m": {"mean": statistics.fmean(row["top1_error_m"] for row in selected), "median": statistics.median(row["top1_error_m"] for row in selected)}, "minimum_top10_error_m": {"mean": statistics.fmean(mins), "median": statistics.median(mins), "values": mins}})
    return output


def paired(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    index = {(row["source_query_id"], row["gallery_id"], row["kind"]): row for row in rows}; output = []
    for gallery in GALLERIES:
        for kind in KINDS[1:]:
            cases = []
            for qid in sorted({row["source_query_id"] for row in rows}):
                anchor, variant = index[(qid, gallery, "es_original")], index[(qid, gallery, kind)]; delta = variant["minimum_top10_error_m"] - anchor["minimum_top10_error_m"]
                cases.append({"source_query_id": qid, "minimum_top10_delta_m": delta, "geo50_change": int(variant["geo_recall_at_10"]["50"]) - int(anchor["geo_recall_at_10"]["50"]), "geo100_change": int(variant["geo_recall_at_10"]["100"]) - int(anchor["geo_recall_at_10"]["100"])})
            output.append({"gallery_id": gallery, "kind": kind, "count": len(cases), "geo50_improved": sum(row["geo50_change"] > 0 for row in cases), "geo50_worsened": sum(row["geo50_change"] < 0 for row in cases), "geo100_improved": sum(row["geo100_change"] > 0 for row in cases), "geo100_worsened": sum(row["geo100_change"] < 0 for row in cases), "minimum_top10_improved": sum(row["minimum_top10_delta_m"] < 0 for row in cases), "minimum_top10_worsened": sum(row["minimum_top10_delta_m"] > 0 for row in cases), "mean_minimum_top10_delta_m": statistics.fmean(row["minimum_top10_delta_m"] for row in cases), "cases": cases})
    return output


def _coordinate(value):
    lat, lon = value.get("latitude"), value.get("longitude")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (lat, lon)): raise F59ExtensionError("coordenada inválida")
    return {"latitude": float(lat), "longitude": float(lon), "crs": "EPSG:4326"}
def _range(value, low, high, inclusive): return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value and (value <= high if inclusive else value < high)
def _inside(c, b): return b["south"] <= c["latitude"] <= b["north"] and b["west"] <= c["longitude"] <= b["east"]
def _relations(text): return {name for name, patterns in RELATION_PATTERNS.items() if any(re.search(pattern, text, re.I) for pattern in patterns)}
def _relation_label(value):
    labels = {"izquierda": "left", "derecha": "right", "delante": "front", "frente": "front", "en frente": "front", "detrás": "behind"}
    if value not in labels: raise F59ExtensionError(f"relación documental desconocida: {value}")
    return labels[value]
def _sha(text): return hashlib.sha256(text.encode()).hexdigest()
def _leak_codes(text, source):
    codes=[]
    if COORD_RE.search(text): codes.append("coordinate_leak")
    if source["panorama"]["panorama_id"] in text or INTERNAL_RE.search(text): codes.append("internal_or_panorama_id_leak")
    for assignment in source["geography"]["panorama_reference_assignments"].values():
        if assignment.get("candidate_id") and assignment["candidate_id"] in text: codes.append("candidate_id_leak")
    return codes
