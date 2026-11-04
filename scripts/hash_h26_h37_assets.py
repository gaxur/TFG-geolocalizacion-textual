#!/usr/bin/env python3
"""Añade dHash reproducible y ejecuta el gate automático de independencia."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import canonical_bytes


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dhash(path: Path) -> str:
    with Image.open(path) as image:
        pixels = list(image.convert("L").resize((9, 8)).getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | (pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return f"{value:016x}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output-assets", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text())
    assets = json.loads(args.assets.read_text())
    rows = []
    for row in assets["assets"]:
        path = (args.assets.parent / row["logical_path"]).resolve()
        if digest(path) != row["sha256"] or path.stat().st_size != row["size_bytes"]:
            raise ValueError(f"asset sin integridad: {row['image_id']}")
        rows.append({**row, "perceptual_hash": dhash(path)})
    by_id = {row["image_id"]: row for row in rows}
    exact_duplicates = []
    near_duplicates = []
    for item in selection["references"]:
        reference = by_id[item["reference"]["image_id"]]
        for planned in item["verification_plan"]:
            verification = by_id[planned["image_id"]]
            if reference["sha256"] == verification["sha256"]:
                exact_duplicates.append([reference["image_id"], verification["image_id"]])
            distance = (int(reference["perceptual_hash"], 16) ^ int(verification["perceptual_hash"], 16)).bit_count()
            if distance <= 6:
                near_duplicates.append({"query_id": item["query_id"], "reference_image_id": reference["image_id"], "verification_image_id": verification["image_id"], "hamming_distance": distance})
    report = {"schema_version": "1.0", "contract_version": "h26-h37-pixel-independence-v1", "selection_id": selection["selection_id"], "algorithm": "dhash-9x8-grayscale-v1", "maximum_perceptual_distance": 6, "exact_duplicates": exact_duplicates, "near_duplicate_review_queue": near_duplicates, "automatic_gate_passed": not exact_duplicates and not near_duplicates, "human_overlap_review_required": True, "independence_claim": "pending_human_overlap_review" if not exact_duplicates and not near_duplicates else "failed_or_pending_resolution"}
    document = {**assets, "contract_version": "h26-h37-mapillary-assets-hashed-v1", "inputs": {"asset_manifest_sha256": digest(args.assets), "selection_sha256": digest(args.selection)}, "assets": rows, "perceptual_hash": {"algorithm": "dhash-9x8-grayscale-v1", "bits": 64}}
    args.output_assets.parent.mkdir(parents=True, exist_ok=True)
    args.output_assets.write_bytes(canonical_bytes(document) + b"\n")
    args.output_report.write_bytes(canonical_bytes(report) + b"\n")
    print(json.dumps({"assets": len(rows), "exact_duplicates": len(report["exact_duplicates"]), "near_duplicate_review_queue": len(report["near_duplicate_review_queue"]), "automatic_gate_passed": report["automatic_gate_passed"], "human_overlap_review_required": report["human_overlap_review_required"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
