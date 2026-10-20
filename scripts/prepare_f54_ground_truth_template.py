#!/usr/bin/env python3
"""Materializa y valida la plantilla vacía F5.4 contra F4.3 y ambos catálogos."""

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
from src.tfg_phase0.f5_ground_truth_evaluation import ground_truth_dataset_id, validate_ground_truth_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-query-dataset", type=Path, default=ROOT / "config/madrid_f43_query_dataset_draft.json")
    parser.add_argument("--catalog-25m", type=Path, default=ROOT / "data/processed/catalog/manifest-25m.json")
    parser.add_argument("--catalog-50m", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--template", type=Path, default=ROOT / "config/madrid_f54_ground_truth_template.json")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_raw = args.source_query_dataset.read_bytes(); source = json.loads(source_raw)
    config = load_region_config(ROOT / "config/madrid.yaml")
    catalogs = {"madrid-25m": load_verified_f1_catalog(args.catalog_25m, config), "madrid-50m": load_verified_f1_catalog(args.catalog_50m, config)}
    document = json.loads(args.template.read_text(encoding="utf-8"))
    document["source_query_dataset"] = {"dataset_id": source["dataset_id"], "sha256": hashlib.sha256(source_raw).hexdigest()}
    document["catalogs"] = {gallery: {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": len(catalog.candidates), "cell_size_m": catalog.cell_size_m} for gallery, catalog in catalogs.items()}
    document["dataset_id"] = ground_truth_dataset_id(document)
    summary = validate_ground_truth_dataset(document, source, catalogs, source_sha256=hashlib.sha256(source_raw).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
