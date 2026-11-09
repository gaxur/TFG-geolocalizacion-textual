#!/usr/bin/env python3
"""Audita edificios y geometrías de la fuente PBF F4 en D004 más un buffer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.madrid_osm_cartography import audit_local_pbf


def run_audit(source_dir: Path, config_path: Path, margin_m: float) -> dict[str, Any]:
    features, audit = audit_local_pbf(source_dir, config_path, margin_m=margin_m)
    # The report is a summary; do not duplicate OSM geometries into JSON output.
    audit["feature_count_for_map"] = len(features)
    return {
        "schema_version": "1.0",
        "contract_version": "madrid-osm-building-audit-f4-v1",
        "audit_scope": "F4 regional PBF clipped to D004 plus projected buffer",
        "audit": audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path,
        default=ROOT / "data/raw/osm/f4_sources/madrid-geofabrik-20261014",
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--margin-m", type=float, default=250)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_audit(args.source_dir, args.config, args.margin_m)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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
