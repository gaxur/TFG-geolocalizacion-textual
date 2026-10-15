#!/usr/bin/env python3
"""Comprueba que la metadata Osmium del PBF coincide con su provenance F4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    args = parser.parse_args()
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    completed = subprocess.run(
        ["osmium", "fileinfo", "-e", "-j", str(args.pbf)],
        check=True,
        capture_output=True,
        text=True,
    )
    info = json.loads(completed.stdout)
    header = info["header"]
    bbox = header["boxes"][0]
    expected_bbox = provenance["bbox"]
    if bbox != [expected_bbox["west"], expected_bbox["south"], expected_bbox["east"], expected_bbox["north"]]:
        raise ValueError("bbox de cabecera PBF no coincide con provenance")
    if header["option"].get("timestamp") != provenance["data_timestamp_utc"]:
        raise ValueError("timestamp de cabecera PBF no coincide con provenance")
    if not info["data"].get("objects_ordered"):
        raise ValueError("PBF no está ordenado para osm2pgsql")
    if info["file"]["size"] != provenance["raw_size_bytes"]:
        raise ValueError("tamaño PBF no coincide con provenance")
    print(json.dumps({"bbox": bbox, "objects_ordered": True, "status": "valid", "timestamp": provenance["data_timestamp_utc"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
