#!/usr/bin/env python3
"""Importa únicamente registros F5.5 aprobados a contratos F4.3/F5.4."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import validate_query_dataset
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_evidence_acquisition import import_approved_field_records, import_approved_panoramax_reviews
from src.tfg_phase0.f5_ground_truth_evaluation import validate_ground_truth_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--field-record", action="append", type=Path)
    source.add_argument("--panoramax-review", type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--catalog-25m", type=Path, default=ROOT / "data/processed/catalog/manifest-25m.json")
    parser.add_argument("--catalog-50m", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    args = parser.parse_args()
    config = load_region_config(ROOT / "config/madrid.yaml")
    catalogs = {"madrid-25m": load_verified_f1_catalog(args.catalog_25m, config), "madrid-50m": load_verified_f1_catalog(args.catalog_50m, config)}
    if args.field_record:
        records = [json.loads(path.read_text(encoding="utf-8")) for path in args.field_record]
        source_dataset, gt_dataset, counts = import_approved_field_records(records, evidence_root=args.evidence_root, catalogs=catalogs)
    else:
        queue = json.loads(args.panoramax_review.read_text(encoding="utf-8"))
        source_dataset, gt_dataset, counts = import_approved_panoramax_reviews(queue, evidence_root=args.evidence_root, catalogs=catalogs)
    validate_query_dataset(source_dataset, catalogs["madrid-50m"])
    source_raw = (json.dumps(source_dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if gt_dataset["source_query_dataset"]["sha256"] != hashlib.sha256(source_raw).hexdigest():
        raise RuntimeError("hash interno F5.5 inesperado")
    validate_ground_truth_dataset(gt_dataset, source_dataset, catalogs, source_sha256=gt_dataset["source_query_dataset"]["sha256"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "query-dataset.json").write_bytes(source_raw)
    (args.output_dir / "ground-truth.json").write_text(json.dumps(gt_dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"review_counts": counts, "imported": len(source_dataset["queries"]), "output": str(args.output_dir)}, sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
