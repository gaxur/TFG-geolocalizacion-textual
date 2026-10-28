#!/usr/bin/env python3
"""Materializa un inventario por consulta sin inferencia ni red."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    h01_h02 = json.loads((root / "results/generated/f5/f59-h01-h02/inputs/dataset.json").read_text(encoding="utf-8"))
    h03_h10 = json.loads((root / "results/generated/f5/f59-h03-h10/inputs/dataset.json").read_text(encoding="utf-8"))
    h11_h25 = json.loads((root / "results/generated/f5/h11-h25-independent/dataset.json").read_text(encoding="utf-8"))
    top100 = json.loads((root / "results/generated/f5/h11-h25-independent/top100/rankings.json").read_text(encoding="utf-8"))
    initial_fixture = json.loads((root / "results/generated/mapillary/visual-reranking-development-v1/atomic-development-fixture.json").read_text(encoding="utf-8"))
    expanded_fixture = json.loads((root / "results/generated/mapillary/visual-reranking-expanded-v1/fixture.json").read_text(encoding="utf-8"))
    h11_fixture = json.loads((root / "results/generated/mapillary/h11-visual-development-v1/fixture.json").read_text(encoding="utf-8"))
    visual_counts = {}
    for fixture in (initial_fixture, expanded_fixture):
        for row in fixture["associations"]:
            visual_counts.setdefault(row["query_id"], set()).add(row["image_id"])
    visual_counts["H11"] = set(h11_fixture["assets"])
    claim_counts = {row["query_id"]: len(row["claims"]) for fixture in (initial_fixture, expanded_fixture) for row in fixture["claim_sets"]}
    claim_counts["H11"] = len(h11_fixture["claims"]["claims"])
    observations = []
    for source, group in ((h01_h02, "H01-H02"), (h03_h10, "H03-H10"), (h11_h25, "H11-H25")):
        for row in source["observations"]:
            query_id = row.get("query_id") or row.get("observation_id")
            reference = row.get("reference") or row.get("panorama_coordinate") or row.get("provided_coordinate")
            variants = row.get("variants") or row.get("text") or {}
            if not isinstance(variants, dict):
                variants = {"es_original": row.get("spanish_text") or row.get("text")}
            observations.append({"query_id": query_id, "historical_group": group, "variant_names": sorted(variants), "reference": reference, "reference_uncertainty": "unknown", "ranking_depth": 100 if query_id and int(query_id[1:]) >= 11 else 10, "claims": claim_counts.get(query_id, 0), "claims_review_status": "approved_claim_set_not_claim_image_labels" if query_id == "H11" else "human_reviewed_subset" if query_id in visual_counts else "not_materialized", "mapillary_images": len(visual_counts.get(query_id, set())), "paired_2b_8b_verdicts": query_id in visual_counts, "geographic_metrics_possible": reference is not None, "visual_reranking_scope": "complete_top10" if query_id == "H11" else "one_candidate_only" if query_id in visual_counts else "none", "source_verification_dependency": "different_provider_but_source_bytes_unavailable_for_duplicate_check"})
    observations.sort(key=lambda row: int(row["query_id"][1:]))
    document = {"schema_version": "1.0", "contract_version": "h01-h25-real-artifact-audit-v1", "generated_without_network_or_inference": True, "top100_reserve_id": top100["reserve_id"], "observations": observations, "summary": {"queries": len(observations), "queries_with_any_mapillary_fixture": sum(row["mapillary_images"] > 0 for row in observations), "queries_with_complete_multicandidate_fixture": sum(row["visual_reranking_scope"] == "complete_top10" for row in observations), "queries_with_paired_vlm_outputs": sum(row["paired_2b_8b_verdicts"] for row in observations)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
