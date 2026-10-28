#!/usr/bin/env python3
"""Adquiere el plan Top-50 exacto solo con autorización ligada a su plan_id."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_cache import cache_from_env
from src.tfg_phase0.mapillary_coverage import MapillaryClient, MapillaryCoverageError, canonical_bytes
from src.tfg_phase0.mapillary_visual_pilot import image_dimensions


EXPECTED_PLAN_ID = "h16-h23-acquisition-sha256-c5fabcc68d2066024c8058837d01e7401e473c957173caa53c206c713a331a4d"
FIELDS = ("id", "creator", "computed_geometry", "captured_at", "computed_compass_angle", "sequence", "camera_type", "width", "height", "quality_score", "thumb_1024_url")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    authorization = json.loads(args.authorization.read_text(encoding="utf-8"))
    if plan.get("plan_id") != EXPECTED_PLAN_ID:
        raise ValueError("plan_id distinto del Top-50 congelado")
    required = {"plan_id": EXPECTED_PLAN_ID, "approved": True, "terms_reviewed": True, "maximum_resolution_px": 1024, "allow_fixed_2b_8b_inference": True, "allow_training": False, "allow_public_dataset": False}
    if any(authorization.get(key) != value for key, value in required.items()):
        raise ValueError("autorización ausente o incompatible con el plan exacto")
    if not authorization.get("approved_by") or not authorization.get("approved_at_utc") or not authorization.get("retention_deadline_utc"):
        raise ValueError("autorización sin responsable, fecha o retención")
    cache = cache_from_env(ROOT)
    cache.prepare()
    client = MapillaryClient()
    records = []
    selected = {row["image_id"]: row for row in plan["assets"]}
    for image_id, planned in selected.items():
        if planned["status"] == "reusable":
            path = Path(planned["existing_logical_path"])
            if not path.is_file() or digest(path) != planned["existing_sha256"]:
                raise ValueError(f"asset reutilizable inválido: {image_id}")
            source_record = {"image_id": image_id, "status": "reused", "logical_path": str(path), "sha256": planned["existing_sha256"], "size_bytes": path.stat().st_size, "associations": planned["associations"]}
            records.append(source_record)
            continue
        try:
            metadata = client.image_metadata(image_id, FIELDS)
            creator = metadata.get("creator") or {}
            username = creator.get("username") or creator.get("name")
            if not username:
                raise MapillaryCoverageError("autor ausente")
            raw, _ = client.download_bytes(metadata["thumb_1024_url"], max_bytes=8_000_000)
            media_type, width, height = image_dimensions(raw)
            suffix = ".jpg" if media_type == "image/jpeg" else ".png"
            record = cache.store(image_id, raw, {"status": "downloaded", "media_type": media_type, "downloaded_resolution": [width, height], "source_resolution": [metadata.get("width"), metadata.get("height")], "captured_at": metadata.get("captured_at"), "camera_type": metadata.get("camera_type"), "creator": creator, "creator_profile_url": f"https://www.mapillary.com/app/user/{username}", "attribution": f"Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0", "license": "CC-BY-SA-4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "source_page_url": f"https://www.mapillary.com/app/?pKey={image_id}", "modifications": "Downloaded as a 1024 px thumbnail; no content edits by the TFG", "acquired_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}, suffix=suffix)
            cached_path = cache.root / record["logical_path"]
            records.append({**record, "logical_path": os.path.relpath(cached_path.resolve(), args.output.parent.resolve()), "associations": planned["associations"]})
        except MapillaryCoverageError as error:
            records.append({"image_id": image_id, "status": "failed", "error": str(error), "associations": planned["associations"]})
    manifest = {"schema_version": "1.0", "contract_version": "h16-h23-top50-asset-manifest-v1", "plan_id": EXPECTED_PLAN_ID, "plan_sha256": digest(args.plan), "authorization_sha256": digest(args.authorization), "authorization": {key: authorization[key] for key in required}, "assets": records, "summary": {"requested": len(records), "downloaded": sum(row["status"] == "downloaded" for row in records), "reused": sum(row["status"] == "reused" for row in records), "failed": sum(row["status"] == "failed" for row in records)}, "protocol": {"download_once_by_image_id": True, "failed_assets_remain_neutral": True, "no_visual_replacement": True, "cache_dir": str(cache.root)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(manifest) + b"\n")
    print(json.dumps(manifest["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
