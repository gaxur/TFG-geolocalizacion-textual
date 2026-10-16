#!/usr/bin/env python3
"""Valida y audita un dataset de consultas F4.3 sin ejecutar el modelo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import assign_reference, validate_query_dataset
from src.tfg_phase0.f4_validation import load_verified_f1_50m


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--print-assignments", action="store_true")
    args = parser.parse_args()
    catalog = load_verified_f1_50m(args.manifest, load_region_config(args.config))
    document = json.loads(args.dataset.read_text(encoding="utf-8"))
    audit = validate_query_dataset(document, catalog)
    references = {}
    for query in document["queries"]:
        reference = query["reference"]
        if reference["status"] == "validated":
            references[query["query_id"]] = assign_reference(
                reference["latitude"], reference["longitude"], catalog,
                reported_accuracy_m=reference["reported_accuracy_m"],
            )
    output = {
        "dataset_id": document["dataset_id"],
        "query_count": len(document["queries"]),
        "development_count": sum(query["partition"] == "development" for query in document["queries"]),
        "evaluation_count": sum(query["partition"] == "evaluation" for query in document["queries"]),
        "validated_reference_count": len(references),
        "pending_reference_count": sum(query["reference"]["status"] == "pending" for query in document["queries"]),
        "partition_audit": audit,
        "status": "valid",
    }
    if args.print_assignments:
        output["assignments"] = references
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
