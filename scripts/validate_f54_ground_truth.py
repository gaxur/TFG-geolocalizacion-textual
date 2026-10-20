#!/usr/bin/env python3
"""Valida Ground Truth F5.4 y resume preparación y cobertura de ambas galerías."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_ground_truth_evaluation import validate_ground_truth_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--source-query-dataset", required=True, type=Path)
    parser.add_argument("--catalog-25m", type=Path, default=ROOT / "data/processed/catalog/manifest-25m.json")
    parser.add_argument("--catalog-50m", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    args = parser.parse_args()
    source_raw = args.source_query_dataset.read_bytes(); source = json.loads(source_raw)
    document = json.loads(args.dataset.read_text(encoding="utf-8"))
    config = load_region_config(ROOT / "config/madrid.yaml")
    catalogs = {"madrid-25m": load_verified_f1_catalog(args.catalog_25m, config), "madrid-50m": load_verified_f1_catalog(args.catalog_50m, config)}
    summary = validate_ground_truth_dataset(document, source, catalogs, source_sha256=hashlib.sha256(source_raw).hexdigest())
    print(json.dumps({**summary, "status": "valid"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
