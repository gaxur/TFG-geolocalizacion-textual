"""F5.9: dos casos humanos Street View con referencia experimental separada."""

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
from .f57_experimental_evaluation import COORD_RE, INTERNAL_RE, RELATIONS, canonical_bytes, audit_variants


KINDS = ("es_original", "en_human_control", "es_cartographic", "en_conventional", "en_toponym_preserved", "en_cartographic")
GALLERIES = ("madrid-25m", "madrid-50m")
DATASET_PREFIX = "f59-human-streetview-sha256-"
RANKING_PREFIX = "f59-exploratory-rankings-sha256-"
EVALUATION_PREFIX = "f59-exploratory-evaluation-sha256-"


class F59Error(ValueError):
    pass


def dataset_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "protocol", "catalogs", "observations", "limitations")}
    return DATASET_PREFIX + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def build_dataset(spec: Mapping[str, Any], catalogs: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("contract_version") != "f59-human-streetview-input-v1" or spec.get("reference_policy") != "panorama_coordinate_experimental_unknown_uncertainty":
        raise F59Error("especificación F5.9 incompatible")
    if set(catalogs) != set(GALLERIES) or [row.get("observation_id") for row in spec.get("observations", [])] != ["H01", "H02"]:
        raise F59Error("F5.9 exige H01/H02 y ambas galerías")
    observations = []
    for source in spec["observations"]:
        spanish, english = source["spanish_text"], source["human_english_text"]
        panorama_id = source["panorama_id"]
        for text in (spanish, english):
            if COORD_RE.search(text) or panorama_id in text or INTERNAL_RE.search(text):
                raise F59Error("texto H01/H02 contiene metadatos prohibidos")
        toponyms = []
        for mention in source["proper_toponyms"]:
            matches = list(re.finditer(re.escape(mention), spanish))
            if len(matches) != 1: raise F59Error("topónimo propio ambiguo o ausente")
            match = matches[0]
            entity_type = "station" if mention == "Cercanías" else "poi"
            toponyms.append({"mention": mention, "span": {"start": match.start(), "end": match.end()}, "entity_type": entity_type, "name_kind": "proper_name", "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"})
        marker = _coordinate(source["provided_coordinate"])
        panorama = _coordinate(source["panorama_coordinate"])
        inside_marker = _inside_d004(marker, next(iter(catalogs.values())).region_bbox_wgs84)
        inside_panorama = _inside_d004(panorama, next(iter(catalogs.values())).region_bbox_wgs84)
        observations.append({
            "observation_id": source["observation_id"], "source_type": "human_description_streetview_reference",
            "texts": {"es_original": {"text": spanish, "language": "es", "source": "human_tfg_owner", "frozen_before_qwen_and_retrieval": True}, "en_human_control": {"text": english, "language": "en", "source": "human_translation_supplied_by_tfg_owner", "not_qwen_output": True, "frozen_before_qwen_and_retrieval": True}},
            "toponyms": toponyms,
            "provided_coordinate": {**marker, "meaning": source["provided_coordinate"]["meaning"], "dms": source["provided_coordinate"].get("dms")},
            "panorama_coordinate": {**panorama, "meaning": source["panorama_coordinate"]["meaning"], "camera_position_independently_verified": False, "positional_uncertainty": "unknown"},
            "panorama": {"provider": "Google Street View", "panorama_id": panorama_id, "heading_degrees": source["heading_degrees"], "pitch_degrees": source["pitch_degrees"], "heading_is_camera_not_body_orientation": True},
            "geography": {"experimental_reference_role": "panorama_coordinate", "official_f54_ground_truth": False, "provided_coordinate_inside_d004": inside_marker, "panorama_coordinate_inside_d004": inside_panorama, "provided_to_panorama_distance_m": haversine_m(marker["latitude"], marker["longitude"], panorama["latitude"], panorama["longitude"]), "provided_coordinate_assignments": {gallery: assign_reference(marker["latitude"], marker["longitude"], catalog) for gallery, catalog in catalogs.items()}, "panorama_reference_assignments": {gallery: assign_reference(panorama["latitude"], panorama["longitude"], catalog) for gallery, catalog in catalogs.items()}},
            "review": {"status": "pending", "description_visual_correspondence_verified": False, "egocentric_relations_verified_against_heading": False, "camera_position_verified": False},
        })
    document = {"schema_version": "1.0", "contract_version": "f59-human-streetview-exploratory-v1", "dataset_id": "", "protocol": {"reference_kind": "streetview_panorama_coordinate_unknown_uncertainty", "reference_coordinate_role": "panorama_coordinate", "real_ground_truth": False, "official_f54_evaluation": False, "coordinates_used_for_qwen_or_retrieval": False, "human_english_is_independent_control": True}, "catalogs": {gallery: {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": len(catalog.candidates)} for gallery, catalog in catalogs.items()}, "observations": observations, "limitations": ["panorama_camera_position_not_independently_verified", "unknown_positional_uncertainty", "descriptions_pending_visual_review", "two_case_exploratory_sample", "not_f54_metrics"]}
    document["dataset_id"] = dataset_id(document)
    validate_dataset(document, catalogs)
    return document


def validate_dataset(document: Mapping[str, Any], catalogs: Mapping[str, Any]) -> None:
    if document.get("dataset_id") != dataset_id(document) or document["protocol"]["real_ground_truth"] is not False: raise F59Error("identidad o separación F5.9 inválida")
    for row in document["observations"]:
        if not row["geography"]["provided_coordinate_inside_d004"] or not row["geography"]["panorama_coordinate_inside_d004"]: raise F59Error("H01/H02 fuera de D004")
        reference = row["panorama_coordinate"]
        for gallery, catalog in catalogs.items():
            if row["geography"]["panorama_reference_assignments"][gallery] != assign_reference(reference["latitude"], reference["longitude"], catalog): raise F59Error("asignación de panorama inconsistente")
        if row["review"]["status"] != "pending" or row["geography"]["official_f54_ground_truth"]: raise F59Error("H01/H02 se presenta como aprobado u oficial")


def prepare_variant_inputs(dataset: Mapping[str, Any], catalog50: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    queries, observations = [], []
    for row in dataset["observations"]:
        qid, text = row["observation_id"], row["texts"]["es_original"]["text"]
        query = {"query_id": qid, "location_id": f"f59-{qid}", "derivation_group_id": f"f59-{qid}", "partition": "development", "description": {"text": text, "language": "es", "contains_coordinates": False}, "provenance": {"source_type": "existing_dataset", "description": "Descripción humana F5.9; referencias reservadas para evaluación posterior.", "independent_environment_observation": False, "instructions_version": "f59-human-streetview-v1", "collected_at_utc": None}, "reference": {"status": "pending", "latitude": None, "longitude": None, "crs": None, "capture_method": None, "reported_accuracy_m": None, "validation_method": None, "catalog_assignment": None}, "ambiguity": {"status": "unreviewed", "notes": "Referencia y metadatos Street View excluidos de Qwen y retrieval."}, "validation_status": "pending"}
        queries.append(query)
        def pending(kind, language): return {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": language, "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        original = {"variant_id": f"{qid}-es-original-f59-v1", "kind": "es_original", "status": "reviewed", "text": text, "language": "es", "generation": {"method": "original", "tool_or_model": "human_tfg_owner", "version": "f59-v1", "configuration_or_prompt": "copy-frozen-human-description", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        observations.append({"source_query_id": qid, "source_input_sha256": "0" * 64, "partition": "development", "location_id": f"f59-{qid}", "derivation_group_id": f"f59-{qid}", "toponyms": row["toponyms"], "orientation": {"status": "reported", "cardinal": None, "bearing_degrees": row["panorama"]["heading_degrees"], "bearing_convention": "degrees_clockwise_from_true_north", "method": "streetview_link_heading_unverified", "uncertainty_degrees": 180.0, "provenance": "f59_streetview_metadata", "verification_status": "pending", "relative_relations_present": True, "notes": "Heading de cámara; no convierte relaciones egocéntricas a cardinales."}, "variants": [original, pending("es_cartographic", "es"), pending("en_conventional", "en"), pending("en_toponym_preserved", "en"), pending("en_cartographic", "en")], "notes": "F5.9 exploratorio; control inglés humano en artefacto separado."})
    query_dataset = {"schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "", "dataset_version": "f59-human-streetview-provisional-v1", "region": {"region_id": catalog50.region_id, "bbox_wgs84": dict(catalog50.region_bbox_wgs84)}, "catalog": {"manifest_id": catalog50.manifest_id, "manifest_sha256": catalog50.sha256, "candidate_count": len(catalog50.candidates), "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"}, "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": 0.8}, "queries": queries}
    query_dataset["dataset_id"] = query_dataset_id(query_dataset)
    query_by = {row["query_id"]: row for row in queries}
    for row in observations: row["source_input_sha256"] = source_query_input_sha256(query_by[row["source_query_id"]])
    sidecar = json.loads((Path(__file__).resolve().parents[2] / "config/madrid_f53b_textual_variants_template.json").read_text())
    sidecar["dataset_version"] = "f59-human-streetview-provisional-v1"; raw = canonical_bytes(query_dataset) + b"\n"
    sidecar["source_query_dataset"] = {"dataset_id": query_dataset["dataset_id"], "sha256": hashlib.sha256(raw).hexdigest()}; sidecar["observations"] = observations; sidecar["dataset_id"] = textual_variant_dataset_id(sidecar)
    return query_dataset, sidecar


def build_control_plan(dataset: Mapping[str, Any], sidecar: Mapping[str, Any], run: Mapping[str, Any]) -> dict[str, Any]:
    audit = audit_variants(sidecar, run)
    eligible = {(row["source_query_id"], row["variant_kind"]) for row in audit["eligible_pairs"]}
    source = {row["observation_id"]: row for row in dataset["observations"]}; controls = []
    for observation in sidecar["observations"]:
        qid = observation["source_query_id"]
        variants = {row["kind"]: row for row in observation["variants"]}
        ordered = [(kind, variants[kind]) for kind in KINDS if kind != "en_human_control"]
        human_text = source[qid]["texts"]["en_human_control"]["text"]
        ordered.insert(1, ("en_human_control", {"variant_id": f"{qid}-en-human-control-f59-v1", "text": human_text, "language": "en"}))
        for kind, variant in ordered:
            codes = _leak_codes(variant["text"], source[qid])
            if kind != "en_human_control" and (qid, kind) not in eligible: codes.append("standard_variant_audit_failed")
            controls.append({"source_query_id": qid, "control_id": variant["variant_id"], "kind": kind, "language": variant["language"], "text": variant["text"], "text_sha256": _sha256_text(variant["text"]), "source": "human_translation" if kind == "en_human_control" else ("human_original" if kind == "es_original" else "qwen"), "automatic_checks_passed": not codes, "issue_codes": codes})
    if len(controls) != 12 or any(not row["automatic_checks_passed"] for row in controls): raise F59Error("plan F5.9 incompleto o con fuga")
    return {"schema_version": "1.0", "contract_version": "f59-six-control-plan-v1", "dataset_id": dataset["dataset_id"], "controls": controls, "coordinates_present": False, "limitations": ["human_english_control_not_qwen", "automatic_checks_do_not_replace_human_review"]}


def run_rankings(plan: Mapping[str, Any], retriever: Any) -> dict[str, Any]:
    rows, checkpoint = [], None
    for control in plan["controls"]:
        started = time.perf_counter(); response = retriever.retrieve_many(gallery_ids=GALLERIES, query_id=control["control_id"], text=control["text"], language=control["language"], k=10); elapsed = (time.perf_counter() - started) * 1000
        current = response["model"]["checkpoint_sha256"]; checkpoint = current if checkpoint is None else checkpoint
        if checkpoint != current: raise F59Error("checkpoint cambió durante F5.9")
        for retrieval in response["retrievals"]:
            _validate_results(retrieval["results"])
            rows.append({"source_query_id": control["source_query_id"], "control_id": control["control_id"], "kind": control["kind"], "source": control["source"], "language": control["language"], "text_sha256": control["text_sha256"], "gallery_id": retrieval["gallery_id"], "top_k": 10, "results": retrieval["results"], "retrieval_ms": response["timings_ms"]["total"], "pipeline_elapsed_ms": elapsed})
    document = {"schema_version": "1.0", "contract_version": "f59-exploratory-rankings-v1", "ranking_id": "", "checkpoint_sha256": checkpoint, "gallery_ids": list(GALLERIES), "ranking_method": "exhaustive_cosine", "top_k": 10, "rows": rows, "limitations": ["coordinates_not_used_for_retrieval", "no_prefiltering", "no_reranking", "frozen_embeddings"]}
    document["ranking_id"] = ranking_id(document); return document


def ranking_id(document: Mapping[str, Any]) -> str:
    return RANKING_PREFIX + hashlib.sha256(canonical_bytes({key: document[key] for key in document if key != "ranking_id"})).hexdigest()


def evaluate(dataset: Mapping[str, Any], rankings: Mapping[str, Any], *, dataset_sha256: str, plan_sha256: str, rankings_sha256: str) -> dict[str, Any]:
    if rankings["ranking_id"] != ranking_id(rankings) or len(rankings["rows"]) != 24: raise F59Error("rankings F5.9 incompatibles")
    references = {row["observation_id"]: row for row in dataset["observations"]}; rows = []
    for ranking in rankings["rows"]:
        reference = references[ranking["source_query_id"]]; coordinate = reference["panorama_coordinate"]; assignment = reference["geography"]["panorama_reference_assignments"][ranking["gallery_id"]]
        candidates = []
        for candidate in ranking["results"]:
            distance = haversine_m(coordinate["latitude"], coordinate["longitude"], candidate["latitude"], candidate["longitude"])
            candidates.append({**candidate, "distance_to_panorama_reference_m": distance, "is_reference_cell": candidate["candidate_id"] == assignment.get("candidate_id"), "within_50m": distance <= 50, "within_100m": distance <= 100})
        exact_available = assignment.get("status") == "assigned" and bool(assignment.get("candidate_id"))
        exact_rank = next((row["rank"] for row in candidates if row["is_reference_cell"]), None) if exact_available else None
        rows.append({"source_query_id": ranking["source_query_id"], "kind": ranking["kind"], "source": ranking["source"], "gallery_id": ranking["gallery_id"], "reference_kind": "panorama_coordinate_unknown_uncertainty", "reference_assignment_status": assignment.get("status"), "reference_candidate_id": assignment.get("candidate_id"), "exact_recall_available": exact_available, "exact_rank": exact_rank, "recall_at_10": (exact_rank is not None and exact_rank <= 10) if exact_available else None, "top1_error_m": candidates[0]["distance_to_panorama_reference_m"], "minimum_top10_error_m": min(row["distance_to_panorama_reference_m"] for row in candidates), "geo_recall_at_10": {"50": any(row["within_50m"] for row in candidates), "100": any(row["within_100m"] for row in candidates)}, "retrieval_ms": ranking["retrieval_ms"], "candidates": candidates})
    metrics = []
    for gallery in GALLERIES:
        for kind in KINDS:
            selected = [row for row in rows if row["gallery_id"] == gallery and row["kind"] == kind]
            exact = [row["recall_at_10"] for row in selected if row["exact_recall_available"]]
            metrics.append({"gallery_id": gallery, "kind": kind, "count": len(selected), "exact_recall_count": len(exact), "recall_at_10": statistics.fmean(exact) if exact else None, "geo_recall_at_10": {radius: statistics.fmean(row["geo_recall_at_10"][radius] for row in selected) for radius in ("50", "100")}, "top1_error_m": {"mean": statistics.fmean(row["top1_error_m"] for row in selected), "median": statistics.median(row["top1_error_m"] for row in selected)}, "minimum_top10_error_m": {"mean": statistics.fmean(row["minimum_top10_error_m"] for row in selected), "median": statistics.median(row["minimum_top10_error_m"] for row in selected)}})
    document = {"schema_version": "1.0", "contract_version": "f59-exploratory-evaluation-v1", "evaluation_id": "", "protocol": {"reference_kind": "streetview_panorama_coordinate_unknown_uncertainty", "official_f54_evaluation": False, "coordinates_used_for_retrieval": False, "sample_size": 2, "controls_per_observation": 6, "geo_thresholds_m": [50, 100]}, "inputs": {"dataset_id": dataset["dataset_id"], "dataset_sha256": dataset_sha256, "plan_sha256": plan_sha256, "rankings_sha256": rankings_sha256}, "coverage": {"observations": 2, "expected_rankings": 24, "observed_rankings": len(rankings["rows"]), "officially_evaluable": 0}, "metrics": metrics, "per_observation": rows, "limitations": ["panorama_coordinates_unknown_uncertainty", "not_official_ground_truth", "two_case_exploratory_sample", "unreviewed_qwen_variants", "no_vlm", "no_finetuning"]}
    document["evaluation_id"] = EVALUATION_PREFIX + hashlib.sha256(canonical_bytes({key: document[key] for key in document if key != "evaluation_id"})).hexdigest(); return document


def render_html(document: Mapping[str, Any], output: Path) -> None:
    rows = []
    candidates = []
    for item in document["per_observation"]:
        exact = str(item["exact_rank"]) if item["exact_recall_available"] else "no disponible"
        rows.append(f"<tr><td>{escape(item['source_query_id'])}</td><td>{escape(item['gallery_id'])}</td><td>{escape(item['kind'])}</td><td>{exact}</td><td>{item['geo_recall_at_10']['50']}</td><td>{item['geo_recall_at_10']['100']}</td><td>{item['top1_error_m']:.2f}</td><td>{item['minimum_top10_error_m']:.2f}</td></tr>")
        for candidate in item["candidates"]:
            candidates.append(f"<tr><td>{escape(item['source_query_id'])}</td><td>{escape(item['gallery_id'])}</td><td>{escape(item['kind'])}</td><td>{candidate['rank']}</td><td><code>{escape(candidate['candidate_id'])}</code></td><td>{candidate['latitude']:.7f}</td><td>{candidate['longitude']:.7f}</td><td>{candidate['cosine_similarity']:.6f}</td><td>{candidate['distance_to_panorama_reference_m']:.2f}</td><td>{candidate['within_50m']}</td><td>{candidate['within_100m']}</td></tr>")
    output.write_text(f"<!doctype html><html lang='es'><meta charset='utf-8'><title>F5.9</title><style>body{{font:16px system-ui;max-width:1500px;margin:auto;padding:2rem}}table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}th,td{{border:1px solid #aaa;padding:.4rem}}code{{overflow-wrap:anywhere}}</style><h1>F5.9: H01/H02 experimental</h1><p><strong>No es F5.4:</strong> referencia de panorama no verificada e incertidumbre desconocida.</p><h2>Resumen por ranking</h2><table><tr><th>Caso</th><th>Galería</th><th>Control</th><th>Rango exacto</th><th>Geo50</th><th>Geo100</th><th>Top-1 m</th><th>Mín. Top-10 m</th></tr>{''.join(rows)}</table><h2>240 candidatas individuales</h2><table><tr><th>Caso</th><th>Galería</th><th>Control</th><th>Rank</th><th>Candidate ID</th><th>Latitud</th><th>Longitud</th><th>Coseno</th><th>Distancia m</th><th>≤50 m</th><th>≤100 m</th></tr>{''.join(candidates)}</table></html>", encoding="utf-8")


def _coordinate(value: Mapping[str, Any]) -> dict[str, float]:
    lat, lon = value.get("latitude"), value.get("longitude")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in (lat, lon)) or not -90 <= lat <= 90 or not -180 <= lon <= 180: raise F59Error("coordenada inválida")
    return {"latitude": float(lat), "longitude": float(lon), "crs": "EPSG:4326"}


def _inside_d004(coordinate: Mapping[str, float], bbox: Mapping[str, float]) -> bool: return bbox["south"] <= coordinate["latitude"] <= bbox["north"] and bbox["west"] <= coordinate["longitude"] <= bbox["east"]
def _sha256_text(value: str) -> str: return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _leak_codes(text: str, source: Mapping[str, Any]) -> list[str]:
    codes = []
    if COORD_RE.search(text): codes.append("coordinate_leak")
    if source["panorama"]["panorama_id"] in text or INTERNAL_RE.search(text): codes.append("internal_or_panorama_id_leak")
    for assignment_group in ("provided_coordinate_assignments", "panorama_reference_assignments"):
        for assignment in source["geography"][assignment_group].values():
            if assignment.get("candidate_id") and assignment["candidate_id"] in text: codes.append("candidate_id_leak")
    return sorted(set(codes))


def _validate_results(results: Sequence[Mapping[str, Any]]) -> None:
    if len(results) != 10 or [row.get("rank") for row in results] != list(range(1, 11)) or len({row.get("candidate_id") for row in results}) != 10: raise F59Error("Top-10 inválido")
    for previous, current in zip(results, results[1:]):
        if current["cosine_similarity"] > previous["cosine_similarity"] or (current["cosine_similarity"] == previous["cosine_similarity"] and current["candidate_id"] < previous["candidate_id"]): raise F59Error("ranking no ordenado")
