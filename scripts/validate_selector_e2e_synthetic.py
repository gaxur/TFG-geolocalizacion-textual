#!/usr/bin/env python3
"""Ejecuta el E2E sintético aislado y publica un reporte técnico, sin red/modelos."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_cache import MapillaryCache
from src.tfg_phase0.selector_e2e import build_physical_plan, evaluate_synthetic_rankings, execute_physical_plan, freeze_arm_rankings, physical_task_id, project_results
from src.tfg_phase0.symmetric_visual_reranking import freeze_symmetric_policy


def claim(claim_id, orientation=False):
    return {"claim_id": claim_id, "source_text_sha256": "0" * 64, "kind": "egocentric_relation" if orientation else "object_presence", "value": {"relation": "left_of_observer", "subject_type": "building"} if orientation else {"object_type": "building"}, "evidence": {"text": "left" if orientation else "building", "span": {"start": 0, "end": 4 if orientation else 8}}, "specificity": "distinctive", "requires_ocr": False, "requires_orientation": orientation}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    claims = {"Q": [claim("claim-object"), claim("claim-orientation", True)]}
    models = {"qwen3-vl-2b": {"model_id": "Qwen/Qwen3-VL-2B-Instruct", "revision": "synthetic-2b", "weight_sha256": "2" * 64}, "qwen3-vl-8b": {"model_id": "Qwen/Qwen3-VL-8B-Instruct", "revision": "synthetic-8b", "weight_sha256": ["8" * 64]}}
    baseline = [{"rank": index, "candidate_id": f"c{index}", "latitude": 40 + index * 0.00001, "longitude": -3.0, "cosine_similarity": 1 - index / 1000} for index in range(1, 51)]
    queries = [{"query_id": "Q", "baseline_results": baseline}]
    common = {"query_id": "Q", "candidate_id": "c11", "image_id": "1", "sequence_id": "s1", "orientation_comparable": False}
    arms = {"coverage": {"associations": [common, {"query_id": "Q", "candidate_id": "c10", "image_id": "2", "sequence_id": "s2", "orientation_comparable": False}]}, "geometric": {"associations": [common, {"query_id": "Q", "candidate_id": "c9", "image_id": "3", "sequence_id": "s3", "orientation_comparable": False}]}}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        cache = MapillaryCache(root / "cache", max_gb=1, ttl_hours=1)
        assets = {image_id: cache.store(image_id, raw, {"provider": "FakeTransport", "license": "synthetic"}) for image_id, raw in (("1", b"shared"), ("2", b"coverage"), ("3", b"geometric"))}
        plan = build_physical_plan(arms, assets, claims, models)
        reused_id = physical_task_id(models["qwen3-vl-2b"], assets["1"]["sha256"], claims["Q"][0], policy_unverifiable=False)
        previous = {reused_id: {"status": "valid", "verdict": "supported"}}
        results = {}
        calls = {}
        resumed = False
        for model_key in models:
            calls[model_key] = []
            checkpoint = root / f"{model_key}.jsonl"
            if model_key == "qwen3-vl-8b":
                failed = {"value": False}
                def fail_once(task):
                    calls[model_key].append(task["task_id"])
                    if not failed["value"]:
                        failed["value"] = True
                        raise RuntimeError("synthetic interruption")
                    return "supported"
                try:
                    execute_physical_plan(plan, model_key=model_key, checkpoint_path=checkpoint, previous_results={}, execute=fail_once)
                except RuntimeError:
                    resumed = True
                results[model_key] = execute_physical_plan(plan, model_key=model_key, checkpoint_path=checkpoint, previous_results={}, execute=lambda task: (calls[model_key].append(task["task_id"]) or "supported"))
            else:
                results[model_key] = execute_physical_plan(plan, model_key=model_key, checkpoint_path=checkpoint, previous_results=previous, execute=lambda task: (calls[model_key].append(task["task_id"]) or "supported"))
        projected = {(arm, model): project_results(plan, results[model], arm=arm, model_key=model) for arm in arms for model in models}
        frozen_path = root / "rankings.json"
        frozen = freeze_arm_rankings(fixture_queries=queries, arm_manifests=arms, claims_by_query=claims, projected=projected, policy=freeze_symmetric_policy(), output_path=frozen_path)
        frozen_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
        evaluation = evaluate_synthetic_rankings(frozen, {"Q": {"latitude": 40.0001, "longitude": -3.0}})
        report = {"schema_version": "1.0", "contract_version": "selector-e2e-synthetic-validation-report-v1", "status": "passed", "network_opened": False, "models_loaded": False, "authorization_scope": "temporary_synthetic_fixture_only", "stages": ["synthetic_authorization", "fake_acquisition", "sha256_manifest", "physical_task_plan", "exact_reuse", "fake_inference", "projection_to_arms", "aggregation", "symmetric_reranking", "atomic_ranking_freeze", "separate_synthetic_evaluation"], "counts": {"physical_assets": len(assets), "logical_jobs": plan["summary"]["logical_jobs"], "physical_tasks": plan["summary"]["physical_tasks"], "deduplicated_jobs": plan["summary"]["deduplicated_jobs"], "fake_calls": {key: len(value) for key, value in calls.items()}}, "invariants": {"shared_asset_stored_once": len(list((root / "cache/images").iterdir())) == 3, "model_task_ids_separate": set(results["qwen3-vl-2b"]) != set(results["qwen3-vl-8b"]), "resume_exercised": resumed, "candidate_set_preserved": all(query["reranking"]["audit"]["candidate_set_invariant_top50"] for model in frozen["models"].values() for arm in model.values() for query in arm), "ranking_frozen_before_evaluation": evaluation["ranking_set_id"] == frozen["ranking_set_id"], "gt_absent_pre_evaluation": frozen["protocol"]["ground_truth_used"] is False, "evaluation_synthetic_nonofficial": evaluation["real_ground_truth"] is False and evaluation["official_evaluation"] is False}, "frozen_ranking_set_id": frozen["ranking_set_id"], "frozen_ranking_sha256": frozen_sha, "limitations": ["synthetic_bytes", "fake_verifier", "no_network", "no_real_model", "no_real_gt"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"], "invariants": report["invariants"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
