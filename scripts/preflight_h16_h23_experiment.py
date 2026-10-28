#!/usr/bin/env python3
"""Comprueba gates del experimento sin red, GPU o referencias geográficas."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.h16_h23_claim_review import ClaimReviewError, validate_review


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--claim-review", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--run-2b", type=Path)
    parser.add_argument("--run-8b", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    variant = protocol["scope"]["variant"]
    fixture_variant = fixture["policy"].get("variant_family") or fixture["policy"].get("kind")
    checks = {"protocol_fixture_hash": protocol["inputs"]["fixture_sha256"] == digest(args.fixture), "protocol_plan_hash": protocol["inputs"]["acquisition_plan_sha256"] == digest(args.plan), "protocol_plan_id": protocol["inputs"]["acquisition_plan_id"] == plan["plan_id"], "fixture_identity": protocol["inputs"]["fixture_id"] == fixture["fixture_id"], "top50_fixed": protocol["scope"]["candidate_depth_primary"] == 50 and fixture["policy"]["complete_symmetric_rank_block"] == [1, 50], "variant_gallery": variant in {"en_cartographic", "corrected_v2"} and fixture_variant == variant and protocol["scope"]["gallery_id"] == "madrid-50m", "no_gt_selection": fixture["policy"]["ground_truth_used"] is False and fixture["policy"]["coverage_used_for_candidate_selection"] is False}
    gates = {}
    if args.claim_review and args.claim_review.is_file():
        review = json.loads(args.claim_review.read_text(encoding="utf-8"))
        try:
            validate_review(review, fixture, protocol, require_complete=True, fixture_sha256=digest(args.fixture), protocol_sha256=digest(args.protocol))
            gates["claims_review"] = True
        except (ClaimReviewError, KeyError, TypeError):
            gates["claims_review"] = False
    else:
        gates["claims_review"] = False
    if args.authorization and args.authorization.is_file():
        authorization = json.loads(args.authorization.read_text(encoding="utf-8"))
        gates["mapillary_authorization"] = authorization.get("plan_id") == plan["plan_id"] and authorization.get("approved") is True and authorization.get("terms_reviewed") is True
    else:
        gates["mapillary_authorization"] = False
    if args.asset_manifest and args.asset_manifest.is_file():
        assets = json.loads(args.asset_manifest.read_text(encoding="utf-8"))
        gates["asset_manifest_complete"] = assets.get("plan_id") == plan["plan_id"] and not any(row.get("status") == "failed" for row in assets.get("assets", [])) and {row["image_id"] for row in assets.get("assets", [])} == set(fixture["assets"])
    else:
        gates["asset_manifest_complete"] = False
    paired = args.run_2b and args.run_8b and args.run_2b.is_file() and args.run_8b.is_file()
    if paired:
        run_2b = json.loads(args.run_2b.read_text(encoding="utf-8"))
        run_8b = json.loads(args.run_8b.read_text(encoding="utf-8"))
        gates["paired_inference"] = run_2b.get("fixture_id") == run_8b.get("fixture_id") == fixture["fixture_id"] and run_2b.get("inputs") == run_8b.get("inputs")
    else:
        gates["paired_inference"] = False
    gates["promotion_evaluation"] = all(gates.values())
    document = {"schema_version": "1.0", "contract_version": "h16-h23-experiment-preflight-v1", "protocol_id": protocol["protocol_id"], "checks": checks, "gates": gates, "ready_for_acquisition": all(checks.values()) and gates["claims_review"] and gates["mapillary_authorization"], "ready_for_inference": all(checks.values()) and gates["claims_review"] and gates["mapillary_authorization"] and gates["asset_manifest_complete"], "ready_for_evaluation": all(checks.values()) and gates["promotion_evaluation"], "blockers": [key for key, value in gates.items() if not value]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks_passed": all(checks.values()), "gates": gates, "blockers": document["blockers"]}, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
