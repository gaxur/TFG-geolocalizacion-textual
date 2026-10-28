#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.crs import wgs84_to_epsg25830
from src.tfg_phase0.remote_mapillary_campaign import canonical_bytes, select_remote_campaign


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Selecciona H26-H61 solo con metadatos Mapillary congelados.")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--region-config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--historical", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    region = json.loads(args.region_config.read_text(encoding="utf-8"))
    historical = []
    for path in args.historical:
        document = json.loads(path.read_text(encoding="utf-8"))
        for row in document.get("observations", []):
            coordinate = row.get("panorama_coordinate") or row.get("link_coordinate")
            if coordinate is None and "latitude" in row:
                coordinate = {"latitude": row["latitude"], "longitude": row["longitude"]}
            if coordinate:
                easting, northing = wgs84_to_epsg25830(coordinate["latitude"], coordinate["longitude"])
                historical.append(
                    {
                        "id": row.get("observation_id") or row.get("query_id"),
                        "easting": easting,
                        "northing": northing,
                    }
                )

    plan = select_remote_campaign(
        inventory,
        bbox=region["region"]["bbox"],
        historical=historical,
        inventory_sha256=sha256_file(args.inventory),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(plan) + b"\n")
    print(json.dumps({"selection_id": plan["selection_id"], **plan["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
