#!/usr/bin/env python3
"""Valida que un paquete aislado contenga solo H26-H37 development."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.tfg_phase0.remote_mapillary_campaign import EXPECTED_DEVELOPMENT_IDS


FORBIDDEN_KEYS = {"ct2l_rankings", "cosine_similarity", "candidate_distances", "evaluation_metrics", "vlm_outputs", "final_top10_candidate_ids"}


def reject_system_outputs(value, path="fixture"):
    if isinstance(value, dict):
        forbidden = FORBIDDEN_KEYS.intersection(value)
        if forbidden:
            raise ValueError(f"contenido de sistema prohibido en {path}: {sorted(forbidden)}")
        for key, item in value.items():
            reject_system_outputs(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_system_outputs(item, f"{path}[{index}]")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.fixture.read_text(encoding="utf-8"))
    reject_system_outputs(document)
    ids = tuple(row.get("query_id") for row in document.get("observations", []))
    if document.get("partition") != "development" or tuple(document.get("query_ids", [])) != EXPECTED_DEVELOPMENT_IDS or ids != EXPECTED_DEVELOPMENT_IDS:
        raise ValueError("paquete no está aislado exactamente a H26-H37")
    if "other_partition_records" not in document.get("forbidden_content", []):
        raise ValueError("paquete no declara exclusión de otras particiones")
    print(json.dumps({"status": "valid", "queries": len(ids), "sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
