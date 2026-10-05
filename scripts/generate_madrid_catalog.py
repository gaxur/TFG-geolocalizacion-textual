#!/usr/bin/env python3
"""Genera solo el catálogo geométrico del piloto de Madrid."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--spacing-m", type=int, required=True)
    parser.add_argument("--cell-size-m", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = load_region_config(args.config)
    config_path = args.config.resolve()
    try:
        config_source = config_path.relative_to(ROOT).as_posix()
    except ValueError:
        config_source = config_path.name
    manifest = build_catalog(
        config,
        spacing_m=args.spacing_m,
        cell_size_m=args.cell_size_m,
        config_source=config_source,
    )
    output = args.output or ROOT / config["artifacts"]["manifest"]
    write_manifest(manifest, output)
    print(f"Manifest: {output}")
    print(f"Candidatos: {len(manifest['candidates'])}")
    print(f"Spacing: {manifest['generation']['spacing_m']} m")
    print(f"Cell size: {manifest['generation']['cell_size_m']} m")


if __name__ == "__main__":
    main()
