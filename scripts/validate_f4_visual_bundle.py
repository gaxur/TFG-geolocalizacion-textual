#!/usr/bin/env python3
"""Valida un bundle visual F4 local contra F1 y todos sus inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_preflight import load_verified_selection
from src.tfg_phase0.f4_validation import load_verified_f1_50m, validate_visual_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--selection", type=Path, default=ROOT / "config/madrid_f4_visual_fixture.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    args = parser.parse_args()

    bundle = args.bundle.resolve()
    catalog = load_verified_f1_50m(args.manifest, load_region_config(args.config))
    selection, selection_hash = load_verified_selection(args.selection, catalog)
    document = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    validate_visual_bundle(
        document,
        catalog,
        selection=selection,
        selection_sha256=selection_hash,
        dataset_root=bundle,
        project_root=ROOT,
    )
    print(json.dumps({
        "visual_dataset_id": document["visual_dataset_id"],
        "generated": sum(row["generation_status"] == "generated" for row in document["images"]),
        "status": "valid",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
