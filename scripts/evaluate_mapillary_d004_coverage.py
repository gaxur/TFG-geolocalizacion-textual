#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import (  # noqa: E402
    build_coverage,
    canonical_bytes,
    render_coverage_markdown,
    sha256_file,
    validate_run_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Calcula cobertura Mapillary local sin red ni GT")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--catalog-25m", type=Path, default=ROOT / "data/processed/catalog/manifest-25m.json")
    parser.add_argument("--catalog-50m", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--rankings", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/rankings.json")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    inputs = {
        "inventory": args.inventory,
        "catalog_25m": args.catalog_25m,
        "catalog_50m": args.catalog_50m,
        "rankings": args.rankings,
    }
    loaded = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in inputs.items()}
    coverage = build_coverage(
        loaded["inventory"],
        {"madrid-25m": loaded["catalog_25m"], "madrid-50m": loaded["catalog_50m"]},
        loaded["rankings"],
        input_hashes={name: sha256_file(path) for name, path in inputs.items()},
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    coverage_path = args.output_root / "coverage.json"
    report_path = args.output_root / "report.md"
    coverage_path.write_bytes(canonical_bytes(coverage) + b"\n")
    report_path.write_text(render_coverage_markdown(coverage), encoding="utf-8")
    artifacts = {
        "inventory": args.inventory,
        "catalog_25m": args.catalog_25m,
        "catalog_50m": args.catalog_50m,
        "rankings": args.rankings,
        "coverage": coverage_path,
        "report": report_path,
    }
    manifest = {
        "schema_version": "1.0",
        "contract_version": "mapillary-d004-coverage-manifest-v1",
        "coverage_id": coverage["coverage_id"],
        "ground_truth_used": False,
        "images_downloaded": False,
        "artifacts": {
            name: {
                "logical_path": str(path.resolve().relative_to(ROOT)),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for name, path in artifacts.items()
        },
    }
    validate_run_manifest(manifest, ROOT)
    (args.output_root / "manifest.json").write_bytes(canonical_bytes(manifest) + b"\n")
    print(json.dumps({"coverage_id": coverage["coverage_id"], "inventory_images": loaded["inventory"]["image_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
