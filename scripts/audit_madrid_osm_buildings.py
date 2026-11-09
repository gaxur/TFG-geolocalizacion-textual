#!/usr/bin/env python3
"""Audita tags de edificios en el snapshot XML OSM inmutable de D004.

El informe cuenta tags presentes y valores numéricos interpretables; no crea
alturas, no transforma niveles en metros y no constituye cobertura topográfica.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.validation import validate_document


NUMBER_WITH_OPTIONAL_METERS = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m)?\s*$", re.IGNORECASE)
NUMBER = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*$")


def _numeric_tag(tags: dict[str, str], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        raw = tags.get(key)
        if raw is None or not raw.strip():
            continue
        match = NUMBER_WITH_OPTIONAL_METERS.fullmatch(raw) if key.endswith("height") else NUMBER.fullmatch(raw)
        if match:
            value = float(match.group(1))
            if value > 0:
                return value
    return None


def _is_building(tags: dict[str, str]) -> bool:
    return any(tags.get(key, "").strip().lower() not in {"", "no", "false"} for key in ("building", "building:part"))


def _tags(element: ET.Element) -> dict[str, str]:
    return {item.attrib["k"]: item.attrib["v"] for item in element.findall("tag") if "k" in item.attrib and "v" in item.attrib}


def summarize_osm_xml(source: str | Path | BinaryIO) -> dict[str, Any]:
    """Cuenta edificios y atributos desde OSM XML sin retener el documento entero."""
    counters = {
        "osm_elements": {"node": 0, "way": 0, "relation": 0},
        "building_nodes": 0,
        "building_ways": 0,
        "closed_building_ways": 0,
        "open_building_ways": 0,
        "closed_area_no_building_ways": 0,
        "building_relations": 0,
        "multipolygon_building_relations": 0,
        "footprint_candidates": 0,
        "tag_counts": {
            "height": 0,
            "building:height": 0,
            "building:levels": 0,
            "building:levels:aboveground": 0,
            "min_height": 0,
            "building:min_level": 0,
        },
        "height_values": {
            "explicit_numeric_height": 0,
            "height_tag_unparsed_or_nonpositive": 0,
            "levels_only_not_converted_to_meters": 0,
            "height_and_levels_unknown": 0,
        },
    }

    iterator = ET.iterparse(source, events=("end",))
    for _, element in iterator:
        kind = element.tag
        if kind not in counters["osm_elements"]:
            continue
        counters["osm_elements"][kind] += 1
        tags = _tags(element)
        building = _is_building(tags)
        if kind == "node":
            if building:
                counters["building_nodes"] += 1
            element.clear()
            continue
        if not building:
            element.clear()
            continue

        footprint_candidate = False
        if kind == "way":
            counters["building_ways"] += 1
            refs = [nd.attrib.get("ref") for nd in element.findall("nd")]
            closed = len(refs) >= 4 and refs[0] == refs[-1]
            if closed:
                counters["closed_building_ways"] += 1
                if tags.get("area", "").strip().lower() == "no":
                    counters["closed_area_no_building_ways"] += 1
                else:
                    counters["footprint_candidates"] += 1
                    footprint_candidate = True
            else:
                counters["open_building_ways"] += 1
        else:
            counters["building_relations"] += 1
            if tags.get("type") in {"multipolygon", "building"}:
                counters["multipolygon_building_relations"] += 1
                counters["footprint_candidates"] += 1
                footprint_candidate = True

        for key in counters["tag_counts"]:
            if tags.get(key, "").strip():
                counters["tag_counts"][key] += 1

        if footprint_candidate:
            has_height_tag = any(tags.get(key, "").strip() for key in ("height", "building:height"))
            height = _numeric_tag(tags, ("height", "building:height"))
            levels = _numeric_tag(tags, ("building:levels", "building:levels:aboveground"))
            if height is not None:
                counters["height_values"]["explicit_numeric_height"] += 1
            elif has_height_tag:
                counters["height_values"]["height_tag_unparsed_or_nonpositive"] += 1
            elif levels is not None:
                counters["height_values"]["levels_only_not_converted_to_meters"] += 1
            else:
                counters["height_values"]["height_and_levels_unknown"] += 1
        element.clear()

    footprint_count = counters["footprint_candidates"]
    counters["coverage_percent"] = {
        key: round(100 * value / footprint_count, 4) if footprint_count else None
        for key, value in counters["height_values"].items()
    }
    counters["interpretation"] = {
        "height_is_measured": False,
        "levels_were_converted_to_meters": False,
        "denominator": "closed building ways plus tagged building multipolygon relations",
        "notes": [
            "A los multipolígonos se les cuenta como un objeto; sus ways miembros pueden aparecer también por separado.",
            "Los nodos etiquetados building se contabilizan, pero no entran en el denominador de huellas poligonales.",
            "Los valores no numéricos/unidades no reconocidas se informan como no interpretables, nunca se reparan.",
        ],
    }
    return counters


def audit_snapshot(snapshot_dir: Path, config_path: Path) -> dict[str, Any]:
    source_path = snapshot_dir / "source.osm"
    provenance_path = snapshot_dir / "provenance.json"
    checksum_path = snapshot_dir / "sha256.txt"
    for path in (source_path, provenance_path, checksum_path):
        if not path.is_file():
            raise FileNotFoundError(f"Falta artefacto del snapshot: {path}")

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    validate_document(provenance, "osm_snapshot")
    config = load_region_config(config_path)
    if provenance["bbox"] != config["region"]["bbox"]:
        raise ValueError("La bbox del snapshot no coincide exactamente con D004")
    if provenance["license"] != "ODbL-1.0":
        raise ValueError("El snapshot no declara ODbL-1.0")

    digest = hashlib.sha256()
    size = 0
    with source_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    sha256 = digest.hexdigest()
    if sha256 != provenance["raw_sha256"] or size != provenance["raw_size_bytes"]:
        raise ValueError("El raw OSM no coincide con SHA-256/tamaño de provenance")
    if checksum_path.read_text(encoding="ascii").strip() != sha256:
        raise ValueError("sha256.txt no coincide con el raw OSM")
    if provenance["osm_snapshot_id"].rsplit("-", 1)[-1] != sha256:
        raise ValueError("osm_snapshot_id no corresponde al raw OSM")

    return {
        "schema_version": "1.0",
        "contract_version": "madrid-osm-building-audit-v1",
        "snapshot_id": provenance["osm_snapshot_id"],
        "raw_sha256": sha256,
        "raw_size_bytes": size,
        "acquired_at_utc": provenance["acquired_at_utc"],
        "bbox": provenance["bbox"],
        "crs": "EPSG:4326",
        "license": provenance["license"],
        "attribution": provenance["attribution"],
        "building_audit": summarize_osm_xml(source_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--output", type=Path, help="JSON de auditoría local (no se publica por defecto)")
    args = parser.parse_args()
    report = audit_snapshot(args.snapshot_dir, args.config)
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"No se sobrescribe el informe existente: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
