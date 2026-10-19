#!/usr/bin/env python3
"""Aplica decisiones humanas explícitas a un sidecar F5.2 generado."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = json.loads(args.sidecar.read_text(encoding="utf-8"))
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    if decisions.get("contract_version") != "f52-human-review-decisions-v1" or decisions.get("source_dataset_id") != document["dataset_id"] or not isinstance(decisions.get("reviewer"), str) or not decisions["reviewer"].strip():
        raise ValueError("manifiesto de revisión incompatible")
    by_id = {}
    for observation in document["observations"]:
        for variant in observation["variants"]:
            if variant["variant_id"] is not None:
                by_id[variant["variant_id"]] = variant
    rows = decisions.get("decisions")
    if not isinstance(rows, list) or len({row.get("variant_id") for row in rows}) != len(rows):
        raise ValueError("decisiones duplicadas o inválidas")
    expected = {variant_id for variant_id, variant in by_id.items() if variant["status"] == "generated"}
    if {row.get("variant_id") for row in rows} != expected:
        raise ValueError("la revisión debe cubrir exactamente todas las variantes generadas")
    for row in rows:
        decision = row.get("decision")
        if decision not in {"approve", "reject"} or not isinstance(row.get("notes"), str) or not row["notes"].strip():
            raise ValueError("cada decisión requiere approve/reject y notas")
        variant = by_id[row["variant_id"]]
        variant["status"] = "reviewed" if decision == "approve" else "rejected"
        variant["review_status"] = "reviewed" if decision == "approve" else "rejected"
    document["dataset_version"] += "-human-reviewed"
    document["dataset_id"] = textual_variant_dataset_id(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"dataset_id": document["dataset_id"], "approved": sum(row["decision"] == "approve" for row in rows), "rejected": sum(row["decision"] == "reject" for row in rows), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
