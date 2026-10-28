#!/usr/bin/env python3
"""Materializa una atestación humana explícita sobre el template v2 exacto."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at-utc", required=True)
    parser.add_argument("--attestation-id", required=True)
    args = parser.parse_args()
    document = json.loads(args.template.read_text(encoding="utf-8"))
    if document.get("contract_version") != "h16-h23-reviewed-claim-set-v2" or len(document.get("records", [])) != 29 or document.get("review_status") != "pending":
        raise ValueError("template v2 incompatible")
    for row in document["records"]:
        if row.get("decision") != "pending":
            raise ValueError("el template ya contiene decisiones")
        row.update({"decision": "approved", "reason": None, "reviewer": args.reviewer, "reviewed_at_utc": args.reviewed_at_utc})
    document["review_status"] = "complete"
    document["provenance"] = {"kind": "human_review_export", "imported_at_utc": None, "source_export_sha256": None, "previous_canonical_sha256": None, "attestation_id": args.attestation_id}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("la exportación recibida ya existe")
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "records": 29, "approved": 29, "reviewer": args.reviewer}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
