#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path("schemas/remote_mapillary_observation.schema.json"))
    args = parser.parse_args()
    campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    observations = campaign.get("observations", [])
    for row in observations:
        validator.validate(row)
        expected_partition = "development" if 26 <= int(row["query_id"][1:]) <= 37 else "test_sealed"
        if row["partition"] != expected_partition:
            raise ValueError(f"split inválido para {row['query_id']}")
        reference_id = row["reference_asset"]["image_id"]
        if reference_id in {asset["image_id"] for asset in row["verification_assets"]}:
            raise ValueError(f"referencia reutilizada como verificación en {row['query_id']}")
        if row["reference_asset"]["sequence_id"] in {asset["sequence_id"] for asset in row["verification_assets"]}:
            raise ValueError(f"secuencia de referencia reutilizada en {row['query_id']}")
        if row["lifecycle_status"] == "frozen":
            if row["human_review"]["status"] != "approved" or not row["freeze"]["frozen_at_utc"] or not row["freeze"]["canonical_sha256"]:
                raise ValueError(f"freeze incompleto en {row['query_id']}")
            if row["partition"] == "test_sealed" and not row["human_review"]["secondary_reviewer"]:
                raise ValueError(f"test sin segundo revisor en {row['query_id']}")
            payload=json.loads(json.dumps(row));payload["freeze"]["canonical_sha256"]=None;payload["freeze"]["frozen_at_utc"]=None;payload["lifecycle_status"]="approved"
            expected=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
            if row["freeze"]["canonical_sha256"]!=expected:
                raise ValueError(f"hash canónico inválido en {row['query_id']}")
    ids = [row["query_id"] for row in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("query_id duplicado")
    if ids and all(26 <= int(value[1:]) <= 37 for value in ids) and ids != [f"H{index:02d}" for index in range(26,38)]:
        raise ValueError("campaña development debe contener exactamente H26-H37 ordenados")
    print(json.dumps({"valid": True, "observations": len(observations), "campaign_sha256": hashlib.sha256(args.campaign.read_bytes()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
