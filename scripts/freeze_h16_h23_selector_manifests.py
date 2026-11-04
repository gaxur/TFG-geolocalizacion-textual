#!/usr/bin/env python3
"""Congela manifests pareados y calcula reutilización exacta sin red ni inferencia."""

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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_associations(plan: dict, arm: str, rank_by_slot: dict[str, int]) -> list[dict]:
    rows = []
    for row in plan["associations"]:
        if arm == "coverage_adaptive":
            query_id, candidate_id = row["candidate_id"].split(":", 1)
            slot_id = row["candidate_id"]
        else:
            query_id, candidate_id, slot_id = row["query_id"], row["candidate_id"], row["slot_id"]
        rows.append({"query_id": query_id, "slot_id": slot_id, "candidate_id": candidate_id, "baseline_rank": rank_by_slot[slot_id], "image_id": row["provider_record_id"], "global_record_id": row["global_record_id"], "sequence_id": row["opportunity_group_id"].split(":", 1)[1], "distance_m": row["distance_m"], "orientation_band": row["orientation_band"], "quality_score": row.get("quality_score"), "width_px": row.get("width_px"), "height_px": row.get("height_px"), **({"surface_distance_m": row["surface_distance_m"], "classification": row["classification"], "competing_candidate_count": row["competing_candidate_count"], "geometric_rank": row["geometric_rank"]} if arm == "geometric_adaptive" else {})})
    rows.sort(key=lambda row: (row["query_id"], row["candidate_id"], row["orientation_band"], row["distance_m"], row["image_id"]))
    keys = [(row["query_id"], row["candidate_id"], row["image_id"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"asociaciones duplicadas en {arm}")
    return rows


def task_fingerprint(model_key: str, image_sha256: str, claim: dict, *, policy_unverifiable: bool) -> str:
    model = SUPPORTED_LOCAL_MODELS[model_key]
    prompt = None if policy_unverifiable else verdict_only_prompt(claim)
    payload = {"model_id": model["model_id"], "revision": model["revision"], "weight_sha256": model["weight_sha256"], "image_sha256": image_sha256, "claim_sha256": hashlib.sha256(canonical_bytes(claim)).hexdigest(), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest() if prompt else None, "output_schema_sha256": hashlib.sha256(canonical_bytes(verdict_only_schema())).hexdigest(), "generation": {"do_sample": False, "max_new_tokens": 24, "batch_size": 1}, "execution_mode": "policy_unverifiable" if policy_unverifiable else "model"}
    return "visual-task-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--adaptive-config", type=Path, required=True)
    parser.add_argument("--partial-assets", type=Path, required=True)
    parser.add_argument("--run-2b", type=Path, required=True)
    parser.add_argument("--run-8b", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    config = json.loads(args.adaptive_config.read_text(encoding="utf-8"))
    partial = json.loads(args.partial_assets.read_text(encoding="utf-8"))
    runs = {"qwen3-vl-2b": json.loads(args.run_2b.read_text(encoding="utf-8")), "qwen3-vl-8b": json.loads(args.run_8b.read_text(encoding="utf-8"))}
    claims = {query["query_id"]: query["claims"]["claims"] for query in fixture["queries"]}
    candidate_slots = [{"slot_id": f"{query['query_id']}:{candidate['candidate_id']}", "query_id": query["query_id"], "candidate_id": candidate["candidate_id"], "baseline_rank": candidate["rank"]} for query in fixture["queries"] for candidate in query["baseline_results"]]
    rank_by_slot = {row["slot_id"]: row["baseline_rank"] for row in candidate_slots}
    image_meta = {row["image_id"]: row for row in inventory["images"]}
    local_assets = {row["image_id"]: row for row in partial["assets"]}
    existing_associations = {(row["query_id"], row["candidate_id"], row["image_id"]) for row in partial["associations"]}
    existing_records = {}
    for model_key, run in runs.items():
        index = {}
        for record in run["records"]:
            claim = next(claim for claim in claims[record["query_id"]] if claim["claim_id"] == record["claim_id"])
            task_id = task_fingerprint(model_key, record["image_sha256"], claim, policy_unverifiable=record["status"] == "policy_unverifiable")
            previous = index.get(task_id)
            if previous and previous["verdict"] != record["verdict"]:
                raise ValueError("tarea física repetida con veredictos distintos")
            index[task_id] = record
        existing_records[model_key] = index
    manifests = {}
    for arm, plan_key in (("coverage_adaptive", "adaptive_plan"), ("geometric_adaptive", "geometric_plan")):
        associations = normalize_associations(comparison[plan_key], arm, rank_by_slot)
        asset_ids = sorted({row["image_id"] for row in associations})
        available_ids = sorted(set(asset_ids) & set(local_assets))
        pending_ids = sorted(set(asset_ids) - set(local_assets))
        for image_id in asset_ids:
            if image_id not in image_meta:
                raise ValueError(f"imagen {image_id} ausente del inventario")
        projected = {model: {"total": 0, "reusable": 0, "new": 0, "model_generate_total": 0, "model_generate_reusable": 0, "policy_abstention_total": 0, "policy_abstention_reusable": 0, "unique_physical_tasks_total": set(), "unique_physical_tasks_reusable": set()} for model in runs}
        for association in associations:
            asset = local_assets.get(association["image_id"])
            for claim in claims[association["query_id"]]:
                policy_unverifiable = claim["requires_orientation"]
                for model_key in runs:
                    row = projected[model_key]
                    row["total"] += 1
                    row["policy_abstention_total" if policy_unverifiable else "model_generate_total"] += 1
                    if asset:
                        task_id = task_fingerprint(model_key, asset["sha256"], claim, policy_unverifiable=policy_unverifiable)
                        row["unique_physical_tasks_total"].add(task_id)
                        if task_id in existing_records[model_key]:
                            row["reusable"] += 1
                            row["policy_abstention_reusable" if policy_unverifiable else "model_generate_reusable"] += 1
                            row["unique_physical_tasks_reusable"].add(task_id)
                        else:
                            row["new"] += 1
                    else:
                        row["new"] += 1
        jobs = {}
        for model_key, row in projected.items():
            jobs[model_key] = {key: value for key, value in row.items() if not isinstance(value, set)}
            jobs[model_key]["unique_physical_tasks_on_available_assets"] = len(row["unique_physical_tasks_total"])
            jobs[model_key]["unique_physical_tasks_reusable"] = len(row["unique_physical_tasks_reusable"])
            jobs[model_key]["model_generate_new"] = row["model_generate_total"] - row["model_generate_reusable"]
            jobs[model_key]["policy_abstention_new"] = row["policy_abstention_total"] - row["policy_abstention_reusable"]
            observed = runs[model_key]["resources"]["execution_seconds"] / max(1, runs[model_key]["summary"]["valid"])
            jobs[model_key]["observed_seconds_per_generate"] = observed
            jobs[model_key]["estimated_new_generate_seconds"] = jobs[model_key]["model_generate_new"] * observed
        sequences = sorted({row["sequence_id"] for row in associations})
        manifest = {"schema_version": "1.0", "contract_version": "h16-h23-selector-manifest-v1", "manifest_id": "", "arm": arm, "protocol_id": f"h16-h23-{arm}-selector-v1", "status": "frozen_not_authorized", "inputs": {"comparison_sha256": digest(args.comparison), "fixture_sha256": digest(args.fixture), "inventory_sha256": digest(args.inventory), "adaptive_config_sha256": digest(args.adaptive_config), "partial_assets_sha256": digest(args.partial_assets), "runs": {model: digest(args.run_2b if model == "qwen3-vl-2b" else args.run_8b) for model in runs}}, "policy": {"rounds": config["rounds"], "limits": config["limits"], "selection_criteria": "coverage max-min, independent sequence, then metadata tie-breaks" if arm == "coverage_adaptive" else "coverage max-min, independent sequence, geometric compatibility, ambiguity, surface distance, metadata tie-breaks", "fov": {"basis": "hypothetical_policy" if arm == "geometric_adaptive" else "not_used_for_selection", "primary_degrees": 90 if arm == "geometric_adaptive" else None, "sensitivity_degrees": [60, 120] if arm == "geometric_adaptive" else []}, "ground_truth_used": False, "pixels_used": False, "vlm_outputs_used": False}, "candidate_slots": candidate_slots, "image_ids": asset_ids, "available_image_ids": available_ids, "pending_image_ids": pending_ids, "sequence_ids": sequences, "associations": associations, "jobs": jobs, "budget": {"selected_unique_assets": len(asset_ids), "available_assets": len(available_ids), "pending_downloads": len(pending_ids), "estimated_pending_bytes": round(len(pending_ids) * 121667.67164179105), "hard_maximum_pending_bytes": len(pending_ids) * config["limits"]["max_asset_bytes"]}, "reuse": {"existing_exact_associations": sum((row["query_id"], row["candidate_id"], row["image_id"]) in existing_associations for row in associations), "new_associations": sum((row["query_id"], row["candidate_id"], row["image_id"]) not in existing_associations for row in associations)}, "authorization": {"approved": False, "terms_reviewed": False}, "limitations": ["metadata_selection_not_visual_quality", "partial_existing_runs_only", "physical_task_reuse_requires_exact_hash_and_protocol"]}
        manifest["manifest_id"] = f"h16-h23-{arm}-manifest-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in manifest.items() if key != "manifest_id"})).hexdigest()
        manifests[arm] = manifest
    args.output_root.mkdir(parents=True, exist_ok=True)
    for arm, manifest in manifests.items():
        (args.output_root / f"{arm}-manifest.json").write_bytes(canonical_bytes(manifest) + b"\n")
    left, right = set(manifests["coverage_adaptive"]["image_ids"]), set(manifests["geometric_adaptive"]["image_ids"])
    association_sets = {arm: {(row["query_id"], row["candidate_id"], row["image_id"]) for row in manifest["associations"]} for arm, manifest in manifests.items()}
    comparison_output = {"schema_version": "1.0", "contract_version": "h16-h23-selector-paired-reuse-plan-v1", "manifest_ids": {arm: manifest["manifest_id"] for arm, manifest in manifests.items()}, "asset_sets": {"shared": len(left & right), "coverage_only": len(left - right), "geometric_only": len(right - left), "union": len(left | right)}, "association_sets": {"shared": len(association_sets["coverage_adaptive"] & association_sets["geometric_adaptive"]), "coverage_only": len(association_sets["coverage_adaptive"] - association_sets["geometric_adaptive"]), "geometric_only": len(association_sets["geometric_adaptive"] - association_sets["coverage_adaptive"])}, "download_plan": {"available_union": len((left | right) & set(local_assets)), "pending_union": len((left | right) - set(local_assets)), "deduplicated_new_downloads": sorted((left | right) - set(local_assets)), "estimated_pending_bytes": round(len((left | right) - set(local_assets)) * 121667.67164179105), "hard_maximum_bytes": len((left | right) - set(local_assets)) * config["limits"]["max_asset_bytes"]}, "authorization": {"approved": False, "terms_reviewed": False}, "limitations": ["no_downloads_permitted", "jobs_for_pending_assets_are_planned_not_executed", "planned_task_reuse_for_pending_assets_requires_downloaded_sha256"]}
    (args.output_root / "paired-reuse-plan.json").write_bytes(canonical_bytes(comparison_output) + b"\n")
    print(json.dumps({"manifests": {arm: {"manifest_id": manifest["manifest_id"], "assets": len(manifest["image_ids"]), "available": len(manifest["available_image_ids"]), "pending": len(manifest["pending_image_ids"]), "associations": len(manifest["associations"]), "jobs": manifest["jobs"]} for arm, manifest in manifests.items()}, "paired_assets": comparison_output["asset_sets"], "pending_union": comparison_output["download_plan"]["pending_union"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
