"""Benchmark sintético F5.5c basado exclusivamente en evidencia OSM/F3 congelada."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from html import escape
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any, Mapping, Sequence

from .crs import wgs84_to_epsg25830
from .f4_evaluation import assign_reference, haversine_m


PREFIX = "f55c-synthetic-osm-sha256-"
TYPE_ORDER = ("square", "park", "church", "monument", "street", "building", "commercial")
TYPE_LABELS = {"square": "una plaza", "park": "un parque o jardín", "church": "un lugar de culto", "monument": "un monumento o elemento histórico", "street": "una vía", "building": "edificios", "commercial": "actividades o equipamientos urbanos"}


class SyntheticBenchmarkError(ValueError):
    pass


def benchmark_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "protocol", "inputs", "partitions", "observations", "limitations")}
    return PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build_synthetic_benchmark(*, catalog_50, catalog_25, f3_bundle: Path, count: int = 40, seed: int = 55, minimum_spacing_m: float = 80.0, development_fraction: float = .7) -> dict[str, Any]:
    if not 30 <= count <= 50 or seed < 0 or minimum_spacing_m <= 0 or not 0 < development_fraction < 1:
        raise SyntheticBenchmarkError("configuración synthetic_osm fuera de rango")
    provenance_path = f3_bundle / "provenance.json"; objects_path = f3_bundle / "osm_objects.jsonl"; associations_path = f3_bundle / "candidate_osm_associations.jsonl"
    for path in (provenance_path, objects_path, associations_path):
        if not path.is_file(): raise SyntheticBenchmarkError(f"input F3 ausente: {path}")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    objects = {row["osm_ref"]: row for row in load_jsonl(objects_path)}
    associations = defaultdict(list)
    for row in load_jsonl(associations_path): associations[row["candidate_id"]].append(row)
    candidates = []
    for candidate in catalog_50.candidates:
        assignment_50 = assign_reference(candidate.latitude, candidate.longitude, catalog_50)
        assignment_25 = assign_reference(candidate.latitude, candidate.longitude, catalog_25)
        if assignment_50["status"] != "assigned" or assignment_25["status"] != "assigned": continue
        evidence = build_candidate_evidence(associations.get(candidate.candidate_id, ()), objects)
        type_counts = Counter(row["semantic_type"] for row in evidence)
        if len(evidence) < 3 or len(type_counts) < 2: continue
        description, used = build_description(evidence)
        if description is None: continue
        quality = quality_metrics(description, used)
        if not quality["passes_automatic_quality"]: continue
        candidates.append({"candidate": candidate, "assignment_25": assignment_25, "assignment_50": assignment_50, "evidence": evidence, "description": description, "used": used, "quality": quality})
    selected = spatial_select(candidates, count=count, seed=seed, minimum_spacing_m=minimum_spacing_m)
    if len(selected) < 30:
        raise SyntheticBenchmarkError(f"solo {len(selected)} observaciones cumplen calidad y separación")
    observations = []
    partition_by_group = spatial_group_partitions(selected, development_fraction=development_fraction, seed=seed)
    development_count = sum(partition_by_group[spatial_group_id(row["candidate"])] == "development" for row in selected)
    for index, row in enumerate(selected, 1):
        candidate = row["candidate"]
        group_id = spatial_group_id(candidate); partition = partition_by_group[group_id]
        evidence_rows = []
        for evidence in row["used"]:
            evidence_rows.append({key: evidence[key] for key in ("osm_ref", "osm_type", "osm_id", "geometry_role", "semantic_type", "name", "relation", "center_distance_m", "tag_evidence")})
        observations.append({
            "observation_id": f"synthetic-osm-{index:03d}", "location_id": f"synthetic-location-{index:03d}", "derivation_group_id": f"synthetic-osm-{index:03d}", "spatial_group_id": group_id, "partition": partition,
            "source_type": "synthetic_osm", "reference": {"method": "f1_50m_candidate_center_with_independent_25m_assignment", "latitude": candidate.latitude, "longitude": candidate.longitude, "crs": "EPSG:4326", "easting_m": candidate.center_easting_m, "northing_m": candidate.center_northing_m, "synthetic_coordinate_not_gnss": True, "madrid-25m": row["assignment_25"], "madrid-50m": row["assignment_50"]},
            "description": {"text": row["description"], "language": "es", "contains_coordinates": False, "contains_internal_ids": False, "visibility_claimed": False, "orientation_claimed": False},
            "evidence": evidence_rows, "quality": row["quality"],
            "review": {"status": "pending", "reviewer": None, "reviewed_at_utc": None, "osm_consistency_approved": False, "rejection_reasons": [], "notes": None},
        })
    document = {
        "schema_version": "1.0", "contract_version": "f55c-synthetic-osm-benchmark-v1", "benchmark_id": PREFIX + "0" * 64,
        "protocol": {"version": "f55c-synthetic-osm-v2", "seed": seed, "requested_count": count, "minimum_spacing_m": minimum_spacing_m, "selection": "randomized_farthest_point_epsg25830_unique_text_v1", "position": "f1_50m_candidate_center_explicitly_synthetic", "description_generator": "deterministic_osm_evidence_templates_v1", "ground_truth_kind": "synthetic_osm", "human_observation": False, "visibility_inference": False, "orientation_inference": False, "ranking_used_for_selection": False, "embeddings_used_for_selection": False, "frozen_before_retrieval": True, "evaluation_adapter": "separate_synthetic_f54_metric_definitions_v1"},
        "inputs": {"catalog_50m": {"manifest_id": catalog_50.manifest_id, "sha256": catalog_50.sha256}, "catalog_25m": {"manifest_id": catalog_25.manifest_id, "sha256": catalog_25.sha256}, "f3_dataset_id": provenance["f3_dataset_id"], "f3_provenance_sha256": _sha256_file(provenance_path), "osm_objects_sha256": _sha256_file(objects_path), "associations_sha256": _sha256_file(associations_path), "osm_snapshot_id": provenance["inputs"]["osm"]["osm_snapshot_id"]},
        "partitions": {"policy": "location_and_spatial_group_no_variant_split_v1", "development": development_count, "evaluation": len(selected) - development_count, "evaluation_frozen": True},
        "observations": observations,
        "limitations": ["synthetic_osm_not_human_in_situ", "text_and_candidate_representation_share_osm_source", "no_visibility_evidence", "not_valid_for_claims_about_human_descriptions", "not_sufficient_alone_for_osm_prefilter_or_rerank_selection", "all_descriptions_require_human_review"],
    }
    document["benchmark_id"] = benchmark_id(document)
    validate_synthetic_benchmark(document)
    return document


def build_candidate_evidence(rows: Sequence[Mapping[str, Any]], objects: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for association in rows:
        obj = objects.get(association["osm_ref"])
        if obj is None or obj["geometry_status"] != "valid": continue
        semantic_type, tag_evidence = classify_object(obj)
        if semantic_type is None: continue
        relation = association_relation(association)
        if relation is None: continue
        output.append({"osm_ref": obj["osm_ref"], "osm_type": obj["osm_type"], "osm_id": obj["osm_id"], "geometry_role": obj["geometry_role"], "semantic_type": semantic_type, "name": safe_name(obj["tags"]), "relation": relation, "center_distance_m": association["center_distance_m"], "tag_evidence": tag_evidence})
    return sorted(output, key=lambda row: (row["center_distance_m"], TYPE_ORDER.index(row["semantic_type"]), row["osm_type"], row["osm_id"]))


def classify_object(obj: Mapping[str, Any]) -> tuple[str | None, dict[str, str]]:
    tags = obj["tags"]
    if tags.get("place") == "square" or tags.get("highway") == "pedestrian" and "plaza" in (tags.get("name", "").casefold()): return "square", _tags(tags, "place", "highway")
    if tags.get("leisure") in {"park", "garden"}: return "park", _tags(tags, "leisure")
    if tags.get("amenity") == "place_of_worship": return "church", _tags(tags, "amenity", "religion", "denomination")
    if tags.get("historic") in {"monument", "memorial"} or tags.get("tourism") == "artwork": return "monument", _tags(tags, "historic", "tourism", "memorial", "artwork_type")
    if obj["geometry_role"] == "line" and tags.get("highway") in {"residential", "tertiary", "pedestrian", "living_street", "footway", "service"}: return "street", _tags(tags, "highway")
    if obj["geometry_role"] == "area" and "building" in tags: return "building", _tags(tags, "building")
    if "shop" in tags or tags.get("amenity") in {"restaurant", "cafe", "bar", "pub", "school", "college", "library", "theatre", "marketplace", "pharmacy", "bank"}: return "commercial", _tags(tags, "shop", "amenity")
    return None, {}


def association_relation(row: Mapping[str, Any]) -> str | None:
    if row["touches"]: return "touches_cell_boundary"
    if row["contains"]: return "contains_cell"
    if row["within"]: return "inside_cell"
    if row["crosses"]: return "crosses_cell"
    if row["overlaps"]: return "overlaps_cell"
    if row["intersects"]: return "intersects_cell"
    return None


def build_description(evidence: Sequence[Mapping[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    chosen = []
    for semantic_type in TYPE_ORDER:
        match = next((row for row in evidence if row["semantic_type"] == semantic_type and row["center_distance_m"] <= 45), None)
        if match is not None: chosen.append(dict(match))
        if len(chosen) == 4: break
    if len(chosen) < 3 or len({row["semantic_type"] for row in chosen}) < 2: return None, []
    phrases = []
    for row in chosen:
        label = TYPE_LABELS[row["semantic_type"]]
        relation = row["relation"]
        plural = row["semantic_type"] in {"building", "commercial"}
        if relation == "inside_cell": phrases.append(f"dentro de la zona cartográfica {'hay' if plural else 'aparece'} {label}")
        elif relation == "crosses_cell": phrases.append(f"{label} {'cruzan' if plural else 'cruza'} la zona cartográfica")
        elif relation == "contains_cell": phrases.append(f"{label} {'contienen' if plural else 'contiene'} la zona de referencia")
        elif relation == "overlaps_cell": phrases.append(f"{label} {'se solapan' if plural else 'se solapa'} con la zona cartográfica")
        elif relation == "touches_cell_boundary": phrases.append(f"{label} {'tocan' if plural else 'toca'} el borde de la zona cartográfica")
        else:
            band = "muy próximo al punto de referencia" if row["center_distance_m"] <= 15 else "próximo al punto de referencia"
            phrases.append(f"{band} se encuentra {label}")
    text = "En la cartografía de esta zona urbana, " + "; ".join(phrases[:-1]) + "; además, " + phrases[-1] + "."
    return text, chosen


def quality_metrics(text: str, evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    types = sorted({row["semantic_type"] for row in evidence})
    warnings = []
    if len(evidence) < 3: warnings.append("too_few_entities")
    if len(types) < 2: warnings.append("low_type_diversity")
    if len(text) < 120: warnings.append("description_too_short")
    if any(value in text for value in ("MADP_", "node/", "way/")): warnings.append("internal_identifier_leak")
    return {"entity_count": len(evidence), "relation_count": len(evidence), "semantic_types": types, "character_count": len(text), "warnings": warnings, "passes_automatic_quality": not warnings}


def spatial_select(candidates: Sequence[Mapping[str, Any]], *, count: int, seed: int, minimum_spacing_m: float) -> list[Mapping[str, Any]]:
    ordered = sorted(candidates, key=lambda row: row["candidate"].candidate_id)
    rng = random.Random(seed)
    first = ordered[rng.randrange(len(ordered))]
    selected = [first]; used_texts = {first["description"]}; remaining = [row for row in ordered if row is not first]
    while remaining and len(selected) < count:
        scored = []
        for row in remaining:
            if row["description"] in used_texts: continue
            distance = min(math.hypot(row["candidate"].center_easting_m - chosen["candidate"].center_easting_m, row["candidate"].center_northing_m - chosen["candidate"].center_northing_m) for chosen in selected)
            scored.append((distance, row["candidate"].candidate_id, row))
        if not scored: break
        distance, _, chosen = max(scored, key=lambda value: (value[0], value[1]))
        if distance < minimum_spacing_m: break
        selected.append(chosen); used_texts.add(chosen["description"]); remaining.remove(chosen)
    selected.sort(key=lambda row: row["candidate"].candidate_id)
    return selected


def spatial_group_id(candidate, block_size_m: float = 150.0) -> str:
    return f"block-{math.floor(candidate.center_easting_m / block_size_m)}-{math.floor(candidate.center_northing_m / block_size_m)}"


def spatial_group_partitions(selected: Sequence[Mapping[str, Any]], *, development_fraction: float, seed: int) -> dict[str, str]:
    groups = sorted({spatial_group_id(row["candidate"]) for row in selected}, key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest())
    if len(groups) < 2: raise SyntheticBenchmarkError("no hay bloques espaciales suficientes para particionar")
    development_groups = max(1, min(len(groups) - 1, round(len(groups) * development_fraction)))
    return {group: "development" if index < development_groups else "evaluation" for index, group in enumerate(groups)}


def validate_synthetic_benchmark(document: Mapping[str, Any]) -> dict[str, Any]:
    if document["benchmark_id"] != benchmark_id(document) or document["protocol"]["ground_truth_kind"] != "synthetic_osm" or document["protocol"]["human_observation"] is not False:
        raise SyntheticBenchmarkError("identidad o separación synthetic_osm inválida")
    ids, texts, locations = set(), set(), set(); group_partitions = {}
    for row in document["observations"]:
        if row["observation_id"] in ids or row["description"]["text"] in texts or row["location_id"] in locations: raise SyntheticBenchmarkError("duplicado synthetic_osm")
        ids.add(row["observation_id"]); texts.add(row["description"]["text"]); locations.add(row["location_id"])
        previous = group_partitions.setdefault(row["spatial_group_id"], row["partition"])
        if previous != row["partition"]: raise SyntheticBenchmarkError("grupo espacial cruza particiones")
        if row["source_type"] != "synthetic_osm" or row["review"]["status"] not in {"pending", "approved", "rejected"} or row["reference"]["synthetic_coordinate_not_gnss"] is not True: raise SyntheticBenchmarkError("registro sintético se presenta como real o tiene estado inválido")
        if row["review"]["status"] == "pending" and any(row["review"][field] is not None for field in ("reviewer", "reviewed_at_utc")): raise SyntheticBenchmarkError("review pending contiene revisor")
        if row["review"]["status"] == "approved" and (not row["review"]["reviewer"] or not str(row["review"]["reviewed_at_utc"]).endswith("Z") or row["review"]["osm_consistency_approved"] is not True): raise SyntheticBenchmarkError("review approved incompleta")
        if row["review"]["status"] == "rejected" and (not row["review"]["reviewer"] or not row["review"]["rejection_reasons"]): raise SyntheticBenchmarkError("review rejected incompleta")
        if row["reference"]["madrid-25m"]["status"] != "assigned" or row["reference"]["madrid-50m"]["status"] != "assigned": raise SyntheticBenchmarkError("posición sintética sin celda GT inequívoca")
        if not row["quality"]["passes_automatic_quality"] or len(row["evidence"]) < 3: raise SyntheticBenchmarkError("observación sin calidad automática mínima")
        if row["description"]["visibility_claimed"] or row["description"]["orientation_claimed"] or row["description"]["contains_coordinates"] or row["description"]["contains_internal_ids"]: raise SyntheticBenchmarkError("descripción sintética contiene fuga o afirmación no soportada")
        evidence_ids = {item["osm_ref"] for item in row["evidence"]}
        if len(evidence_ids) != len(row["evidence"]): raise SyntheticBenchmarkError("evidencia OSM duplicada")
        for item in row["evidence"]:
            if item["relation"] not in {"inside_cell", "crosses_cell", "contains_cell", "overlaps_cell", "touches_cell_boundary", "intersects_cell"} or not isinstance(item["center_distance_m"], (int, float)) or item["center_distance_m"] < 0 or not item["tag_evidence"]:
                raise SyntheticBenchmarkError("evidencia OSM sin predicado, distancia o tags")
    distances = []
    for index, left in enumerate(document["observations"]):
        for right in document["observations"][index + 1:]: distances.append(haversine_m(left["reference"]["latitude"], left["reference"]["longitude"], right["reference"]["latitude"], right["reference"]["longitude"]))
    minimum = min(distances) if distances else None
    if minimum is not None and minimum + 0.5 < document["protocol"]["minimum_spacing_m"]:
        raise SyntheticBenchmarkError("separación espacial inferior al protocolo")
    return {"observations": len(ids), "development": sum(row["partition"] == "development" for row in document["observations"]), "evaluation": sum(row["partition"] == "evaluation" for row in document["observations"]), "minimum_pair_distance_m": minimum, "mean_entities": statistics.fmean(row["quality"]["entity_count"] for row in document["observations"]) if document["observations"] else None}


def validate_benchmark_against_f3(document: Mapping[str, Any], *, catalog_50, catalog_25, f3_bundle: Path) -> None:
    files = {"f3_provenance_sha256": f3_bundle / "provenance.json", "osm_objects_sha256": f3_bundle / "osm_objects.jsonl", "associations_sha256": f3_bundle / "candidate_osm_associations.jsonl"}
    for field, path in files.items():
        if not path.is_file() or document["inputs"][field] != _sha256_file(path): raise SyntheticBenchmarkError(f"input F3 no corresponde: {field}")
    objects = {row["osm_ref"]: row for row in load_jsonl(files["osm_objects_sha256"])}
    associations = defaultdict(dict)
    for row in load_jsonl(files["associations_sha256"]): associations[row["candidate_id"]][row["osm_ref"]] = row
    candidates50 = {row.candidate_id: row for row in catalog_50.candidates}
    for observation in document["observations"]:
        reference = observation["reference"]; candidate_id = reference["madrid-50m"]["candidate_id"]
        candidate = candidates50.get(candidate_id)
        if candidate is None or candidate.latitude != reference["latitude"] or candidate.longitude != reference["longitude"] or candidate.center_easting_m != reference["easting_m"] or candidate.center_northing_m != reference["northing_m"]:
            raise SyntheticBenchmarkError("posición sintética no corresponde al centro F1 declarado")
        if assign_reference(reference["latitude"], reference["longitude"], catalog_50) != reference["madrid-50m"] or assign_reference(reference["latitude"], reference["longitude"], catalog_25) != reference["madrid-25m"]:
            raise SyntheticBenchmarkError("asignación sintética no corresponde a catálogos")
        for evidence in observation["evidence"]:
            association = associations[candidate_id].get(evidence["osm_ref"]); obj = objects.get(evidence["osm_ref"])
            if association is None or obj is None: raise SyntheticBenchmarkError("evidencia no existe en F3")
            semantic_type, tag_evidence = classify_object(obj)
            if semantic_type != evidence["semantic_type"] or tag_evidence != evidence["tag_evidence"] or association_relation(association) != evidence["relation"] or association["center_distance_m"] != evidence["center_distance_m"] or obj["geometry_role"] != evidence["geometry_role"]:
                raise SyntheticBenchmarkError("evidencia persistida no corresponde a F3")


def render_benchmark_html(document: Mapping[str, Any], output: Path) -> None:
    rows = []
    for observation in document["observations"]:
        evidence = "".join(f'<li><code>{escape(item["osm_ref"])}</code>: {escape(item["semantic_type"])}; {escape(item["relation"])}; {item["center_distance_m"]:.1f} m</li>' for item in observation["evidence"])
        rows.append(f'<article><h2>{escape(observation["observation_id"])} · {escape(observation["partition"])}</h2><p>{escape(observation["description"]["text"])}</p><p>WGS84: {observation["reference"]["latitude"]}, {observation["reference"]["longitude"]}</p><ul>{evidence}</ul><p>25 m: <code>{escape(observation["reference"]["madrid-25m"]["candidate_id"])}</code><br>50 m: <code>{escape(observation["reference"]["madrid-50m"]["candidate_id"])}</code></p><p>Revisión: <strong>pending</strong></p></article>')
    html = '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>F5.5c synthetic_osm</title><style>body{font:16px system-ui;max-width:1100px;margin:auto;padding:2rem;background:#eef1eb}article{background:white;padding:1rem;margin:1rem 0;border-left:5px solid #356859}code{overflow-wrap:anywhere}</style></head><body><h1>Benchmark sintético OSM F5.5c</h1><p>No son observaciones humanas ni evidencia de visibilidad. Todas las descripciones están pendientes de revisión.</p>' + "".join(rows) + '</body></html>'
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(html, encoding="utf-8")


def synthetic_evaluation_adapter(document: Mapping[str, Any]) -> dict[str, Any]:
    validate_synthetic_benchmark(document)
    observations = []
    for row in document["observations"]:
        if row["review"]["status"] != "approved": continue
        observations.append({"source_query_id": row["observation_id"], "location_id": row["location_id"], "derivation_group_id": row["derivation_group_id"], "spatial_group_id": row["spatial_group_id"], "partition": row["partition"], "source_type": "synthetic_osm", "description": dict(row["description"]), "reference": dict(row["reference"]), "review_status": "approved", "benchmark_id": document["benchmark_id"]})
    return {"schema_version": "1.0", "contract_version": "f55c-synthetic-evaluation-input-v1", "benchmark_id": document["benchmark_id"], "ground_truth_kind": "synthetic_osm", "real_ground_truth": False, "metric_definitions": {"recall_at_k": "f54_exact_candidate_membership", "top1_error_m": "f54_haversine_to_synthetic_reference", "minimum_error_at_k_m": "f54_haversine_minimum", "geo_recall_at_k": "f54_thresholded_haversine"}, "observations": observations, "excluded_pending": sum(row["review"]["status"] == "pending" for row in document["observations"]), "limitations": ["never_merge_with_real_f54_metrics", "osm_source_overlap", "reviewed_synthetic_descriptions_only"]}


def apply_human_review(document: Mapping[str, Any], decisions: Mapping[str, Any]) -> dict[str, Any]:
    validate_synthetic_benchmark(document)
    if decisions.get("contract_version") != "f55c-synthetic-review-decisions-v1" or not decisions.get("reviewer") or not str(decisions.get("reviewed_at_utc", "")).endswith("Z") or not isinstance(decisions.get("decisions"), list):
        raise SyntheticBenchmarkError("manifiesto de revisión sintética incompatible")
    by_id = {row.get("observation_id"): row for row in decisions["decisions"]}
    expected = {row["observation_id"] for row in document["observations"]}
    if set(by_id) != expected or len(by_id) != len(decisions["decisions"]): raise SyntheticBenchmarkError("la revisión debe cubrir todas las observaciones una vez")
    output = json.loads(json.dumps(document, ensure_ascii=False))
    for row in output["observations"]:
        decision = by_id[row["observation_id"]]
        if decision.get("decision") not in {"approve", "reject"} or not isinstance(decision.get("notes"), str) or not decision["notes"].strip(): raise SyntheticBenchmarkError("decisión sintética incompleta")
        row["review"] = {"status": "approved" if decision["decision"] == "approve" else "rejected", "reviewer": decisions["reviewer"], "reviewed_at_utc": decisions["reviewed_at_utc"], "osm_consistency_approved": decision["decision"] == "approve", "rejection_reasons": [] if decision["decision"] == "approve" else [decision["notes"]], "notes": decision["notes"]}
    output["benchmark_id"] = benchmark_id(output); return output


def safe_name(tags: Mapping[str, str]) -> str | None:
    value = tags.get("name:es") or tags.get("name")
    return value if isinstance(value, str) and 1 <= len(value) <= 120 else None


def _tags(tags: Mapping[str, str], *keys: str) -> dict[str, str]: return {key: tags[key] for key in keys if key in tags}
def _sha256_file(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _canonical_bytes(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
