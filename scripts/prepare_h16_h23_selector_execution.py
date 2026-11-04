#!/usr/bin/env python3
"""Prepara el presupuesto físico A/B y ejecuta un preflight totalmente offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.visual_reranking import canonical_bytes, verdict_only_prompt, verdict_only_schema
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def provisional_task_id(model_key: str, image_id: str, claim: dict, *, policy_unverifiable: bool, image_sha256: str | None) -> str:
    model = SUPPORTED_LOCAL_MODELS[model_key]
    prompt = None if policy_unverifiable else verdict_only_prompt(claim)
    payload = {"model_id": model["model_id"], "revision": model["revision"], "weight_sha256": model["weight_sha256"], "provider": "mapillary", "provider_record_id": image_id, "image_sha256": image_sha256, "claim_sha256": hashlib.sha256(canonical_bytes(claim)).hexdigest(), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest() if prompt else None, "schema_sha256": hashlib.sha256(canonical_bytes(verdict_only_schema())).hexdigest(), "generation": {"do_sample": False, "max_new_tokens": 24, "batch_size": 1}, "execution_mode": "policy_unverifiable" if policy_unverifiable else "model", "identity_status": "final" if image_sha256 else "provisional_pending_bytes"}
    return ("visual-task-sha256-" if image_sha256 else "provisional-visual-task-sha256-") + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--geometric-manifest", type=Path, required=True)
    parser.add_argument("--paired-plan", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--partial-assets", type=Path, required=True)
    parser.add_argument("--run-2b", type=Path, required=True)
    parser.add_argument("--run-8b", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        raise RuntimeError("este preparador solo admite --dry-run; use el runner autorizado futuro tras completar los gates")
    manifests = {"coverage_adaptive": json.loads(args.coverage_manifest.read_text()), "geometric_adaptive": json.loads(args.geometric_manifest.read_text())}
    paired = json.loads(args.paired_plan.read_text())
    fixture = json.loads(args.fixture.read_text())
    partial = json.loads(args.partial_assets.read_text())
    authorization = json.loads(args.authorization.read_text())
    runs = {"qwen3-vl-2b": json.loads(args.run_2b.read_text()), "qwen3-vl-8b": json.loads(args.run_8b.read_text())}
    claims = {query["query_id"]: query["claims"]["claims"] for query in fixture["queries"]}
    available = {row["image_id"]: row for row in partial["assets"]}
    existing_tasks = {}
    for model_key, run in runs.items():
        tasks = set()
        claim_index = {claim["claim_id"]: claim for values in claims.values() for claim in values}
        for record in run["records"]:
            tasks.add(provisional_task_id(model_key, record["image_id"], claim_index[record["claim_id"]], policy_unverifiable=record["status"] == "policy_unverifiable", image_sha256=record["image_sha256"]))
        existing_tasks[model_key] = tasks
    arm_tasks = {arm: {model: set() for model in runs} for arm in manifests}
    arm_generate = {arm: {model: set() for model in runs} for arm in manifests}
    for arm, manifest in manifests.items():
        for association in manifest["associations"]:
            asset = available.get(association["image_id"])
            for claim in claims[association["query_id"]]:
                policy_unverifiable = bool(claim["requires_orientation"])
                for model_key in runs:
                    task_id = provisional_task_id(model_key, association["image_id"], claim, policy_unverifiable=policy_unverifiable, image_sha256=asset["sha256"] if asset else None)
                    arm_tasks[arm][model_key].add(task_id)
                    if not policy_unverifiable:
                        arm_generate[arm][model_key].add(task_id)
    models = {}
    for model_key, run in runs.items():
        union = arm_tasks["coverage_adaptive"][model_key] | arm_tasks["geometric_adaptive"][model_key]
        shared = arm_tasks["coverage_adaptive"][model_key] & arm_tasks["geometric_adaptive"][model_key]
        generate_union = arm_generate["coverage_adaptive"][model_key] | arm_generate["geometric_adaptive"][model_key]
        reusable = union & existing_tasks[model_key]
        generate_reusable = generate_union & existing_tasks[model_key]
        seconds_per_generate = run["resources"]["execution_seconds"] / max(1, run["summary"]["valid"])
        new_generate = len(generate_union - existing_tasks[model_key])
        models[model_key] = {"physical_tasks_union": len(union), "physical_tasks_shared_between_arms": len(shared), "physical_tasks_reusable": len(reusable), "physical_tasks_new": len(union - existing_tasks[model_key]), "generate_calls_union": len(generate_union), "generate_calls_reusable": len(generate_reusable), "generate_calls_new": new_generate, "automatic_abstentions_union": len(union - generate_union), "observed_seconds_per_generate": seconds_per_generate, "estimated_new_inference_seconds": new_generate * seconds_per_generate}
    confirmations = authorization.get("operator_confirmations", {})
    authorization_open = bool(authorization.get("approved") and authorization.get("terms_reviewed") and confirmations and all(confirmations.values()) and authorization.get("approved_by") and authorization.get("approved_at_utc") and authorization.get("retention_deadline_utc") and authorization.get("documentary_basis", {}).get("basis_type") in {"public_license_and_platform_terms", "individual_provider_authorization"})
    authorization_closed = bool(authorization.get("approved") is False and authorization.get("terms_reviewed") is False and not any(confirmations.values()))
    checks = {"coverage_manifest_hash": digest(args.coverage_manifest) == "e02ca2f33772f70dee602d8c58628a8712490f7a3aa2056b956e1bda81003f1d", "geometric_manifest_hash": digest(args.geometric_manifest) == "831c2bc52df35e4cf0bc6401aeef4e5ac2557b1cee7711b42dd57860269b90af", "paired_plan_hash": digest(args.paired_plan) == "036f23821f4333eb62846f6a019bb2e61e79305fa92004d51f7be34138639abb", "fixture_matches": all(manifest["inputs"]["fixture_sha256"] == digest(args.fixture) for manifest in manifests.values()), "authorization_manifest_ids_match": set(authorization["scope"]["frozen_manifest_ids"]) == {manifest["manifest_id"] for manifest in manifests.values()}, "budget_matches": authorization["scope"]["new_unique_images_maximum"] == paired["download_plan"]["pending_union"] and authorization["scope"]["hard_maximum_bytes"] == paired["download_plan"]["hard_maximum_bytes"], "authorization_state_consistent": authorization_open or authorization_closed}
    checkpoint_estimate = {}
    for model_key, data in models.items():
        previous_run = runs[model_key]
        average_record_bytes = len(canonical_bytes(previous_run["records"])) / max(1, len(previous_run["records"]))
        checkpoint_estimate[model_key] = {"average_existing_record_bytes": average_record_bytes, "estimated_checkpoint_bytes_for_union": round(data["physical_tasks_union"] * (average_record_bytes + 220)), "safety_factor_1_5_bytes": round(data["physical_tasks_union"] * (average_record_bytes + 220) * 1.5)}
    document = {"schema_version": "1.0", "contract_version": "h16-h23-selector-execution-dry-run-v1", "mode": "dry_run_offline", "network_opened": False, "model_loaded": False, "inputs": {path.name: digest(path) for path in (args.coverage_manifest, args.geometric_manifest, args.paired_plan, args.fixture, args.partial_assets, args.run_2b, args.run_8b, args.authorization)}, "checks": checks, "ready_for_download": False, "ready_for_inference": False, "blockers": ["authorization_not_approved", "terms_not_reviewed", "operator_confirmations_missing", "pending_assets_not_downloaded"], "assets": paired["asset_sets"], "download_plan": {key: value for key, value in paired["download_plan"].items() if key != "deduplicated_new_downloads"}, "models": models, "checkpoint_storage": checkpoint_estimate, "execution_order": ["validate_authorization", "validate_manifests", "acquire_pending_union_once", "freeze_asset_manifest", "materialize_physical_task_union", "reuse_exact_existing_tasks", "run_only_new_2b_tasks", "run_only_new_8b_tasks", "project_outputs_to_each_arm", "aggregate_per_candidate", "symmetric_reranking", "freeze_rankings", "evaluate_gt_in_separate_process"], "legal_review": {"review_date": "2026-10-29", "official_sources": ["https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data", "https://help.mapillary.com/hc/en-us/articles/360010234680-Accessing-imagery-and-data-through-the-Mapillary-API", "https://www.mapillary.com/developer/api-documentation/", "https://www.mapillary.com/terms"], "verified": ["imagery_declared_cc_by_sa_4_0", "attribution_example_requires_image_link_user_and_license", "official_api_exists"], "interpretation_required": ["fixed_qwen_inference_not_expressly_addressed_by_access_article", "temporary_storage_scope_depends_on_application_terms", "privacy_and_non_copyright_rights_remain"], "unavailable_or_pending": ["terms_url_returned_http_400_in_gateway", "application_specific_terms_not_reviewed_by_user", "api_quotas_and_additional_limits_not_recorded"], "blocking": ["user_terms_confirmation", "exact_manifest_authorization", "retention_deadline", "application_quota_conditions"]}, "limitations": ["pending_asset_task_ids_are_provisional_until_sha256_exists", "time_estimates_derived_from_partial_runs", "dry_run_does_not_validate_network_or_provider_quota"]}
    document["authorization_valid"] = authorization_open
    document["ready_for_download"] = authorization_open
    document["credential_checked"] = False
    document["blockers"] = ["pending_assets_not_downloaded"] if authorization_open else document["blockers"]
    if authorization_open:
        document["legal_review"]["verified"].extend(("published_rate_limits_recorded", "application_holder_review_confirmed"))
        document["legal_review"]["unavailable_or_pending"] = []
    if not all(checks.values()):
        raise ValueError(f"dry-run structural checks failed: {checks}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": checks, "assets": document["assets"], "download_plan": document["download_plan"], "models": models, "checkpoint_storage": checkpoint_estimate, "blockers": document["blockers"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
