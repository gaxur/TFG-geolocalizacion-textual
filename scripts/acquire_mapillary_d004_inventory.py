#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import (  # noqa: E402
    MapillaryClient,
    MapillaryClientConfig,
    MapillaryCoverageError,
    canonical_bytes,
    expand_bbox_projected,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Adquiere solo metadatos Mapillary de D004")
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page-limit", type=int, default=2000)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--request-interval-seconds", type=float, default=0.25)
    parser.add_argument("--buffer-m", type=float, default=0.0)
    parser.add_argument("--grid-size", type=int, default=1)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    client = MapillaryClient(config=MapillaryClientConfig(
        page_limit=args.page_limit,
        max_pages=args.max_pages,
        request_interval_seconds=args.request_interval_seconds,
    ))
    try:
        original_bbox = config["region"]["bbox"]
        expansion = expand_bbox_projected(original_bbox, args.buffer_m) if args.buffer_m else None
        query_bbox = expansion["query_bbox_wgs84"] if expansion else original_bbox
        if args.grid_size > 1:
            inventory = client.partitioned_inventory(query_bbox, original_bbox=original_bbox, margin_m=args.buffer_m, expansion=expansion, grid_size=args.grid_size)
        else:
            inventory = client.inventory(query_bbox, original_bbox=original_bbox, margin_m=args.buffer_m, expansion=expansion)
    except MapillaryCoverageError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(inventory) + b"\n")
    print(json.dumps({"inventory_id": inventory["inventory_id"], "image_count": inventory["image_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
