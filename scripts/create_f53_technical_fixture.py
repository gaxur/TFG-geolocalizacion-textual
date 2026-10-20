#!/usr/bin/env python3
"""Crea un sidecar técnico F5.3 con 10 casos originales sin ground truth."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id


CASES = (
    ("plaza-mayor", "Estoy cerca de Plaza Mayor, junto a una calle estrecha.", "Plaza Mayor", "square", "proper_name"),
    ("parque-avenida", "Hay un parque grande al lado de una avenida.", None, None, None),
    ("interseccion", "Estoy en la intersección de dos calles.", None, None, None),
    ("negacion-parque", "No hay ningún parque cerca de esta intersección.", None, None, None),
    ("estacion-norte", "La estación está al norte de la plaza.", None, None, None),
    ("iglesia-izquierda", "Veo una iglesia a mi izquierda.", None, None, None),
    ("sin-orientacion", "Estoy junto a una plaza; mi orientación es desconocida.", None, None, None),
    ("toponimo-ambiguo", "Estoy cerca de Sol.", "Sol", "other", "proper_name"),
    ("tres-entidades", "Estoy entre una plaza, una iglesia y una estación.", None, None, None),
    ("sin-geografia", "El ambiente es agradable.", None, None, None),
)


def pending(kind: str, language: str) -> dict:
    return {"variant_id": None, "kind": kind, "status": "pending", "text": None, "language": language, "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None}, "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text())
    observations = []
    for index, (case, text, name, entity_type, name_kind) in enumerate(CASES, 1):
        toponyms = []
        if name:
            start = text.index(name)
            toponyms.append({"mention": name, "span": {"start": start, "end": start + len(name)}, "entity_type": entity_type, "name_kind": name_kind, "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"})
        original = {"variant_id": f"f53-technical-{case}-es-original", "kind": "es_original", "status": "reviewed", "text": text, "language": "es", "generation": {"method": "original", "tool_or_model": "manual", "version": "v1", "configuration_or_prompt": "f53-technical-fixture", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}
        observations.append({"source_query_id": f"f53-technical-{case}", "source_input_sha256": hashlib.sha256(text.encode()).hexdigest(), "partition": "development", "location_id": None, "derivation_group_id": f"f53-technical-{case}", "toponyms": toponyms, "orientation": {"status": "absent", "cardinal": None, "bearing_degrees": None, "bearing_convention": None, "method": None, "uncertainty_degrees": None, "provenance": None, "verification_status": "not_applicable", "relative_relations_present": any(value in text.casefold() for value in ("izquierda", "derecha", "delante", "detrás")), "notes": "Fixture técnica F5.3 sin ground truth."}, "variants": [original, pending("es_cartographic", "es"), pending("en_conventional", "en"), pending("en_toponym_preserved", "en")], "notes": "No utilizar como evaluación."})
    document["dataset_version"] = "f53-technical-smoke-v1"
    document["observations"] = observations
    document["dataset_id"] = textual_variant_dataset_id(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"technical_fixture": True, "observations": len(observations), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
