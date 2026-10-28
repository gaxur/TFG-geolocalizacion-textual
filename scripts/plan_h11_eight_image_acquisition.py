#!/usr/bin/env python3
"""Genera el lote incremental exacto para pasar H11 de hasta 5 a hasta 8 vistas."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
from src.tfg_phase0.visual_reranking import canonical_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-8", type=Path, required=True)
    parser.add_argument("--existing-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture_8.read_text(encoding="utf-8"))
    existing = json.loads(args.existing_manifest.read_text(encoding="utf-8"))
    reject_ground_truth(fixture, path="fixture")
    existing_rows = {row["image_id"]: row for row in existing["assets"] if row["status"] in {"downloaded", "reused"}}
    requested = set(fixture["assets"])
    reusable = sorted(requested.intersection(existing_rows))
    new = sorted(requested - set(existing_rows))
    sizes = [row["size_bytes"] for row in existing_rows.values()]
    mean_size = sum(sizes) / len(sizes)
    by_image = {row["image_id"]: row for row in fixture["associations"]}
    assets = [{"image_id": image_id, "candidate_id": by_image[image_id]["candidate_id"], "baseline_rank": by_image[image_id]["baseline_rank"], "sequence_id": by_image[image_id].get("sequence_id"), "distance_to_candidate_m": by_image[image_id]["distance_to_candidate_m"], "orientation_band": by_image[image_id]["orientation_band"], "purpose": "H11 development nested eight-image VLM comparison"} for image_id in new]
    document = {"schema_version": "1.0", "contract_version": "h11-eight-image-acquisition-plan-v1", "plan_id": "", "authorization": {"status": "not_authorized", "downloads_permitted": False, "maximum_resolution_px": 1024, "purpose": "Complete the existing H11 development fixture to at most eight images per CT2L Top-10 candidate for paired 2B/8B inference"}, "inputs": {"fixture_id": fixture["fixture_id"], "fixture_sha256": hashlib.sha256(args.fixture_8.read_bytes()).hexdigest(), "existing_manifest_sha256": hashlib.sha256(args.existing_manifest.read_bytes()).hexdigest()}, "counts": {"requested_assets": len(requested), "already_available": len(reusable), "new_images": len(new), "candidate_count": fixture["coverage"]["candidate_count"], "association_count": fixture["coverage"]["association_count"]}, "storage": {"observed_existing_mean_bytes": mean_size, "estimated_new_bytes": round(len(new) * mean_size), "hard_maximum_bytes": len(new) * 8_000_000}, "new_assets": assets, "protocol": {"ground_truth_used": False, "same_ids_for_2b_and_8b": True, "download_once_by_image_id": True, "cache_dir": "data/cache/mapillary", "failed_downloads_not_replaced_after_visual_inspection": True}, "limitations": ["development_query_only", "metadata_selection_does_not_prove_visibility", "new_terms_authorization_required", "no_download_performed"]}
    payload = {key: value for key, value in document.items() if key != "plan_id"}
    document["plan_id"] = "h11-eight-image-acquisition-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"plan_id": document["plan_id"], **document["counts"], **document["storage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
