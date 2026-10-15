#!/usr/bin/env python3
"""Valida un bundle de embeddings F4 contra la galería visual y F1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_preflight import load_verified_selection
from src.tfg_phase0.f4_validation import (
    load_verified_f1_50m,
    validate_embedding_bundle,
    validate_visual_manifest,
    verify_visual_image_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--visual-bundle", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    args = parser.parse_args()

    catalog = load_verified_f1_50m(args.manifest, load_region_config(args.config))
    selection, selection_hash = load_verified_selection(args.selection, catalog)
    visual_raw = (args.visual_bundle / "manifest.json").read_bytes()
    visual = json.loads(visual_raw.decode("utf-8"))
    validate_visual_manifest(visual, catalog, selection=selection, selection_sha256=selection_hash)
    verify_visual_image_files(visual, args.visual_bundle)
    embedding = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8"))
    matrix, candidate_ids = validate_embedding_bundle(embedding, args.bundle, visual, visual_raw, catalog)
    print(json.dumps({
        "embedding_dataset_id": embedding["embedding_dataset_id"],
        "shape": list(matrix.shape),
        "candidate_count": len(candidate_ids),
        "status": "valid",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
