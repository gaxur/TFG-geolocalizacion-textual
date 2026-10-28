#!/usr/bin/env python3
"""Prepara H16/H23 Top-20 sin GT, descargas ni inferencia."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
from src.tfg_phase0.visual_reranking import canonical_bytes, compile_atomic_claims, compile_atomic_claims_v2, plan_multiview_associations


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_assets(manifests: list[Path]) -> dict[str, dict]:
    assets = {}
    for manifest_path in manifests:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in document.get("assets") or document.get("photos") or []:
            if row.get("status") not in {"downloaded", "reused"}:
                continue
            path = (manifest_path.parent / row["logical_path"]).resolve()
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"asset local inválido: {row['image_id']}")
            assets[row["image_id"]] = {**row, "resolved_path": str(path), "source_manifest_sha256": sha256_file(manifest_path)}
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan simétrico H16/H23 Top-20, en_cartographic, madrid-50m.")
    parser.add_argument("--rankings", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/top100/rankings.json")
    parser.add_argument("--plan", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/plan.json")
    parser.add_argument("--inventory", type=Path, default=ROOT / "results/generated/mapillary/d004-buffer100m/inventory.json")
    parser.add_argument("--local-manifests", nargs="+", type=Path, default=[ROOT / "results/generated/mapillary/visual-pilot-v1/photo-manifest.json", ROOT / "results/generated/mapillary/h11-visual-development-v1/asset-manifest.json"])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--candidate-depth", type=int, choices=(20, 50), default=20)
    parser.add_argument("--max-images-per-candidate", type=int, default=8)
    parser.add_argument("--corrected-v2", action="store_true")
    args = parser.parse_args()
    rankings = json.loads(args.rankings.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    reject_ground_truth(rankings, path="rankings")
    reject_ground_truth(plan, path="plan")
    reject_ground_truth(inventory, path="inventory")
    if args.max_images_per_candidate != 8:
        raise ValueError("la política principal exige ocho imágenes")
    query_ids = ("H16", "H23")
    rows = [row for row in rankings["rows"] if row["query_id"] in query_ids and row["gallery_id"] == "madrid-50m" and (args.corrected_v2 or row["kind"] == "en_cartographic")]
    controls = {row["query_id"]: row for row in plan["controls"] if row["query_id"] in query_ids and (args.corrected_v2 or row["kind"] == "en_cartographic")}
    if len(rows) != 2 or len(controls) != 2 or any(len(row["results"]) != 100 for row in rows):
        raise ValueError("ranking/controles objetivo no disponibles de forma única")
    local = local_assets(args.local_manifests)
    query_documents = []
    all_associations = []
    for ranking in sorted(rows, key=lambda row: row["query_id"]):
        query_id = ranking["query_id"]
        selected = ranking["results"][:args.candidate_depth]
        candidates = [{key: row[key] for key in ("candidate_id", "latitude", "longitude")} for row in selected]
        multiview = plan_multiview_associations(candidates, inventory["images"], max_distance_m=100, max_images_per_candidate=8)
        rank_by = {row["candidate_id"]: row["rank"] for row in selected}
        associations = [{**row, "query_id": query_id, "baseline_rank": rank_by[row["candidate_id"]], "orientation_comparable": False, "orientation_comparability_method": "not_established"} for row in multiview["associations"]]
        associations.sort(key=lambda row: (row["baseline_rank"], row["orientation_band"], row["distance_to_candidate_m"], row["image_id"]))
        claims = compile_atomic_claims_v2(controls[query_id]["text"], []) if args.corrected_v2 else compile_atomic_claims(controls[query_id]["text"], [])
        query_documents.append({"query_id": query_id, "control_id": controls[query_id]["control_id"], "text": controls[query_id]["text"], "text_sha256": controls[query_id]["text_sha256"], "kind": controls[query_id]["kind"], "gallery_id": "madrid-50m", "candidate_depth": args.candidate_depth, "baseline_results": selected, "claims": claims, "claims_review_status": "pending_human_review", "covered_candidates": multiview["covered_candidate_count"], "association_count": len(associations)})
        all_associations.extend(associations)
    selected_ids = sorted({row["image_id"] for row in all_associations})
    reusable_ids = sorted(set(selected_ids).intersection(local))
    new_ids = sorted(set(selected_ids) - set(local))
    associations_by_image = {}
    for row in all_associations:
        associations_by_image.setdefault(row["image_id"], []).append({"query_id": row["query_id"], "candidate_id": row["candidate_id"], "baseline_rank": row["baseline_rank"]})
    sizes = [row["size_bytes"] for row in local.values()]
    mean_size = sum(sizes) / len(sizes)
    fixture = {"schema_version": "2.0" if args.corrected_v2 else "1.0", "contract_version": "h16-h23-multicandidate-fixture-v2" if args.corrected_v2 else "h16-h23-multicandidate-fixture-v1", "fixture_id": "", "fixture_role": "historical_development", "inputs": {"rankings_sha256": sha256_file(args.rankings), "plan_sha256": sha256_file(args.plan), "inventory_sha256": sha256_file(args.inventory), "local_manifest_sha256": [sha256_file(path) for path in args.local_manifests]}, "policy": {"query_ids": list(query_ids), "variant_family": "corrected_v2" if args.corrected_v2 else "en_cartographic", "gallery_id": "madrid-50m", "complete_symmetric_rank_block": [1, args.candidate_depth], "maximum_distance_m": 100, "maximum_images_per_candidate": 8, "ground_truth_used": False, "coverage_used_for_candidate_selection": False, "no_coverage_is_neutral": True, "failed_download_is_neutral": True, "unverifiable_is_neutral": True, "negative_evidence_enabled": False}, "queries": query_documents, "associations": all_associations, "assets": selected_ids, "coverage": {"candidate_slots": 2 * args.candidate_depth, "covered_candidate_slots": sum(row["covered_candidates"] for row in query_documents), "association_count": len(all_associations), "unique_assets": len(selected_ids), "reusable_local_assets": len(reusable_ids), "new_assets_required": len(new_ids)}, "execution_gate": {"claims_human_review_complete": False, "acquisition_authorized": False, "paired_2b_8b_inference_permitted": False}, "limitations": ["historical_development_queries_selected_after_geographic_ceiling", "h16_interior_query_vs_exterior_mapillary", "metadata_proximity_does_not_prove_visibility", "v1_verdicts_not_compatible"]}
    fixture["fixture_id"] = "h16-h23-multicandidate-sha256-" + hashlib.sha256(canonical_bytes(fixture)).hexdigest()
    assets = [{"image_id": image_id, "status": "reusable" if image_id in local else "not_authorized", "associations": sorted(associations_by_image[image_id], key=lambda row: (row["query_id"], row["baseline_rank"], row["candidate_id"])), "shared_association_count": len(associations_by_image[image_id]), "existing_sha256": local.get(image_id, {}).get("sha256"), "existing_logical_path": local.get(image_id, {}).get("resolved_path")} for image_id in selected_ids]
    acquisition = {"schema_version": "1.0", "contract_version": "h16-h23-multicandidate-acquisition-plan-v1", "plan_id": "", "fixture_id": fixture["fixture_id"], "authorization": {"status": "not_authorized", "downloads_permitted": False, "purpose": "paired Qwen3-VL-2B/8B multicandidate reranking and positive promotion on complete H16/H23 Top-20 blocks", "maximum_resolution_px": 1024}, "counts": {"candidate_slots": fixture["coverage"]["candidate_slots"], "covered_candidate_slots": fixture["coverage"]["covered_candidate_slots"], "candidate_image_associations": len(all_associations), "unique_image_ids": len(selected_ids), "already_available": len(reusable_ids), "new_images": len(new_ids), "shared_image_ids": sum(len(value) > 1 for value in associations_by_image.values())}, "storage": {"observed_local_mean_bytes": mean_size, "estimated_new_bytes": round(len(new_ids) * mean_size), "hard_maximum_bytes": len(new_ids) * 8_000_000, "cache_dir": "data/cache/mapillary"}, "assets": assets, "protocol": {"download_once_by_image_id": True, "same_assets_for_2b_and_8b": True, "no_replacement_after_pixel_inspection": True, "sha256_required": True, "cache_atomic_write_required": True}, "limitations": ["new_terms_authorization_required", "claims_require_human_review_before_inference", "no_download_performed"]}
    acquisition_payload = {key: value for key, value in acquisition.items() if key != "plan_id"}
    acquisition["plan_id"] = "h16-h23-acquisition-sha256-" + hashlib.sha256(canonical_bytes(acquisition_payload)).hexdigest()
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "fixture.json").write_bytes(canonical_bytes(fixture) + b"\n")
    (args.output_root / "acquisition-plan.json").write_bytes(canonical_bytes(acquisition) + b"\n")
    print(json.dumps({"fixture_id": fixture["fixture_id"], "plan_id": acquisition["plan_id"], **acquisition["counts"], **acquisition["storage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
