#!/usr/bin/env python3
"""Adquiere el snapshot OSM D004 conforme a D043-D048."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.osm_snapshot import acquire_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--snapshots-root", type=Path)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Autoriza explícitamente una llamada real a Overpass.",
    )
    parser.add_argument(
        "--snapshot-id",
        help="Valida y reutiliza un snapshot local sin usar red.",
    )
    args = parser.parse_args()
    config = load_region_config(args.config)
    root = args.snapshots_root or ROOT / config["artifacts"]["raw_osm"] / "snapshots"
    if not args.allow_network and args.snapshot_id is None:
        parser.error("usar --allow-network para adquirir o --snapshot-id para cache local")
    if args.allow_network and args.snapshot_id is not None:
        parser.error("--allow-network y --snapshot-id son excluyentes")
    snapshot_path, cache_hit = acquire_snapshot(
        config, root, expected_snapshot_id=args.snapshot_id
    )
    print(f"Snapshot: {snapshot_path}")
    print(f"Cache hit: {str(cache_hit).lower()}")


if __name__ == "__main__":
    main()
