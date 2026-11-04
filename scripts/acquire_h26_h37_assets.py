#!/usr/bin/env python3
"""Adquisición fail-closed de los 24 activos development H26-H37."""

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
from src.tfg_phase0.mapillary_coverage import MapillaryClient, canonical_bytes
from src.tfg_phase0.mapillary_visual_pilot import image_dimensions

EXPECTED_SELECTION_SHA256 = "6118ce8b014657eb50c14f631ac34d8df25927e33589ea3a938749707b004f2e"
EXPECTED_SELECTION_ID = "h26-h37-isolated-selection-sha256-d0b310816bece295eff96605503f23a10a94849dd590ab260265155c6dbdc0fa"
FIELDS = ("id", "creator", "computed_geometry", "captured_at", "computed_compass_angle", "sequence", "camera_type", "width", "height", "quality_score", "thumb_1024_url")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if digest(args.selection) != EXPECTED_SELECTION_SHA256:
        raise ValueError("selección H26-H37 no coincide con el freeze")
    selection = json.loads(args.selection.read_text())
    authorization = json.loads(args.authorization.read_text())
    if selection.get("selection_id") != EXPECTED_SELECTION_ID or selection.get("partition") != "development" or selection.get("summary") != {"queries": 12, "reference_assets": 12, "verification_assets": 12, "unique_assets": 24}:
        raise ValueError("selección development incompatible")
    if authorization.get("selection", {}).get("selection_sha256") != EXPECTED_SELECTION_SHA256 or authorization.get("scope", {}).get("planned_unique_assets") != 24:
        raise ValueError("autorización ligada a otro lote")
    confirmations = authorization.get("operator_confirmations", {})
    approved = bool(authorization.get("approved") and authorization.get("terms_reviewed") and confirmations and all(confirmations.values()) and authorization.get("approved_by") and authorization.get("approved_at_utc") and authorization.get("retention_deadline_utc"))
    if args.dry_run:
        print(json.dumps({"network_opened": False, "approved": approved, "assets": 24, "hard_maximum_bytes": 192000000}, sort_keys=True));return 0
    if not approved:
        raise PermissionError("autorización H26-H37 incompleta")
    roles = {}
    for row in selection["references"]:
        roles[row["reference"]["image_id"]] = {"role": "reference_annotation_only", "query_id": row["query_id"]}
        for asset in row["verification_plan"]:
            roles[asset["image_id"]] = {"role": "vlm_verification_only", "query_id": row["query_id"]}
    if set(roles) != set(selection["asset_ids"]) or len(roles) != 24:
        raise ValueError("roles development incompletos")
    cache = cache_from_env(ROOT);cache.prepare();client = MapillaryClient();client._require_token()
    records=[];total=0
    for image_id in sorted(roles):
        metadata_path=cache.metadata/f"{image_id}.json"
        if metadata_path.is_file():
            record=json.loads(metadata_path.read_text());cached=cache.root/record["logical_path"]
            if not cached.is_file() or digest(cached)!=record["sha256"]:raise ValueError("caché sin integridad")
            acquisition="reused_verified_cache"
        else:
            metadata=client.image_metadata(image_id,FIELDS);creator=metadata.get("creator") or {};username=creator.get("username") or creator.get("name")
            if not username:raise ValueError("autor Mapillary ausente")
            raw,_=client.download_bytes(metadata["thumb_1024_url"],max_bytes=8_000_000);media_type,width,height=image_dimensions(raw);suffix=".jpg" if media_type=="image/jpeg" else ".png"
            record=cache.store(image_id,raw,{"status":"downloaded","media_type":media_type,"downloaded_resolution":[width,height],"creator":creator,"creator_profile_url":f"https://www.mapillary.com/app/user/{username}","attribution":f"Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0","license":"CC-BY-SA-4.0","license_url":"https://creativecommons.org/licenses/by-sa/4.0/","source_page_url":f"https://www.mapillary.com/app/?pKey={image_id}","retention_deadline_utc":authorization["retention_deadline_utc"]},suffix=suffix);cached=cache.root/record["logical_path"];acquisition="downloaded"
        total+=record["size_bytes"]
        if total>192_000_000:raise ValueError("presupuesto global excedido")
        cache.pin(image_id,"h26-h37-calibration-v1")
        records.append({**record,**roles[image_id],"acquisition_status":acquisition,"logical_path":os.path.relpath(cached.resolve(),args.output.parent.resolve())})
    document={"schema_version":"1.0","contract_version":"h26-h37-mapillary-assets-v1","selection_id":EXPECTED_SELECTION_ID,"selection_sha256":EXPECTED_SELECTION_SHA256,"authorization_sha256":digest(args.authorization),"assets":records,"summary":{"assets":24,"downloaded":sum(r["acquisition_status"]=="downloaded" for r in records),"reused":sum(r["acquisition_status"]=="reused_verified_cache" for r in records),"reference":12,"verification":12,"total_bytes":total},"protocol":{"test_partition_accessed":False,"sha256_required":True,"atomic_cache":True,"no_replacement_after_pixels":True}}
    args.output.parent.mkdir(parents=True,exist_ok=True);temporary=args.output.with_suffix(".tmp");temporary.write_bytes(canonical_bytes(document)+b"\n");temporary.replace(args.output);print(json.dumps(document["summary"],sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
