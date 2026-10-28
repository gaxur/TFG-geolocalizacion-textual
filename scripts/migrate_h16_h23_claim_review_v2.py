#!/usr/bin/env python3
"""Crea revisión v2 pendiente y manifiesto de correspondencias; no autoaprueba."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.h16_h23_claim_review import canonical_bytes, pending_review, sha256_file


def semantic_key(row):
    value = {key: value for key, value in row["claim"]["value"].items() if key not in {"entity_id", "subject_entity_id"}}
    return (row["query_id"], row["claim"]["kind"], row["claim"]["evidence"]["text"].casefold(), json.dumps(value, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-review", type=Path, required=True)
    parser.add_argument("--new-fixture", type=Path, required=True)
    parser.add_argument("--new-protocol", type=Path, required=True)
    parser.add_argument("--output-review", type=Path, required=True)
    parser.add_argument("--output-migration", type=Path, required=True)
    args = parser.parse_args()
    old = json.loads(args.old_review.read_text(encoding="utf-8"))
    fixture = json.loads(args.new_fixture.read_text(encoding="utf-8"))
    protocol = json.loads(args.new_protocol.read_text(encoding="utf-8"))
    review = pending_review(fixture, protocol, fixture_sha256=sha256_file(args.new_fixture), protocol_sha256=sha256_file(args.new_protocol))
    old_index = {semantic_key(row): row for row in old["records"]}
    records = []
    transferred = 0
    for row in review["records"]:
        old_row = old_index.get(semantic_key(row))
        status = "new_or_semantically_changed"
        if old_row:
            status = "semantically_equivalent_pending" if old_row["decision"] == "pending" else "eligible_for_manual_confirmation"
            if old_row["decision"] != "pending":
                status = "not_transferred_requires_human_confirmation"
        records.append({"old_claim_id": old_row["claim"]["claim_id"] if old_row else None, "new_claim_id": row["claim"]["claim_id"], "query_id": row["query_id"], "status": status, "decision_transferred": False})
    migration = {"schema_version": "1.0", "contract_version": "h16-h23-claim-migration-v1-to-v2", "old_review_sha256": sha256_file(args.old_review), "new_fixture_sha256": sha256_file(args.new_fixture), "records": records, "summary": {"old_decided": sum(row["decision"] != "pending" for row in old["records"]), "new_claims": len(review["records"]), "decisions_transferred": transferred}}
    args.output_review.parent.mkdir(parents=True, exist_ok=True)
    args.output_review.write_bytes(canonical_bytes(review) + b"\n")
    args.output_migration.write_bytes(canonical_bytes(migration) + b"\n")
    print(json.dumps(migration["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
