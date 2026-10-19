#!/usr/bin/env python3
"""Ejecuta rankings F4.6 independientes para variantes F5.2 elegibles."""

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

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, load_runtime_config
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_textual_variants import source_dataset_sha256, validate_textual_variant_dataset
from src.tfg_phase0.f5_variant_ranking import run_variant_rankings
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--source-query-dataset", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--transformation-run", type=Path)
    parser.add_argument("--runtime-config", type=Path, default=ROOT / "config/madrid_f46_retriever.json")
    parser.add_argument("--region-config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--cvg-utils-sha256", required=True)
    parser.add_argument("--clip-weights", required=True, type=Path)
    parser.add_argument("--gallery", action="append", choices=("madrid-25m", "madrid-50m"), required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--allow-unreviewed-technical", action="store_true")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output-uid", type=int)
    parser.add_argument("--output-gid", type=int)
    args = parser.parse_args()

    sidecar_raw = args.sidecar.read_bytes()
    sidecar = json.loads(sidecar_raw)
    source_dataset = json.loads(args.source_query_dataset.read_text(encoding="utf-8"))
    catalog = load_verified_f1_catalog(args.manifest, load_region_config(args.region_config))
    validate_textual_variant_dataset(sidecar, source_dataset, source_sha256=source_dataset_sha256(args.source_query_dataset), catalog=catalog)
    transformation_run = json.loads(args.transformation_run.read_text(encoding="utf-8")) if args.transformation_run else None
    if transformation_run is not None:
        validate_document(transformation_run, "f5_transformation_run")
        records = {row["variant_id"]: row for row in transformation_run["records"] if row["variant_id"] is not None}
        materialized = {variant["variant_id"]: variant for observation in sidecar["observations"] for variant in observation["variants"] if variant["kind"] != "es_original" and variant["variant_id"] is not None}
        if set(records) != set(materialized):
            raise RuntimeError("el sidecar revisado no contiene exactamente las variantes del run")
        for variant_id, variant in materialized.items():
            record = records[variant_id]
            output_hash = hashlib.sha256(variant["text"].encode()).hexdigest() if variant["text"] is not None else None
            if record["output_text_sha256"] != output_hash or record["kind"] != variant["kind"]:
                raise RuntimeError("el texto revisado no corresponde al output del run")
        if args.allow_unreviewed_technical and transformation_run["transformer"]["real_model_inference"]:
            raise RuntimeError("--allow-unreviewed-technical solo se admite para un smoke fake")
    model, galleries = load_runtime_config(args.runtime_config, project_root=ROOT, cvg_utils_sha256=args.cvg_utils_sha256, clip_weights_path=args.clip_weights)
    retriever = CrossText2LocRetriever.load(model_config=model, gallery_configs=galleries, region_config=args.region_config, deep_validate_visual_assets=False)
    try:
        report = run_variant_rankings(sidecar, retriever, sidecar_sha256=hashlib.sha256(sidecar_raw).hexdigest(), gallery_ids=args.gallery, top_k=args.top_k, transformation_run=transformation_run, allow_unreviewed_technical=args.allow_unreviewed_technical)
    finally:
        retriever.close()
    validate_document(report, "f5_variant_ranking_report")
    final = args.output_root / report["report_id"]
    raw = (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if final.exists():
        if (final / "report.json").read_bytes() != raw:
            raise RuntimeError("informe F5.2 existente incompatible")
    else:
        args.output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".f52-ranking-", dir=args.output_root) as temporary:
            path = Path(temporary)
            (path / "report.json").write_bytes(raw)
            os.replace(path, final)
    if args.output_uid is not None or args.output_gid is not None:
        if args.output_uid is None or args.output_gid is None or args.output_uid < 0 or args.output_gid < 0:
            raise ValueError("--output-uid y --output-gid deben proporcionarse juntos y ser no negativos")
        for path in (final, final / "report.json"):
            os.chown(path, args.output_uid, args.output_gid)
        os.chmod(final, 0o755)
        os.chmod(final / "report.json", 0o644)
    print(json.dumps({"report_id": report["report_id"], "rankings": len(report["rankings"]), "comparisons": len(report["comparisons"]), "geographic_accuracy_available": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
