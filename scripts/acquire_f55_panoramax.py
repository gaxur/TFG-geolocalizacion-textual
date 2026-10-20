#!/usr/bin/env python3
"""Congela inventario Panoramax D004, selecciona hasta cinco items y descarga thumbnails."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_evidence_acquisition import DEFAULT_BBOX, DEFAULT_ENDPOINT, F55EvidenceError, attach_download, build_review_queue, download_review_asset, fetch_url, parse_panoramax_response, render_review_html, select_review_items, utc_now, validate_inventory, validate_review_queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--raw-response", type=Path, help="Reanuda desde una respuesta GeoJSON ya congelada.")
    parser.add_argument("--retrieved-at-utc", help="Timestamp original de adquisición al reanudar desde --raw-response.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--review-limit", type=int, default=5)
    parser.add_argument("--asset-role", choices=("thumb", "sd", "none"), default="thumb")
    parser.add_argument("--user-agent", default="TFG-Geolocalizacion-Textual-F5.5/1.0 (academic research; contact repository owner)")
    parser.add_argument("--catalog-25m", type=Path, default=ROOT / "data/processed/catalog/manifest-25m.json")
    parser.add_argument("--catalog-50m", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    args = parser.parse_args()
    if args.limit < 1 or args.review_limit < 1 or args.review_limit > 5:
        parser.error("limit debe ser positivo y review-limit estar entre 1 y 5")
    config = load_region_config(ROOT / "config/madrid.yaml")
    catalogs = {"madrid-25m": load_verified_f1_catalog(args.catalog_25m, config), "madrid-50m": load_verified_f1_catalog(args.catalog_50m, config)}
    params = {"bbox": f"{DEFAULT_BBOX['west']},{DEFAULT_BBOX['south']},{DEFAULT_BBOX['east']},{DEFAULT_BBOX['north']}", "limit": args.limit}
    endpoint_url = args.endpoint + ("&" if "?" in args.endpoint else "?") + urlencode(params)
    if args.raw_response and not args.retrieved_at_utc:
        parser.error("--raw-response requiere --retrieved-at-utc para preservar provenance")
    retrieved = args.retrieved_at_utc or utc_now()
    try:
        if args.raw_response:
            raw, response_media_type = args.raw_response.read_bytes(), "application/json"
        else:
            raw, headers, _ = fetch_url(endpoint_url, user_agent=args.user_agent)
            response_media_type = headers.get("Content-Type", "application/json").split(";", 1)[0]
        inventory = parse_panoramax_response(raw, endpoint_url=endpoint_url, retrieved_at_utc=retrieved, catalogs=catalogs, response_media_type=response_media_type)
        validate_inventory(inventory, catalogs)
        selected = select_review_items(inventory["items"], limit=min(args.review_limit, len(inventory["items"])))
        queue = build_review_queue(inventory, selected)
        final = args.output_root / inventory["inventory_id"]
        if final.exists():
            existing = json.loads((final / "inventory.json").read_text(encoding="utf-8"))
            if existing["source"]["response_sha256"] != inventory["source"]["response_sha256"]:
                raise F55EvidenceError("snapshot existente incompatible")
            validate_inventory(existing, catalogs)
            existing_queue = json.loads((final / "review-queue.json").read_text(encoding="utf-8"))
            validate_review_queue(existing_queue)
            print_summary(final, existing, existing_queue)
            return 0
        args.output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".f55-panoramax-", dir=args.output_root) as temporary:
            path = Path(temporary); (path / "raw-response.geojson").write_bytes(raw)
            if args.asset_role != "none":
                downloaded_hashes = {}
                for item_id in selected:
                    record = next(row for row in queue["records"] if row["item_id"] == item_id)
                    role = args.asset_role if record["assets"].get(args.asset_role) else "thumb"
                    source_url = record["assets"][role]["url"]
                    relative = f"assets/{item_id}-{role}.jpg"
                    asset = download_review_asset(source_url, path / relative, logical_path=relative, user_agent=args.user_agent)
                    if asset.sha256 in downloaded_hashes:
                        raise F55EvidenceError(f"asset duplicado entre {downloaded_hashes[asset.sha256]} y {item_id}")
                    downloaded_hashes[asset.sha256] = item_id
                    attach_download(queue, item_id, role, asset)
            validate_review_queue(queue)
            (path / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            (path / "review-queue.json").write_text(json.dumps(queue, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            render_review_html(queue, path / "review.html")
            os.replace(path, final)
        print_summary(final, inventory, queue)
        return 0
    except Exception as error:
        args.output_root.mkdir(parents=True, exist_ok=True)
        failure = {"schema_version": "1.0", "stage": "f55_panoramax_acquisition", "endpoint_url": endpoint_url, "failed_at_utc": utc_now(), "error_type": type(error).__name__, "message": str(error), "raw_response_path": str(args.raw_response) if args.raw_response else None}
        name = datetime.now(timezone.utc).strftime("failure-%Y%m%dT%H%M%SZ.json")
        (args.output_root / name).write_text(json.dumps(failure, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        raise


def print_summary(path: Path, inventory: dict, queue: dict) -> None:
    counts = validate_review_queue(queue)
    assignments = {gallery: {} for gallery in ("madrid-25m", "madrid-50m")}
    for item in inventory["items"]:
        for gallery, value in item["catalog_assignments"].items():
            assignments[gallery][value["status"]] = assignments[gallery].get(value["status"], 0) + 1
    downloaded = sum(bool(value and value.get("download")) for row in queue["records"] for role, value in row["assets"].items() if role in {"thumb", "sd"})
    print(json.dumps({"inventory_id": inventory["inventory_id"], "items": len(inventory["items"]), "collections": len({row["collection_id"] for row in inventory["items"]}), "selected": len(queue["records"]), "downloaded_assets": downloaded, "review_counts": counts, "assignment_status_counts": assignments, "output": str(path)}, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
