#!/usr/bin/env python3
"""Adquiere el lote H11 planificado tras una autorización explícita."""

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
from src.tfg_phase0.mapillary_visual_pilot import image_dimensions, reject_ground_truth


FIELDS = ("id", "creator", "computed_geometry", "captured_at", "computed_compass_angle", "sequence", "camera_type", "width", "height", "quality_score", "thumb_1024_url")


def main() -> int:
    parser = argparse.ArgumentParser(description="Adquiere assets únicos H11 ya planificados.")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--existing-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-new-downloads", type=int, default=23)
    parser.add_argument("--max-total-bytes", type=int, default=184_000_000)
    parser.add_argument("--confirm-terms-reviewed", action="store_true")
    args = parser.parse_args()
    if not args.confirm_terms_reviewed:
        print("ERROR: confirme términos para este lote H11", file=sys.stderr)
        return 2
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    existing = json.loads(args.existing_manifest.read_text(encoding="utf-8"))
    reject_ground_truth(fixture, path="fixture")
    assets = fixture["assets"]
    existing_records = existing.get("assets") or existing.get("photos") or []
    old = {row["image_id"]: row for row in existing_records if row["status"] in {"downloaded", "reused"}}
    new = [image_id for image_id in assets if image_id not in old]
    if len(new) > args.max_new_downloads or not 1 <= args.max_new_downloads <= 80 or args.max_total_bytes > 640_000_000:
        raise ValueError("presupuesto H11 excedido")
    args.output_root.mkdir(parents=True, exist_ok=True)
    records = []
    total = 0
    client = MapillaryClient()
    cache = cache_from_env(ROOT)
    cache.prepare()
    for image_id in assets:
        if image_id in old:
            source = old[image_id]
            path = (args.existing_manifest.parent / source["logical_path"]).resolve()
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError("asset reutilizado con hash inválido")
            records.append({"image_id": image_id, "status": "reused", "source_manifest_sha256": hashlib.sha256(args.existing_manifest.read_bytes()).hexdigest(), "logical_path": os.path.relpath(path, args.output_root.resolve()), "sha256": source["sha256"], "size_bytes": source["size_bytes"], "media_type": source["media_type"], "downloaded_resolution": source["downloaded_resolution"], "creator": source["creator"], "creator_profile_url": source["creator_profile_url"], "attribution": source["attribution"], "license": "CC-BY-SA-4.0", "license_url": source["license_url"], "source_page_url": source["source_page_url"], "modifications": source["modifications"]})
            continue
        try:
            metadata = client.image_metadata(image_id, FIELDS)
            creator = metadata.get("creator") or {}
            username = creator.get("username") or creator.get("name")
            if not username:
                raise MapillaryCoverageError("autor ausente")
            raw, _ = client.download_bytes(metadata["thumb_1024_url"], max_bytes=8_000_000)
            media_type, width, height = image_dimensions(raw)
            total += len(raw)
            if total > args.max_total_bytes:
                raise ValueError("presupuesto total excedido")
            suffix = ".jpg" if media_type == "image/jpeg" else ".png"
            record = {"status": "downloaded", "media_type": media_type, "downloaded_resolution": [width, height], "source_resolution": [metadata.get("width"), metadata.get("height")], "captured_at": metadata.get("captured_at"), "camera_type": metadata.get("camera_type"), "creator": creator, "creator_profile_url": f"https://www.mapillary.com/app/user/{username}", "attribution": f"Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0", "license": "CC-BY-SA-4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "source_page_url": f"https://www.mapillary.com/app/?pKey={image_id}", "modifications": "Downloaded as a 1024 px thumbnail; no content edits by the TFG", "acquired_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
            records.append(cache.store(image_id, raw, record, suffix=suffix))
        except MapillaryCoverageError as error:
            records.append({"image_id": image_id, "status": "failed", "error": str(error)})
    manifest = {"schema_version": "1.1", "contract_version": "h11-visual-asset-manifest-v1", "fixture_id": fixture["fixture_id"], "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(), "terms_review_confirmed_by_operator": True, "requested_unique_assets": len(assets), "new_download_budget": args.max_new_downloads, "downloaded_new": sum(row["status"] == "downloaded" for row in records), "reused": sum(row["status"] == "reused" for row in records), "failed": sum(row["status"] == "failed" for row in records), "assets": records, "associations": fixture["associations"], "limitations": ["proximity_does_not_prove_visibility", "orientation_not_observer_orientation"]}
    (args.output_root / "asset-manifest.json").write_bytes(canonical_bytes(manifest) + b"\n")
    print(json.dumps({key: manifest[key] for key in ("requested_unique_assets", "downloaded_new", "reused", "failed")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
