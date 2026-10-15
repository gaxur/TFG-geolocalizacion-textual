#!/usr/bin/env python3
"""Evalúa en solo lectura la cobertura F2 de la selección visual F4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_preflight import load_verified_selection, preflight_local_snapshot
from src.tfg_phase0.f4_validation import load_verified_f1_50m


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--selection", type=Path, default=ROOT / "config/madrid_f4_visual_fixture.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    args = parser.parse_args()
    config = load_region_config(args.config)
    catalog = load_verified_f1_50m(args.manifest, config)
    selection, _ = load_verified_selection(args.selection, catalog)
    result = preflight_local_snapshot(catalog, selection, args.snapshot_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
