#!/usr/bin/env python3
"""Descargador A/B fail-closed; no usar sin autorización exacta completada."""

from __future__ import annotations

import argparse
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


EXPECTED = {
    "coverage": "e02ca2f33772f70dee602d8c58628a8712490f7a3aa2056b956e1bda81003f1d",
    "geometric": "831c2bc52df35e4cf0bc6401aeef4e5ac2557b1cee7711b42dd57860269b90af",
    "paired": "036f23821f4333eb62846f6a019bb2e61e79305fa92004d51f7be34138639abb",
}
FIELDS = ("id", "creator", "computed_geometry", "captured_at", "computed_compass_angle", "sequence", "camera_type", "width", "height", "quality_score", "thumb_1024_url")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--geometric-manifest", type=Path, required=True)
    parser.add_argument("--paired-plan", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paths = {"coverage": args.coverage_manifest, "geometric": args.geometric_manifest, "paired": args.paired_plan}
    actual = {key: digest(path) for key, path in paths.items()}
    if actual != EXPECTED:
        raise ValueError("manifests A/B distintos de los congelados")
    coverage = json.loads(args.coverage_manifest.read_text())
    geometric = json.loads(args.geometric_manifest.read_text())
    paired = json.loads(args.paired_plan.read_text())
    authorization = json.loads(args.authorization.read_text())
    pending = paired["download_plan"]["deduplicated_new_downloads"]
    if len(pending) != 474 or paired["download_plan"]["hard_maximum_bytes"] != 3_792_000_000:
        raise ValueError("presupuesto físico inesperado")
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "network_opened": False, "pending_assets": len(pending), "authorization_approved": authorization.get("approved") is True}, sort_keys=True))
        return 0
    confirmations = authorization.get("operator_confirmations", {})
    if not authorization.get("approved") or not authorization.get("terms_reviewed") or not all(confirmations.values()) or not authorization.get("approved_by") or not authorization.get("approved_at_utc") or not authorization.get("retention_deadline_utc"):
        raise PermissionError("autorización A/B incompleta")
    if set(authorization["scope"]["frozen_manifest_ids"]) != {coverage["manifest_id"], geometric["manifest_id"]}:
        raise ValueError("autorización para otros manifests")
    basis = authorization.get("documentary_basis", {})
    if basis.get("basis_type") not in {"public_license_and_platform_terms", "individual_provider_authorization"}:
        raise ValueError("fundamento documental ausente o incompatible")
    if basis["basis_type"] == "individual_provider_authorization" and not basis.get("individual_provider_authorization_reference"):
        raise ValueError("referencia de autorización individual ausente")
    cache = cache_from_env(ROOT)
    cache.prepare()
    client = MapillaryClient()
    client._require_token()
    records = []
    total = 0
    for image_id in sorted(set(pending)):
        try:
            metadata_path = cache.metadata / f"{image_id}.json"
            if metadata_path.is_file():
                record = json.loads(metadata_path.read_text(encoding="utf-8"))
                cached = cache.root / record["logical_path"]
                if not cached.is_file() or hashlib.sha256(cached.read_bytes()).hexdigest() != record.get("sha256"):
                    raise ValueError("asset cacheado sin integridad verificable")
                total += cached.stat().st_size
                if total > authorization["scope"]["hard_maximum_bytes"]:
                    raise ValueError("presupuesto total excedido")
                cache.pin(image_id, "h16-h23-selector-comparison-v1")
                records.append({**record, "acquisition_status": "reused_verified_cache", "logical_path": os.path.relpath(cached.resolve(), args.output.parent.resolve())})
                continue
            metadata = client.image_metadata(image_id, FIELDS)
            creator = metadata.get("creator") or {}
            username = creator.get("username") or creator.get("name")
            if not username:
                raise MapillaryCoverageError("autor ausente")
            raw, _ = client.download_bytes(metadata["thumb_1024_url"], max_bytes=8_000_000)
            total += len(raw)
            if total > authorization["scope"]["hard_maximum_bytes"]:
                raise ValueError("presupuesto total excedido")
            media_type, width, height = image_dimensions(raw)
            suffix = ".jpg" if media_type == "image/jpeg" else ".png"
            record = cache.store(image_id, raw, {"status": "downloaded", "media_type": media_type, "downloaded_resolution": [width, height], "creator": creator, "creator_profile_url": f"https://www.mapillary.com/app/user/{username}", "attribution": f"Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0", "license": "CC-BY-SA-4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "source_page_url": f"https://www.mapillary.com/app/?pKey={image_id}", "retention_deadline_utc": authorization["retention_deadline_utc"]}, suffix=suffix)
            cached = cache.root / record["logical_path"]
            cache.pin(image_id, "h16-h23-selector-comparison-v1")
            records.append({**record, "acquisition_status": "downloaded", "logical_path": os.path.relpath(cached.resolve(), args.output.parent.resolve())})
        except MapillaryCoverageError as error:
            records.append({"image_id": image_id, "status": "failed", "error": str(error)})
    document = {"schema_version": "1.0", "contract_version": "h16-h23-selector-union-asset-manifest-v1", "inputs": {"coverage_manifest_sha256": actual["coverage"], "geometric_manifest_sha256": actual["geometric"], "paired_plan_sha256": actual["paired"], "authorization_sha256": digest(args.authorization)}, "assets": records, "summary": {"requested": len(pending), "downloaded": sum(row.get("acquisition_status") == "downloaded" for row in records), "reused_verified_cache": sum(row.get("acquisition_status") == "reused_verified_cache" for row in records), "complete": sum(row.get("status") == "downloaded" for row in records), "failed": sum(row["status"] == "failed" for row in records), "total_bytes": total}, "protocol": {"global_deduplication_by_image_id": True, "atomic_cache": True, "sha256_required": True, "resume_from_verified_cache": True, "no_replacement_after_pixel_inspection": True}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_bytes(canonical_bytes(document) + b"\n")
    temporary.replace(args.output)
    print(json.dumps(document["summary"], sort_keys=True))
    if document["summary"]["failed"]:
        raise RuntimeError("adquisición incompleta; no se puede congelar el manifest físico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
