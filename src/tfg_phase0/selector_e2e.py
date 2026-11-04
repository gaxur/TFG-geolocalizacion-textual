"""Integración A/B: tareas físicas, proyección, agregación y ranking congelado."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .append_jsonl_checkpoint import PlannedJob, finalize_json_atomic, run_resumable
from .camera_candidate_spatial import circular_difference_degrees
from .crs import wgs84_to_epsg25830
from .mapillary_visual_pilot import reject_ground_truth
from .symmetric_visual_reranking import apply_symmetric_reranking, canonical_bytes, freeze_symmetric_policy
from .visual_reranking import aggregate_candidate_evidence, verdict_only_prompt, verdict_only_schema


class SelectorPipelineError(ValueError):
    pass


def physical_task_id(model: Mapping[str, Any], image_sha256: str, claim: Mapping[str, Any], *, policy_unverifiable: bool) -> str:
    prompt = None if policy_unverifiable else verdict_only_prompt(claim)
    payload = {"model_id": model["model_id"], "revision": model["revision"], "weight_sha256": model["weight_sha256"], "image_sha256": image_sha256, "claim_sha256": hashlib.sha256(canonical_bytes(claim)).hexdigest(), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest() if prompt else None, "schema_sha256": hashlib.sha256(canonical_bytes(verdict_only_schema())).hexdigest(), "generation": {"do_sample": False, "max_new_tokens": 24, "batch_size": 1}, "execution_mode": "policy_unverifiable" if policy_unverifiable else "model"}
    return "physical-visual-task-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def build_physical_plan(arm_manifests: Mapping[str, Mapping[str, Any]], assets: Mapping[str, Mapping[str, Any]], claims_by_query: Mapping[str, Sequence[Mapping[str, Any]]], models: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    reject_ground_truth(arm_manifests, path="arm_manifests")
    reject_ground_truth(assets, path="assets")
    tasks = {}
    projections = []
    for arm, manifest in sorted(arm_manifests.items()):
        for association in manifest["associations"]:
            image_id = association["image_id"]
            asset = assets.get(image_id)
            if asset is None or not asset.get("sha256"):
                raise SelectorPipelineError(f"asset físico ausente: {image_id}")
            for claim in claims_by_query[association["query_id"]]:
                policy_unverifiable = bool(claim["requires_orientation"] and not association.get("orientation_comparable", False))
                for model_key, model in sorted(models.items()):
                    task_id = physical_task_id(model, asset["sha256"], claim, policy_unverifiable=policy_unverifiable)
                    task = {"task_id": task_id, "model_key": model_key, "image_id": image_id, "image_sha256": asset["sha256"], "claim": claim, "policy_unverifiable": policy_unverifiable}
                    previous = tasks.get(task_id)
                    identity_keys = ("task_id", "model_key", "image_sha256", "claim", "policy_unverifiable")
                    if previous is not None and any(previous[key] != task[key] for key in identity_keys):
                        raise SelectorPipelineError("colisión de tarea física")
                    tasks.setdefault(task_id, task)
                    projections.append({"arm": arm, "model_key": model_key, "query_id": association["query_id"], "candidate_id": association["candidate_id"], "image_id": image_id, "claim_id": claim["claim_id"], "sequence_id": association.get("sequence_id"), "physical_task_id": task_id})
    projection_keys = [(row["arm"], row["model_key"], row["query_id"], row["candidate_id"], row["image_id"], row["claim_id"]) for row in projections]
    if len(projection_keys) != len(set(projection_keys)):
        raise SelectorPipelineError("proyecciones duplicadas")
    ordered_tasks = [tasks[key] for key in sorted(tasks)]
    return {"schema_version": "1.0", "contract_version": "selector-physical-task-plan-v1", "task_plan_id": "selector-task-plan-sha256-" + hashlib.sha256(canonical_bytes(ordered_tasks)).hexdigest(), "tasks": ordered_tasks, "projections": sorted(projections, key=lambda row: tuple(row[key] for key in ("arm", "model_key", "query_id", "candidate_id", "image_id", "claim_id"))), "summary": {"logical_jobs": len(projections), "physical_tasks": len(ordered_tasks), "deduplicated_jobs": len(projections) - len(ordered_tasks)}}


def execute_physical_plan(plan: Mapping[str, Any], *, model_key: str, checkpoint_path: Path, previous_results: Mapping[str, Mapping[str, Any]], execute) -> dict[str, Mapping[str, Any]]:
    selected = [row for row in plan["tasks"] if row["model_key"] == model_key]
    jobs = []
    for row in selected:
        execution_key = row["claim"]["claim_id"] + (":policy" if row["policy_unverifiable"] else ":model")
        key = (None, model_key, row["image_sha256"], execution_key)
        jobs.append(PlannedJob(key, {key: row[key] for key in ("task_id", "model_key", "image_sha256", "policy_unverifiable")}, row, not row["policy_unverifiable"] and row["task_id"] not in previous_results))

    def policy(job):
        row = job.payload
        prior = previous_results.get(row["task_id"])
        verdict = prior["verdict"] if prior else "unverifiable"
        status = prior.get("status", "valid") if prior else "policy_unverifiable"
        return {"query_id": None, "candidate_id": model_key, "image_id": row["image_sha256"], "claim_id": job.key[3], "atomic_claim_id": row["claim"]["claim_id"], "physical_task_id": row["task_id"], "status": status, "verdict": verdict, "source": "reused" if prior else "policy"}

    def callback(job):
        row = job.payload
        result = execute(row)
        details = result if isinstance(result, Mapping) else {"status": "valid", "verdict": result}
        return {"query_id": None, "candidate_id": model_key, "image_id": row["image_sha256"], "claim_id": job.key[3], "atomic_claim_id": row["claim"]["claim_id"], "physical_task_id": row["task_id"], "source": "executed", **details}

    records = run_resumable(checkpoint_path=checkpoint_path, provenance={"task_plan_id": plan["task_plan_id"], "model_key": model_key}, jobs=jobs, execute=callback, policy_result=policy)
    return {record["physical_task_id"]: record for record in records}


def project_results(plan: Mapping[str, Any], physical_results: Mapping[str, Mapping[str, Any]], *, arm: str, model_key: str) -> list[dict[str, Any]]:
    records = []
    for row in plan["projections"]:
        if row["arm"] != arm or row["model_key"] != model_key:
            continue
        physical = physical_results.get(row["physical_task_id"])
        if physical is None:
            raise SelectorPipelineError("resultado físico ausente")
        if physical.get("atomic_claim_id", row["claim_id"]) != row["claim_id"]:
            raise SelectorPipelineError("resultado físico ligado a otro claim")
        records.append({"status": physical["status"], "verdict": physical["verdict"], "query_id": row["query_id"], "candidate_id": row["candidate_id"], "image_id": row["image_id"], "claim_id": row["claim_id"], "sequence_id": row["sequence_id"], "physical_task_id": row["physical_task_id"], "physical_result_source": physical["source"]})
    return records


def freeze_arm_rankings(*, fixture_queries: Sequence[Mapping[str, Any]], arm_manifests: Mapping[str, Mapping[str, Any]], claims_by_query: Mapping[str, Sequence[Mapping[str, Any]]], projected: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]], policy: Mapping[str, Any], output_path: Path | None = None, synthetic_fixture: bool = True) -> dict[str, Any]:
    reject_ground_truth(fixture_queries, path="fixture_queries")
    models = {}
    for (arm, model_key), records in sorted(projected.items()):
        query_outputs = []
        manifest = arm_manifests[arm]
        for query in fixture_queries:
            query_id = query["query_id"]
            associations = [row for row in manifest["associations"] if row["query_id"] == query_id]
            verdicts = [{"status": row["status"], "candidate_id": row["candidate_id"], "image_id": row["image_id"], "claim_id": row["claim_id"], "verdict": row["verdict"]} for row in records if row["query_id"] == query_id]
            candidate_ids = [row["candidate_id"] for row in query["baseline_results"]]
            aggregate = aggregate_candidate_evidence(claims_by_query[query_id], associations, verdicts, candidate_ids=candidate_ids)
            reranking = apply_symmetric_reranking(query["baseline_results"], aggregate, policy)
            query_outputs.append({"query_id": query_id, "aggregate": aggregate, "reranking": reranking})
        models.setdefault(model_key, {})[arm] = query_outputs
    contract = "synthetic-selector-frozen-ranking-set-v1" if synthetic_fixture else "h16-h23-selector-frozen-ranking-set-v1"
    prefix = "synthetic-ranking-set-sha256-" if synthetic_fixture else "h16-h23-selector-ranking-set-sha256-"
    document = {"schema_version": "1.0", "contract_version": contract, "ranking_set_id": "", "protocol": {"ground_truth_used": False, "synthetic_fixture": synthetic_fixture, "official_evaluation": not synthetic_fixture}, "policy_id": policy["policy_id"], "models": models}
    document["ranking_set_id"] = prefix + hashlib.sha256(canonical_bytes({key: value for key, value in document.items() if key != "ranking_set_id"})).hexdigest()
    if output_path is not None:
        finalize_json_atomic(output_path=output_path, document=document)
    return document


def evaluate_synthetic_rankings(frozen: Mapping[str, Any], references: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    if frozen.get("contract_version") != "synthetic-selector-frozen-ranking-set-v1" or not frozen.get("ranking_set_id"):
        raise SelectorPipelineError("ranking-set no congelado")
    results = {}
    for model_key, arms in frozen["models"].items():
        results[model_key] = {}
        for arm, queries in arms.items():
            rows = []
            for query in queries:
                reference = references[query["query_id"]]
                candidate_rows = {row["candidate_id"]: row for row in query["reranking"]["baseline_results"]}
                ids = query["reranking"]["final_top10_candidate_ids"]
                ref_x, ref_y = wgs84_to_epsg25830(reference["latitude"], reference["longitude"])
                distances = []
                for candidate_id in ids:
                    row = candidate_rows[candidate_id]
                    x, y = wgs84_to_epsg25830(row["latitude"], row["longitude"])
                    distances.append(((x - ref_x) ** 2 + (y - ref_y) ** 2) ** 0.5)
                rows.append({"query_id": query["query_id"], "top1_distance_m": distances[0], "geo10_50": min(distances) <= 50})
            results[model_key][arm] = rows
    return {"schema_version": "1.0", "contract_version": "synthetic-selector-evaluation-v1", "ranking_set_id": frozen["ranking_set_id"], "reference_kind": "synthetic_fixture", "real_ground_truth": False, "official_evaluation": False, "results": results}
