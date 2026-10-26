#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.visual_reranking import atomic_annotation_template, canonical_bytes, compile_atomic_claims, plan_multiview_associations  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara fixture offline para verificación visual, sin GT ni descargas")
    parser.add_argument("--rankings", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/rankings.json")
    parser.add_argument("--inventory", type=Path, default=ROOT / "results/generated/mapillary/d004-buffer100m/inventory.json")
    parser.add_argument("--spec", type=Path, default=ROOT / "config/madrid_h11_h25_independent.json")
    parser.add_argument("--existing-photos", type=Path, default=ROOT / "results/generated/mapillary/visual-pilot-v1/photo-manifest.json")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-images-per-candidate", type=int, default=3)
    parser.add_argument("--max-distance-m", type=float, default=100)
    parser.add_argument("--development-query-ids", nargs="*", default=["H12", "H14", "H16", "H19"])
    args = parser.parse_args()
    rankings = json.loads(args.rankings.read_text(encoding="utf-8"))
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    existing = json.loads(args.existing_photos.read_text(encoding="utf-8"))
    selected = [row for row in rankings["rows"] if row["gallery_id"] == "madrid-50m" and row["kind"] == "en_cartographic"]
    candidates = {}
    for ranking in selected:
        for result in ranking["results"]:
            candidates[result["candidate_id"]] = {key: result[key] for key in ("candidate_id", "latitude", "longitude")}
    plan = plan_multiview_associations(sorted(candidates.values(), key=lambda row: row["candidate_id"]), inventory["images"], max_distance_m=args.max_distance_m, max_images_per_candidate=args.max_images_per_candidate)
    existing_ids = {row["image_id"] for row in existing["photos"] if row["status"] == "downloaded"}
    new_ids = sorted(set(plan["asset_image_ids"]) - existing_ids)
    sizes = [row["size_bytes"] for row in existing["photos"] if row["status"] == "downloaded"]
    average = sum(sizes) / len(sizes)
    plan["inputs"] = {"rankings_sha256": digest(args.rankings), "inventory_sha256": digest(args.inventory), "filter": {"gallery_id": "madrid-50m", "kind": "en_cartographic"}}
    plan["storage_estimate"] = {"existing_assets_reused": len(set(plan["asset_image_ids"]) & existing_ids), "new_assets_required": len(new_ids), "new_asset_image_ids": new_ids, "pilot_average_bytes": average, "estimated_new_bytes": round(len(new_ids) * average), "maximum_download_bytes_at_8mb_each": len(new_ids) * 8_000_000, "downloads_permitted_by_this_plan": False}
    claim_sets = []
    for observation in spec["observations"]:
        claims = compile_atomic_claims(observation["text"], observation["proper_toponyms"])
        claim_sets.append({"query_id": observation["query_id"], **claims})
    claims_doc = {"schema_version": "1.0", "contract_version": "visual-atomic-claim-set-v1", "source_spec_sha256": digest(args.spec), "records": claim_sets, "claim_count": sum(len(row["claims"]) for row in claim_sets), "limitations": ["deterministic_literal_rules_only", "human_review_required_before_vlm", "development_fixture_not_independent_test"]}
    photo_rows = [row for row in existing["photos"] if row["status"] == "downloaded" and row["query_id"] in set(args.development_query_ids)]
    claim_subset = []
    for record in claim_sets:
        if record["query_id"] not in args.development_query_ids:
            continue
        ordered = sorted(record["claims"], key=lambda row: (row["requires_ocr"] is False, row["requires_orientation"], row["specificity"] != "distinctive", row["evidence"]["span"]["start"]))[:5]
        claim_subset.append({"query_id": record["query_id"], "claims": ordered})
    development_associations = [{"query_id": row["query_id"], "candidate_id": row["candidate_id"], "image_id": row["image_id"]} for row in photo_rows]
    annotation_template = atomic_annotation_template(claim_subset, development_associations)
    development = {"schema_version": "1.0", "contract_version": "visual-atomic-development-fixture-v1", "query_ids": args.development_query_ids, "claim_sets": claim_subset, "associations": development_associations, "annotation_template": annotation_template, "policy": {"maximum_claims_per_query": 5, "existing_images_only": True, "selection_role": "development_not_test", "human_review_required_before_vlm": True}}
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "multiview-plan.json").write_bytes(canonical_bytes(plan) + b"\n")
    (args.output_root / "atomic-claims.json").write_bytes(canonical_bytes(claims_doc) + b"\n")
    (args.output_root / "atomic-development-fixture.json").write_bytes(canonical_bytes(development) + b"\n")
    print(json.dumps({"candidates": plan["candidate_count"], "covered": plan["covered_candidate_count"], "associations": plan["association_count"], "assets": plan["unique_asset_count"], "new_assets": len(new_ids), "claims": claims_doc["claim_count"], "development_claims": sum(len(row["claims"]) for row in claim_subset), "development_images": len(photo_rows), "development_annotations": len(annotation_template["records"]), "estimated_new_bytes": plan["storage_estimate"]["estimated_new_bytes"]}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
