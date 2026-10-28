#!/usr/bin/env python3
"""Agrega runs pareados y aplica promoción congelada sin cargar referencias."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
from src.tfg_phase0.topn_promotion import apply_promotion, canonical_bytes, validate_policy
from src.tfg_phase0.visual_reranking import aggregate_candidate_evidence


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--reviewed-claims", type=Path, required=True)
    parser.add_argument("--run-2b", type=Path, required=True)
    parser.add_argument("--run-8b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    assets = json.loads(args.assets.read_text(encoding="utf-8"))
    review = json.loads(args.reviewed_claims.read_text(encoding="utf-8"))
    runs = {"qwen3-vl-2b": json.loads(args.run_2b.read_text(encoding="utf-8")), "qwen3-vl-8b": json.loads(args.run_8b.read_text(encoding="utf-8"))}
    for name, document in (("protocol", protocol), ("fixture", fixture), ("assets", assets), ("review", review), *runs.items()):
        reject_ground_truth(document, path=name)
    allowed_protocols = {"h16-h23-top50-experiment-protocol-v1", "h16-h23-top50-experiment-protocol-v2"}
    if protocol["contract_version"] not in allowed_protocols or protocol["inputs"]["fixture_id"] != fixture["fixture_id"] or protocol["inputs"]["fixture_sha256"] != digest(args.fixture):
        raise ValueError("protocolo o fixture incompatible")
    validate_policy(protocol["promotion_policy"])
    if review.get("fixture_id") != fixture["fixture_id"] or review.get("review_status") != "complete":
        raise ValueError("claims sin revisión humana completa")
    source_claims = {claim["claim_id"]: claim for query in fixture["queries"] for claim in query["claims"]["claims"]}
    reviewed = {row["claim"]["claim_id"]: row for row in review["records"]}
    if set(reviewed) != set(source_claims) or any(row["claim"] != source_claims[claim_id] or row["decision"] not in {"approved", "rejected"} for claim_id, row in reviewed.items()):
        raise ValueError("revisión no cubre exactamente los claims")
    approved_by_query = {query["query_id"]: [claim for claim in query["claims"]["claims"] if reviewed[claim["claim_id"]]["decision"] == "approved"] for query in fixture["queries"]}
    asset_rows = {row["image_id"]: row for row in assets["assets"] if row["status"] in {"downloaded", "reused"}}
    if assets.get("plan_id") != protocol["inputs"]["acquisition_plan_id"]:
        raise ValueError("manifest de otro plan")
    fixture_association_keys = {(row["query_id"], row["candidate_id"], row["image_id"]) for row in fixture["associations"]}
    if args.partial:
        if assets.get("contract_version") != "h16-h23-v2-partial-asset-manifest-v1" or assets.get("analysis_scope") != "partial_historical_availability_not_complete_top50" or not set(asset_rows) < set(fixture["assets"]):
            raise ValueError("manifest parcial incompatible")
        scoped_associations = assets.get("associations", [])
        scoped_keys = {(row["query_id"], row["candidate_id"], row["image_id"]) for row in scoped_associations}
        expected_scoped = {key for key in fixture_association_keys if key[2] in asset_rows}
        if len(scoped_keys) != len(scoped_associations) or scoped_keys != expected_scoped:
            raise ValueError("asociaciones parciales duplicadas o incompletas")
    else:
        if set(asset_rows) != set(fixture["assets"]):
            raise ValueError("manifest de assets incompleto")
        scoped_associations = fixture["associations"]
    for image_id, row in asset_rows.items():
        path = (args.assets.parent / row["logical_path"]).resolve()
        if not path.is_file() or digest(path) != row["sha256"]:
            raise ValueError(f"asset inválido: {image_id}")
    expected_keys = {(association["query_id"], association["candidate_id"], association["image_id"], claim["claim_id"]) for association in scoped_associations for claim in approved_by_query[association["query_id"]]}
    model_documents = {}
    run_keysets = {}
    run_records = {}
    for model_key, run in runs.items():
        if run.get("fixture_id") != fixture["fixture_id"] or run.get("model", {}).get("model_key") != model_key or run.get("inputs", {}).get("fixture_sha256") != digest(args.fixture) or run.get("inputs", {}).get("asset_manifest_sha256") != digest(args.assets) or run.get("inputs", {}).get("reviewed_claims_sha256") != digest(args.reviewed_claims):
            raise ValueError(f"run {model_key} no corresponde a inputs congelados")
        actual_key_list = [(row["query_id"], row["candidate_id"], row["image_id"], row["claim_id"]) for row in run["records"]]
        actual_keys = set(actual_key_list)
        if len(actual_keys) != len(actual_key_list) or actual_keys != expected_keys:
            raise ValueError(f"run {model_key} incompleto o con jobs ajenos")
        run_keysets[model_key] = actual_keys
        run_records[model_key] = {key: row for key, row in zip(actual_key_list, run["records"])}
        query_artifacts = []
        for query in fixture["queries"]:
            query_id = query["query_id"]
            associations = [row for row in scoped_associations if row["query_id"] == query_id]
            verdicts = [{"status": "valid", "candidate_id": row["candidate_id"], "image_id": row["image_id"], "claim_id": row["claim_id"], "verdict": row["verdict"]} for row in run["records"] if row["query_id"] == query_id and row["status"] in {"valid", "policy_unverifiable"} and row.get("verdict")]
            baseline_ids = [row["candidate_id"] for row in query["baseline_results"]]
            aggregate = aggregate_candidate_evidence(approved_by_query[query_id], associations, verdicts, candidate_ids=baseline_ids)
            promotion = apply_promotion(query["baseline_results"], aggregate, protocol["promotion_policy"])
            query_artifacts.append({"query_id": query_id, "aggregate": aggregate, "promotion": promotion})
        model_documents[model_key] = {"run_sha256": digest(args.run_2b if model_key == "qwen3-vl-2b" else args.run_8b), "resources": run.get("resources"), "summary": run.get("summary"), "model_valid_verdicts": sum(row["status"] == "valid" for row in run["records"]), "policy_unverifiable": sum(row["status"] == "policy_unverifiable" for row in run["records"]), "queries": query_artifacts}
    if run_keysets["qwen3-vl-2b"] != run_keysets["qwen3-vl-8b"]:
        raise ValueError("los runs 2B/8B no tienen el mismo keyset")
    transitions = {}
    agreements = 0
    for key in sorted(expected_keys):
        left = run_records["qwen3-vl-2b"][key].get("verdict")
        right = run_records["qwen3-vl-8b"][key].get("verdict")
        transition = f"{left}->{right}"
        transitions[transition] = transitions.get(transition, 0) + 1
        agreements += left == right
    contract = "h16-h23-v2-partial-availability-conditioned-promotion-v1" if args.partial else "h16-h23-paired-promotion-artifacts-v1"
    document = {"schema_version": "1.0", "contract_version": contract, "protocol_id": protocol["protocol_id"], "inputs": {"protocol_sha256": digest(args.protocol), "fixture_sha256": digest(args.fixture), "assets_sha256": digest(args.assets), "reviewed_claims_sha256": digest(args.reviewed_claims)}, "protocol": {"ground_truth_used": False, "same_expected_jobs_for_models": True, "frozen_numeric_policy_unchanged": True, "complete_block_requirement_satisfied": not args.partial, "official_frozen_experiment_result": not args.partial, "availability_conditioned_counterfactual": args.partial, "discard_used": False}, "coverage": {"unique_assets": len(asset_rows), "associations": len(scoped_associations), "candidate_slots_with_evidence": {query_id: len({row["candidate_id"] for row in scoped_associations if row["query_id"] == query_id}) for query_id in ("H16", "H23")}}, "paired_model_comparison": {"jobs": len(expected_keys), "exact_agreement": agreements, "exact_agreement_fraction": agreements / len(expected_keys), "verdict_transitions": transitions, "interpretation": "concordance_only_without_human_claim_image_ground_truth"}, "models": model_documents, "limitations": (["historical_asset_availability_subset", "not_complete_top50", "not_symmetric_candidate_evidence", "no_human_claim_image_ground_truth", "model_concordance_not_accuracy", "h16_interior_exterior_domain_mismatch"] if args.partial else [])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({model: {row["query_id"]: len(row["promotion"]["operations"]) for row in value["queries"]} for model, value in model_documents.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
