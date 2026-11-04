#!/usr/bin/env python3
"""Sella bytes compartidos sin interpretar ni exportar registros H38-H61."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared-selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = {"schema_version": "1.0", "contract_version": "h38-h61-unopened-container-seal-v1", "status": "sealed_unopened", "shared_container": {"logical_path": str(args.shared_selection), "sha256": digest(args.shared_selection), "size_bytes": args.shared_selection.stat().st_size}, "sealed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "content_inspected": False, "permitted_operations_before_policy_freeze": ["byte_hash_verification"], "forbidden_operations": ["parse_test_records", "read_test_descriptions", "read_test_coordinates", "read_test_images", "run_test_retrieval", "run_test_vlm", "evaluate_test"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": document["status"], "container_sha256": document["shared_container"]["sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
