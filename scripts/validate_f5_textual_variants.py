#!/usr/bin/env python3
"""Valida un sidecar F5.1 contra su dataset F4.3 y catálogo F1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_textual_variants import paired_variant_plan, source_dataset_sha256, validate_textual_variant_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--source-query-dataset", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--print-paired-plan", action="store_true")
    args = parser.parse_args()

    catalog = load_verified_f1_catalog(args.manifest, load_region_config(args.config))
    source = json.loads(args.source_query_dataset.read_text(encoding="utf-8"))
    document = json.loads(args.dataset.read_text(encoding="utf-8"))
    summary = validate_textual_variant_dataset(
        document,
        source,
        source_sha256=source_dataset_sha256(args.source_query_dataset),
        catalog=catalog,
    )
    output = {**summary, "status": "valid"}
    if args.print_paired_plan:
        output["paired_variant_plan"] = paired_variant_plan(document)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
