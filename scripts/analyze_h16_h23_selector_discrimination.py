#!/usr/bin/env python3
"""Métricas diagnósticas de evidencia existente proyectable a cada selector."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--geometric-manifest", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--partial-assets", type=Path, required=True)
    parser.add_argument("--spatial-analysis", type=Path, required=True)
    parser.add_argument("--run-2b", type=Path, required=True)
    parser.add_argument("--run-8b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifests = {"coverage_adaptive": json.loads(args.coverage_manifest.read_text()), "geometric_adaptive": json.loads(args.geometric_manifest.read_text())}
    fixture = json.loads(args.fixture.read_text())
    partial = json.loads(args.partial_assets.read_text())
    spatial = json.loads(args.spatial_analysis.read_text())
    runs = {"qwen3-vl-2b": json.loads(args.run_2b.read_text()), "qwen3-vl-8b": json.loads(args.run_8b.read_text())}
    claims = {query["query_id"]: {claim["claim_id"]: claim for claim in query["claims"]["claims"]} for query in fixture["queries"]}
    existing_associations = {(row["query_id"], row["candidate_id"], row["image_id"]): row for row in partial["associations"]}
    spatial_index = {(row["query_id"], row["candidate_id"], row["image_id"]): row for row in spatial["rows"]}
    run_index = {model: {(row["query_id"], row["candidate_id"], row["image_id"], row["claim_id"]): row for row in run["records"]} for model, run in runs.items()}
    output = {}
    for arm, manifest in manifests.items():
        selected_keys = {(row["query_id"], row["candidate_id"], row["image_id"]) for row in manifest["associations"]}
        evaluated_keys = selected_keys & set(existing_associations)
        selected_rows = [existing_associations[key] for key in sorted(evaluated_keys)]
        image_candidates = collections.defaultdict(set)
        for row in selected_rows:
            image_candidates[(row["query_id"], row["image_id"])].add(row["candidate_id"])
        arm_models = {}
        for model, records in run_index.items():
            projected = []
            for association_key in evaluated_keys:
                query_id, candidate_id, image_id = association_key
                for claim_id, claim in claims[query_id].items():
                    record = records[(query_id, candidate_id, image_id, claim_id)]
                    projected.append({**record, "specificity": claim["specificity"], "kind": claim["kind"], "spatial_classification": spatial_index[association_key]["classification"], "competing_candidate_count": spatial_index[association_key]["competing_candidate_count"], "shared_image_within_query": len(image_candidates[(query_id, image_id)]) > 1})
            supported = [row for row in projected if row["verdict"] == "supported"]
            physical_pairs = collections.defaultdict(set)
            sequence_support = collections.defaultdict(set)
            for row in supported:
                physical_pairs[(row["query_id"], row["image_id"], row["claim_id"])].add(row["candidate_id"])
                sequence_support[(row["query_id"], row["candidate_id"], row["claim_id"])].add(row.get("sequence_id") or f"image:{row['image_id']}")
            shared_supported = [row for row in supported if len(physical_pairs[(row["query_id"], row["image_id"], row["claim_id"])]) > 1]
            exclusive_supported = [row for row in supported if len(physical_pairs[(row["query_id"], row["image_id"], row["claim_id"])]) == 1]
            arm_models[model] = {"projected_jobs_evaluated": len(projected), "model_generate_jobs": sum(row["status"] == "valid" for row in projected), "policy_abstentions": sum(row["status"] == "policy_unverifiable" for row in projected), "supported_jobs": len(supported), "contradicted_jobs": sum(row["verdict"] == "contradicted" for row in projected), "unverifiable_jobs": sum(row["verdict"] == "unverifiable" for row in projected), "supported_exclusive_jobs": len(exclusive_supported), "supported_shared_jobs": len(shared_supported), "exclusive_support_fraction": len(exclusive_supported) / len(supported) if supported else None, "shared_support_fraction": len(shared_supported) / len(supported) if supported else None, "supported_generic_jobs": sum(row["specificity"] == "generic" for row in supported), "supported_distinctive_jobs": sum(row["specificity"] == "distinctive" for row in supported), "supported_spatially_ambiguous_jobs": sum(row["spatial_classification"] == "spatially_ambiguous" for row in supported), "supported_orientation_incompatible_jobs": sum(row["spatial_classification"] == "orientation_incompatible" for row in supported), "unique_supported_physical_image_claim_pairs": len(physical_pairs), "shared_supported_physical_image_claim_pairs": sum(len(candidate_ids) > 1 for candidate_ids in physical_pairs.values()), "distinctive_claim_sequence_support": [{"query_id": query_id, "candidate_id": candidate_id, "claim_id": claim_id, "independent_sequences": len(sequences)} for (query_id, candidate_id, claim_id), sequences in sorted(sequence_support.items()) if claims[query_id][claim_id]["specificity"] == "distinctive"], "interpretation": "diagnostic_not_accuracy"}
        output[arm] = {"manifest_id": manifest["manifest_id"], "selected_assets": len(manifest["image_ids"]), "available_selected_assets": len(manifest["available_image_ids"]), "pending_assets": len(manifest["pending_image_ids"]), "selected_associations": len(manifest["associations"]), "evaluated_existing_associations": len(evaluated_keys), "new_associations": len(manifest["associations"]) - len(evaluated_keys), "covered_slots_metadata": len({row["slot_id"] for row in manifest["associations"]}), "covered_slots_with_existing_evaluated_images": len({f"{row['query_id']}:{row['candidate_id']}" for row in selected_rows}), "models": arm_models}
    document = {"schema_version": "1.0", "contract_version": "h16-h23-selector-discrimination-audit-v1", "inputs": {path.name: digest(path) for path in (args.coverage_manifest, args.geometric_manifest, args.fixture, args.partial_assets, args.spatial_analysis, args.run_2b, args.run_8b)}, "protocol": {"ground_truth_used": False, "no_new_inference": True, "exact_existing_association_only": True, "shared_evidence_not_penalized": True}, "arms": output, "limitations": ["historical_availability_subset", "exclusive_does_not_mean_correct", "shared_does_not_mean_wrong", "hypothetical_fov", "no_human_claim_image_labels"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({arm: {"evaluated_associations": value["evaluated_existing_associations"], "models": {model: {key: metrics[key] for key in ("supported_jobs", "supported_exclusive_jobs", "supported_shared_jobs", "exclusive_support_fraction", "supported_distinctive_jobs", "supported_spatially_ambiguous_jobs")} for model, metrics in value["models"].items()}} for arm, value in output.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
