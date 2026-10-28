#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.remote_mapillary_campaign import canonical_bytes, validate_selection_plan


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara un plan offline; no descarga fotografías.")
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--pilot-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    validate_selection_plan(selection)
    pilot = json.loads(args.pilot_manifest.read_text(encoding="utf-8"))
    sizes = [row["size_bytes"] for row in pilot["photos"] if row["status"] == "downloaded"]
    if not sizes:
        raise ValueError("el piloto no contiene tamaños descargados para estimar almacenamiento")
    reference = [row["reference"]["image_id"] for row in selection["references"]]
    verification = [asset["image_id"] for row in selection["references"] for asset in row["verification_plan"]]
    if set(reference).intersection(verification) or len(verification) != len(set(verification)):
        raise ValueError("los roles de activos no son disjuntos")
    image_ids = sorted(set(reference + verification))
    mean_size = sum(sizes) / len(sizes)
    document = {
        "schema_version": "2.0",
        "contract_version": "remote-mapillary-acquisition-plan-v2",
        "plan_id": "",
        "inputs": {"selection_id": selection["selection_id"], "selection_sha256": sha256_file(args.selection)},
        "authorization": {
            "status": "not_authorized",
            "downloads_permitted": False,
            "required_confirmation": [
                "exact_image_ids_and_roles",
                "reference_and_verification_use",
                "maximum_1024px_thumbnails",
                "local_retention_period",
                "private_annotation_transfer",
                "fixed_model_2b_and_8b_inference_without_training",
                "no_public_image_dataset",
                "attribution_privacy_and_application_limits",
            ],
            "maximum_new_images": len(image_ids),
            "maximum_resolution_px": 1024,
            "maximum_total_bytes": len(image_ids) * 8_000_000,
        },
        "assets": {
            "unique_image_ids": image_ids,
            "reference_image_ids": sorted(reference),
            "verification_image_ids": sorted(verification),
            "reference_count": len(reference),
            "verification_count": len(verification),
            "unique_count": len(image_ids),
            "estimated_bytes_at_pilot_mean": round(len(image_ids) * mean_size),
            "pilot_sample_count": len(sizes),
            "pilot_mean_bytes": mean_size,
            "hard_maximum_bytes": len(image_ids) * 8_000_000,
        },
        "protocol": {
            "same_image_reference_and_verification_forbidden": True,
            "same_sequence_per_query_forbidden": True,
            "exact_hash_check_required_after_download": True,
            "perceptual_similarity_check_required_after_download": True,
            "human_overlap_review_required": True,
            "failed_downloads_not_replaced_after_pixel_inspection": True,
        },
        "limitations": [
            "estimate_from_24_thumbnail_pilot",
            "creator_attribution_pending_per_image_metadata",
            "privacy_review_pending",
            "retention_deadline_pending",
            "no_download_performed_by_this_plan",
        ],
    }
    content = {key: value for key, value in document.items() if key != "plan_id"}
    document["plan_id"] = "remote-mapillary-acquisition-sha256-" + hashlib.sha256(canonical_bytes(content)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"plan_id": document["plan_id"], **document["assets"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
