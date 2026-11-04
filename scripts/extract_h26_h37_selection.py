#!/usr/bin/env python3
"""Extrae H26-H37 y detiene el parser antes del primer registro reservado."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.tfg_phase0.remote_mapillary_campaign import EXPECTED_DEVELOPMENT_IDS, canonical_bytes


def prefix_metadata(path: Path) -> tuple[dict, list[dict]]:
    decoder = json.JSONDecoder()
    marker = '"references"'
    buffer = ""
    with path.open("r", encoding="utf-8") as stream:
        while marker not in buffer:
            chunk = stream.read(4096)
            if not chunk:
                raise ValueError("selection sin references")
            buffer += chunk
        marker_index = buffer.index(marker)
        metadata = json.loads(buffer[:marker_index] + '"references":[]}')
        array_index = buffer.index("[", marker_index + len(marker)) + 1
        position = array_index
        references = []
        while len(references) < len(EXPECTED_DEVELOPMENT_IDS):
            while True:
                while position < len(buffer) and buffer[position] in " \r\n\t,": position += 1
                try:
                    row, position = decoder.raw_decode(buffer, position)
                    break
                except json.JSONDecodeError:
                    chunk = stream.read(4096)
                    if not chunk:
                        raise ValueError("selection truncada antes de H37")
                    buffer += chunk
            references.append(row)
    return metadata, references


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata, references = prefix_metadata(args.selection)
    if tuple(row.get("query_id") for row in references) != EXPECTED_DEVELOPMENT_IDS or any(row.get("partition") != "development" for row in references):
        raise ValueError("los doce primeros registros no son H26-H37 development")
    # Los metadatos no sensibles se fijan explícitamente; no se deserializa el resto del contenedor.
    source_sha = hashlib.sha256(args.selection.read_bytes()).hexdigest()
    assets = sorted({row["reference"]["image_id"] for row in references} | {asset["image_id"] for row in references for asset in row["verification_plan"]})
    document = {"schema_version": "1.0", "contract_version": "h26-h37-isolated-selection-v1", "selection_id": "", "source_container": {"sha256": source_sha, "logical_path": str(args.selection)}, "inputs": metadata["inputs"], "partition": "development", "query_ids": list(EXPECTED_DEVELOPMENT_IDS), "references": references, "asset_ids": assets, "summary": {"queries": 12, "reference_assets": 12, "verification_assets": len(assets) - 12, "unique_assets": len(assets)}, "protocol": {"reserved_records_parsed": False, "stopped_after_query_id": "H37", "ground_truth_used": False, "rankings_used": False, "vlm_outputs_used": False}}
    document["selection_id"] = "h26-h37-isolated-selection-sha256-" + hashlib.sha256(canonical_bytes({key:value for key,value in document.items() if key != "selection_id"})).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"selection_id":document["selection_id"],"summary":document["summary"]},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
