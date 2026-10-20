#!/usr/bin/env python3
"""Crea fixture técnica F4.3/F5.1 para smoke Qwen; no es evaluación."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import query_dataset_id
from src.tfg_phase0.f4_validation import load_verified_f1_50m
from src.tfg_phase0.f5_textual_variants import source_query_input_sha256, textual_variant_dataset_id


CASES = (
    ("square", "Estoy cerca de la Plaza Mayor, junto a una calle estrecha.", [("Plaza Mayor", "square", "proper_name")], False),
    ("park", "Hay un parque grande al lado de una avenida.", [("un parque grande", "other", "generic_expression"), ("una avenida", "avenue", "generic_expression")], False),
    ("gran-via", "Estoy entre Gran Vía y una plaza con varios edificios.", [("Gran Vía", "avenue", "proper_name"), ("una plaza", "square", "generic_expression")], False),
    ("negation", "No hay ningún parque cerca de esta intersección.", [("ningún parque", "other", "generic_expression"), ("esta intersección", "other", "generic_expression")], False),
    ("cardinal", "La estación está al norte de la plaza.", [("La estación", "station", "generic_expression"), ("la plaza", "square", "generic_expression")], False),
    ("relative", "Veo una iglesia a mi izquierda y una calle a la derecha.", [("una iglesia", "building", "generic_expression"), ("una calle", "street", "generic_expression")], True),
)


def pending(kind: str, language: str) -> dict:
    return {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": language, "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}


def query(case_id: str, text: str) -> dict:
    return {"query_id": f"f52-technical-{case_id}-es", "location_id": None, "derivation_group_id": f"f52-technical-{case_id}", "partition": "development", "description": {"text": text, "language": "es", "contains_coordinates": False}, "provenance": {"source_type": "technical_probe", "description": "Sonda técnica F5.2b sin observación independiente ni ground truth.", "independent_environment_observation": False, "instructions_version": "f52-technical-smoke-v1", "collected_at_utc": None}, "reference": {"status": "pending", "latitude": None, "longitude": None, "crs": None, "capture_method": None, "reported_accuracy_m": None, "validation_method": None, "catalog_assignment": None}, "ambiguity": {"status": "unreviewed", "notes": "No utilizar como evaluación geográfica."}, "validation_status": "pending"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    config = load_region_config(ROOT / "config/madrid.yaml")
    catalog = load_verified_f1_50m(ROOT / "data/processed/catalog/manifest-50m.json", config)
    queries = [query(case_id, text) for case_id, text, _, _ in CASES]
    dataset = {"schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "f4-madrid-queries-sha256-" + "0" * 64, "dataset_version": "f52-technical-smoke-v1", "region": {"region_id": "madrid_pilot", "bbox_wgs84": dict(config["region"]["bbox"])}, "catalog": {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": 253, "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"}, "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": 0.8}, "queries": queries}
    dataset["dataset_id"] = query_dataset_id(dataset)
    dataset_raw = (json.dumps(dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    observations = []
    for source, (case_id, text, mentions, relative) in zip(queries, CASES):
        toponyms = []
        for mention, entity_type, name_kind in mentions:
            start = text.index(mention)
            toponyms.append({"mention": mention, "span": {"start": start, "end": start + len(mention)}, "entity_type": entity_type, "name_kind": name_kind, "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"})
        orientation = {"status": "absent", "cardinal": None, "bearing_degrees": None, "bearing_convention": None, "method": None, "uncertainty_degrees": None, "provenance": None, "verification_status": "not_applicable", "relative_relations_present": relative, "notes": "Relación egocéntrica sin orientación cardinal." if relative else None}
        original = {"variant_id": f"{source['query_id']}-es-original-v1", "kind": "es_original", "status": "reviewed", "text": text, "language": "es", "generation": {"method": "original", "tool_or_model": "manual", "version": "v1", "configuration_or_prompt": "copy-from-f43", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        observations.append({"source_query_id": source["query_id"], "source_input_sha256": source_query_input_sha256(source), "partition": "development", "location_id": None, "derivation_group_id": source["derivation_group_id"], "toponyms": toponyms, "orientation": orientation, "variants": [original, pending("es_cartographic", "es"), pending("en_conventional", "en"), pending("en_toponym_preserved", "en"), pending("en_cartographic", "en")], "notes": "Fixture técnica F5.3b; no evaluación."})
    template = json.loads((ROOT / "config/madrid_f53b_textual_variants_template.json").read_text())
    template["dataset_version"] = "f52-technical-smoke-v1"
    template["source_query_dataset"] = {"dataset_id": dataset["dataset_id"], "sha256": hashlib.sha256(dataset_raw).hexdigest()}
    template["observations"] = observations
    template["dataset_id"] = textual_variant_dataset_id(template)
    sidecar_raw = (json.dumps(template, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "query-dataset.json").write_bytes(dataset_raw)
    (args.output_dir / "sidecar-f51.json").write_bytes(sidecar_raw)
    print(json.dumps({"technical_fixture": True, "queries": len(queries), "query_dataset": str(args.output_dir / "query-dataset.json"), "sidecar": str(args.output_dir / "sidecar-f51.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
