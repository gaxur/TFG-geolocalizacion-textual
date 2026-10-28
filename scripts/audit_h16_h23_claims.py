#!/usr/bin/env python3
"""Auditoría automática de claims; nunca los aprueba como revisión humana."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    rows = []
    for query in fixture["queries"]:
        text = query["text"]
        issues = []
        for claim in query["claims"]["claims"]:
            span = claim["evidence"]["span"]
            exact = text[span["start"]:span["end"]] == claim["evidence"]["text"]
            source_ok = claim["source_text_sha256"] == query["text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
            orientation_policy_ok = not claim["requires_orientation"] or claim["kind"] == "egocentric_relation"
            if not exact or not source_ok or not orientation_policy_ok:
                issues.append({"claim_id": claim["claim_id"], "exact_span": exact, "source_hash": source_ok, "orientation_policy": orientation_policy_ok})
        warnings = []
        if query["query_id"] == "H16":
            warnings.extend(["interior_claims_vs_exterior_mapillary", "dark_choir_may_be_semantic_mistranslation_of_spanish_retelling"])
        rows.append({"query_id": query["query_id"], "text_sha256": query["text_sha256"], "claim_count": len(query["claims"]["claims"]), "automatic_contract_checks_passed": not issues, "issues": issues, "warnings": warnings, "human_review_status": "pending"})
    document = {"schema_version": "1.0", "contract_version": "h16-h23-claim-audit-v1", "fixture_id": fixture["fixture_id"], "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(), "automatic_audit_only": True, "human_approval_granted": False, "rows": rows, "gate": "blocked_pending_human_review", "instructions": ["verify semantic fidelity to en_cartographic", "reject invented or nonvisual claims", "orientation claims remain unverifiable without comparable heading", "do not reuse es_original verdicts"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"claims": sum(row["claim_count"] for row in rows), "automatic_checks_passed": all(row["automatic_contract_checks_passed"] for row in rows), "human_approval_granted": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
