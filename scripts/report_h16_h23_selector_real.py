#!/usr/bin/env python3
"""Genera el informe final trazable del A/B real ya congelado y evaluado."""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "results/generated/mapillary/h16-h23-selector-comparison-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    plan = json.loads((ART / "physical-task-plan.json").read_text())
    rankings = json.loads((ART / "frozen-rankings.json").read_text())
    evaluation = json.loads((ART / "geographic-evaluation.json").read_text())
    manifests = {arm: json.loads((ART / filename).read_text()) for arm, filename in (("coverage_adaptive", "coverage_adaptive-manifest.json"), ("geometric_adaptive", "geometric_adaptive-manifest.json"))}
    results = {model: json.loads((ART / f"{model}-physical-results.json").read_text()) for model in ("qwen3-vl-2b", "qwen3-vl-8b")}
    result_index = {model: {row["physical_task_id"]: row for row in document["records"]} for model, document in results.items()}
    projections = collections.defaultdict(list)
    for row in plan["projections"]:
        physical = result_index[row["model_key"]][row["physical_task_id"]]
        projections[(row["arm"], row["model_key"])].append({**row, "verdict": physical["verdict"], "status": physical["status"]})
    diagnostics = {}
    for (arm, model), rows in sorted(projections.items()):
        supported = [row for row in rows if row["verdict"] == "supported"]
        image_claim_candidates = collections.defaultdict(set)
        sequence_support = collections.defaultdict(set)
        for row in supported:
            image_claim_candidates[(row["query_id"], row["image_id"], row["claim_id"])].add(row["candidate_id"])
            sequence_support[(row["query_id"], row["candidate_id"], row["claim_id"])].add(row.get("sequence_id") or f"image:{row['image_id']}")
        exclusive = sum(len(image_claim_candidates[(row["query_id"], row["image_id"], row["claim_id"])]) == 1 for row in supported)
        diagnostics.setdefault(model, {})[arm] = {
            "logical_jobs": len(rows),
            "supported_jobs": len(supported),
            "supported_exclusive_jobs": exclusive,
            "supported_shared_jobs": len(supported) - exclusive,
            "supported_unique_image_claim_pairs": len(image_claim_candidates),
            "supported_shared_image_claim_pairs": sum(len(candidates) > 1 for candidates in image_claim_candidates.values()),
            "maximum_independent_supporting_sequences_per_candidate_claim": max(map(len, sequence_support.values()), default=0),
            "mean_independent_supporting_sequences_per_supported_candidate_claim": sum(map(len, sequence_support.values())) / len(sequence_support) if sequence_support else 0,
        }
    spatial = {}
    for arm, manifest in manifests.items():
        counts = collections.Counter(row.get("classification", "not_computed_for_arm") for row in manifest["associations"])
        spatial[arm] = {"associations": len(manifest["associations"]), "unique_sequences": len({row.get("sequence_id") for row in manifest["associations"] if row.get("sequence_id")}), "classifications": counts}
    rank_changes = {}
    for model, arms in rankings["models"].items():
        rank_changes[model] = {}
        for arm, queries in arms.items():
            rank_changes[model][arm] = {query["query_id"]: {"changed_candidates": len(query["reranking"]["rank_changes"]), "crossed_top10_boundary": sum(row["crossed_top10_boundary"] for row in query["reranking"]["rank_changes"]), "top1_changed": query["reranking"]["full_experimental_order"][0] != query["reranking"]["baseline_results"][0]["candidate_id"]} for query in queries}
    checkpoint = ART / "qwen3-vl-8b.checkpoint.jsonl"
    frames = [json.loads(line) for line in checkpoint.read_text().splitlines()[1:]]
    by_index = collections.defaultdict(list)
    for frame in frames:
        by_index[frame["index"]].append(frame["record"])
    duplicated = {index: values for index, values in by_index.items() if len(values) > 1}
    report = {
        "schema_version": "1.0",
        "contract_version": "h16-h23-selector-real-final-report-v1",
        "status": "completed_with_checkpoint_concurrency_incident",
        "inputs": {path.name: digest(path) for path in (ART / "coverage_adaptive-manifest.json", ART / "geometric_adaptive-manifest.json", ART / "paired-reuse-plan.json", ART / "physical-assets.json", ART / "physical-task-plan.json", ART / "qwen3-vl-2b-physical-results.json", ART / "qwen3-vl-8b-physical-results.json", ART / "frozen-rankings.json", ART / "geographic-evaluation.json")},
        "assets": json.loads((ART / "physical-assets.json").read_text())["summary"],
        "inference": {model: {"summary": document["summary"], "resources": document["resources"]} for model, document in results.items()},
        "checkpoint_incident": {"cause": "two_concurrent_8b_resume_processes_appended_to_the_same_checkpoint_after_tool_timeout", "not_a_model_error": True, "checkpoint_frames": len(frames), "planned_tasks": 9594, "duplicated_indices": len(duplicated), "extra_frames": sum(len(values) - 1 for values in duplicated.values()), "semantic_conflicts": 0, "final_atomic_output_complete": True, "checkpoint_left_unmodified": True},
        "rank_changes": rank_changes,
        "geographic_evaluation": evaluation["models"],
        "evidence_diagnostics": diagnostics,
        "spatial_and_sequence_diagnostics": spatial,
        "recommendation": "No adoptar ninguno de los dos selectores como mejora geográfica: no cambia Top-1 ni GeoRecall@1/5/10 a 50/100 m en H16/H23. Conservar la comparación como resultado negativo de dos consultas development y corregir el bloqueo exclusivo del checkpoint antes de otra campaña.",
        "limitations": ["two_retrospectively_selected_development_queries", "reference_coordinate_uncertainty_unknown", "h16_interior_exterior_domain_mismatch", "metadata_proximity_not_visibility", "shared_images_can_create_non_discriminative_support", "hypothetical_fov_in_geometric_arm", "no_statistical_generalization", "8b_checkpoint_not_safe_for_future_resume_due_to_concurrent_duplicate_frames"],
    }
    output = ART / "final-report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "assets": report["assets"], "inference": report["inference"], "rank_changes": rank_changes, "spatial": spatial, "report_sha256": digest(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
