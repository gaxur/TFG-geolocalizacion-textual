#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import MapillaryClient, MapillaryCoverageError, canonical_bytes, sha256_bytes  # noqa: E402
from src.tfg_phase0.mapillary_visual_pilot import MapillaryPilotError, image_dimensions, reject_ground_truth, validate_image_plan  # noqa: E402


FIELDS = ("id", "creator", "computed_geometry", "captured_at", "computed_compass_angle", "sequence", "camera_type", "width", "height", "quality_score", "thumb_1024_url")


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga solo las fotografías planificadas del piloto")
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--image-plan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-downloads", type=int, default=30)
    parser.add_argument("--max-bytes-per-image", type=int, default=8_000_000)
    parser.add_argument("--confirm-terms-reviewed", action="store_true")
    args = parser.parse_args()
    if not args.confirm_terms_reviewed:
        print("ERROR: revise los términos aplicables y use --confirm-terms-reviewed", file=sys.stderr)
        return 2
    if not 1 <= args.max_downloads <= 30:
        print("ERROR: --max-downloads debe estar entre 1 y 30", file=sys.stderr)
        return 2
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    plan = json.loads(args.image_plan.read_text(encoding="utf-8"))
    reject_ground_truth(selection, path="selection")
    reject_ground_truth(plan, path="image_plan")
    validate_image_plan(plan)
    candidate_info = {row["candidate_id"]: row for row in selection["candidates"]}
    planned = [(row["candidate_id"], image) for row in plan["candidates"] for image in row["images"]]
    if len(planned) > args.max_downloads:
        print("ERROR: el plan supera --max-downloads", file=sys.stderr)
        return 2
    client = MapillaryClient()
    image_root = args.output_root / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    photos = []
    for candidate_id, planned_image in planned:
        base = {"candidate_id": candidate_id, "query_id": candidate_info[candidate_id]["query_id"], "baseline_rank": candidate_info[candidate_id]["baseline_rank"], "image_id": planned_image["image_id"], "distance_to_candidate_m": planned_image["distance_to_candidate_m"], "orientation_degrees": planned_image.get("orientation_degrees"), "bearing_to_candidate_degrees": planned_image.get("bearing_to_candidate_degrees"), "angular_difference_degrees": planned_image.get("angular_difference_degrees"), "quality_score": planned_image.get("quality_score"), "license": "CC-BY-SA-4.0", "source_page_url": f"https://www.mapillary.com/app/?pKey={planned_image['image_id']}"}
        try:
            metadata = client.image_metadata(planned_image["image_id"], FIELDS)
            creator = metadata.get("creator") or {}
            username = creator.get("username") or creator.get("name")
            if not username:
                raise MapillaryCoverageError("autor Mapillary ausente; no puede construirse atribución")
            creator_profile_url = f"https://www.mapillary.com/app/user/{username}"
            license_url = "https://creativecommons.org/licenses/by-sa/4.0/"
            attribution = f"Mapillary image {planned_image['image_id']} by {username}, licensed under CC BY-SA 4.0"
            url = metadata.get("thumb_1024_url")
            if not isinstance(url, str) or not url:
                raise MapillaryCoverageError("thumbnail 1024 no disponible")
            raw, response_type = client.download_bytes(url, max_bytes=args.max_bytes_per_image)
            detected_type, width, height = image_dimensions(raw)
            if response_type not in {None, "application/octet-stream", detected_type}:
                raise MapillaryCoverageError("tipo MIME de fotografía inesperado")
            extension = ".jpg" if detected_type == "image/jpeg" else ".png"
            path = image_root / f"{planned_image['image_id']}{extension}"
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(raw)
            temporary.replace(path)
            photos.append({**base, "status": "downloaded", "creator": creator, "creator_profile_url": creator_profile_url, "attribution": attribution, "license_url": license_url, "provider_attribution": "Mapillary", "modifications": "Downloaded as a 1024 px thumbnail; no content edits by the TFG", "captured_at": metadata.get("captured_at"), "camera_type": metadata.get("camera_type"), "source_resolution": [metadata.get("width"), metadata.get("height")], "downloaded_resolution": [width, height], "logical_path": f"images/{path.name}", "sha256": sha256_bytes(raw), "size_bytes": len(raw), "media_type": detected_type, "acquired_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "limitations": ["proximity_does_not_prove_visibility", "candidate_center_is_not_observer_position"]})
        except (MapillaryCoverageError, MapillaryPilotError) as error:
            photos.append({**base, "status": "failed", "creator": None, "creator_profile_url": None, "attribution": None, "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "provider_attribution": "Mapillary", "modifications": None, "captured_at": None, "camera_type": planned_image.get("camera_type"), "source_resolution": [planned_image.get("width_px"), planned_image.get("height_px")], "downloaded_resolution": None, "logical_path": None, "sha256": None, "size_bytes": None, "media_type": None, "acquired_at_utc": None, "error": str(error), "limitations": ["no_visual_evidence_acquired"]})
    manifest = {"schema_version": "1.0", "contract_version": "mapillary-photo-manifest-v1", "selection_id": selection["selection_id"], "image_plan_id": plan["image_plan_id"], "terms_review_confirmed_by_operator": True, "requested_count": len(planned), "downloaded_count": sum(row["status"] == "downloaded" for row in photos), "photos": photos}
    (args.output_root / "photo-manifest.json").write_bytes(canonical_bytes(manifest) + b"\n")
    print(json.dumps({"requested": len(planned), "downloaded": manifest["downloaded_count"], "failed": len(planned) - manifest["downloaded_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
