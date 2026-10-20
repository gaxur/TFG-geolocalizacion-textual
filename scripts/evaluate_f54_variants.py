#!/usr/bin/env python3
"""Evalúa un ranking F5.2 de cinco variantes contra Ground Truth F5.4 validado."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_ground_truth_evaluation import evaluate_variant_rankings, validate_ground_truth_dataset
from src.tfg_phase0.f5_textual_variants import validate_textual_variant_dataset
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--source-query-dataset", required=True, type=Path)
    parser.add_argument("--variants", required=True, type=Path)
    parser.add_argument("--ranking-report", required=True, type=Path)
    parser.add_argument("--catalog-25m", type=Path, default=ROOT / "data/processed/catalog/manifest-25m.json")
    parser.add_argument("--catalog-50m", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--distance-threshold-m", action="append", type=float)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    config = load_region_config(ROOT / "config/madrid.yaml")
    catalogs = {"madrid-25m": load_verified_f1_catalog(args.catalog_25m, config), "madrid-50m": load_verified_f1_catalog(args.catalog_50m, config)}
    source_raw = args.source_query_dataset.read_bytes(); source = json.loads(source_raw)
    gt_raw = args.ground_truth.read_bytes(); gt = json.loads(gt_raw)
    variant_raw = args.variants.read_bytes(); variants = json.loads(variant_raw)
    ranking_raw = args.ranking_report.read_bytes(); ranking = json.loads(ranking_raw)
    validate_ground_truth_dataset(gt, source, catalogs, source_sha256=hashlib.sha256(source_raw).hexdigest())
    validate_textual_variant_dataset(variants, source, source_sha256=hashlib.sha256(source_raw).hexdigest(), catalog=catalogs["madrid-50m"])
    validate_document(ranking, "f5_variant_ranking_report")
    document = evaluate_variant_rankings(gt, variants, ranking, gt_sha256=hashlib.sha256(gt_raw).hexdigest(), variant_sha256=hashlib.sha256(variant_raw).hexdigest(), ranking_sha256=hashlib.sha256(ranking_raw).hexdigest(), distance_thresholds_m=args.distance_threshold_m or (25, 50, 100, 500))
    validate_document(document, "f5_geographic_evaluation")
    final = args.output_root / document["evaluation_id"]
    raw = (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if final.exists():
        if (final / "evaluation.json").read_bytes() != raw: raise RuntimeError("evaluación F5.4 existente incompatible")
    else:
        args.output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".f54-evaluation-", dir=args.output_root) as temporary:
            path = Path(temporary); (path / "evaluation.json").write_bytes(raw); os.replace(path, final)
    print(json.dumps({"evaluation_id": document["evaluation_id"], "coverage": document["coverage"], "output": str(final)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
