#!/usr/bin/env python3
"""Congela el subconjunto de assets históricos disponibles para análisis parcial."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    assets = []
    for row in plan["assets"]:
        path_value, expected = row.get("existing_logical_path"), row.get("existing_sha256")
        if not path_value or not expected:
            continue
        path = Path(path_value).resolve()
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"asset histórico inválido: {row['image_id']}")
        assets.append({"image_id": row["image_id"], "status": "reused", "logical_path": os.path.relpath(path, args.output.parent.resolve()), "sha256": expected, "size_bytes": path.stat().st_size, "associations": row["associations"], "source": "historical_authorized_asset"})
    available = {row["image_id"] for row in assets}
    associations = [row for row in fixture["associations"] if row["image_id"] in available]
    by_query = {query_id: sum(row["query_id"] == query_id for row in associations) for query_id in ("H16", "H23")}
    document = {"schema_version": "1.0", "contract_version": "h16-h23-v2-partial-asset-manifest-v1", "fixture_id": fixture["fixture_id"], "fixture_sha256": digest(args.fixture), "plan_id": plan["plan_id"], "plan_sha256": digest(args.plan), "analysis_scope": "partial_historical_availability_not_complete_top50", "assets": assets, "associations": associations, "summary": {"unique_assets": len(assets), "associations": len(associations), "associations_by_query": by_query, "pending_unique_assets": len(fixture["assets"]) - len(assets)}, "protocol": {"no_new_downloads": True, "availability_not_used_to_claim_complete_evaluation": True, "same_manifest_required_for_2b_8b": True}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
