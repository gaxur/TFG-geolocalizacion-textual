#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import canonical_bytes, sha256_file  # noqa: E402
from src.tfg_phase0.mapillary_visual_pilot import (  # noqa: E402
    annotation_template,
    select_candidate_images,
    select_pilot_candidates,
    vlm_template,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara selección y contratos del piloto Mapillary sin red")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/rankings.json")
    parser.add_argument("--plan", type=Path, default=ROOT / "results/generated/f5/h11-h25-independent/plan.json")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    paths = {"inventory": args.inventory, "coverage": args.coverage, "rankings": args.rankings, "plan": args.plan}
    documents = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
    selection = select_pilot_candidates(documents["inventory"], documents["coverage"], documents["rankings"], documents["plan"], input_hashes={name: sha256_file(path) for name, path in paths.items()})
    image_plan = select_candidate_images(selection, documents["inventory"])
    annotations = annotation_template(selection, image_plan)
    vlm = vlm_template(selection, image_plan)
    planned_photos = {"schema_version": "1.0", "contract_version": "mapillary-photo-manifest-v1", "selection_id": selection["selection_id"], "image_plan_id": image_plan["image_plan_id"], "terms_review_confirmed_by_operator": False, "requested_count": image_plan["planned_image_count"], "downloaded_count": 0, "photos": [{"candidate_id": candidate["candidate_id"], "query_id": next(row["query_id"] for row in selection["candidates"] if row["candidate_id"] == candidate["candidate_id"]), "baseline_rank": next(row["baseline_rank"] for row in selection["candidates"] if row["candidate_id"] == candidate["candidate_id"]), "image_id": image["image_id"], "distance_to_candidate_m": image["distance_to_candidate_m"], "orientation_degrees": image.get("orientation_degrees"), "angular_difference_degrees": image.get("angular_difference_degrees"), "quality_score": image.get("quality_score"), "status": "planned_not_downloaded_terms_review_pending", "logical_path": None, "creator": None, "creator_profile_url": None, "attribution": None, "provider_attribution": "Mapillary", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "modifications": None, "source_page_url": f"https://www.mapillary.com/app/?pKey={image['image_id']}"} for candidate in image_plan["candidates"] for image in candidate["images"]]}
    args.output_root.mkdir(parents=True, exist_ok=True)
    outputs = {"selection.json": selection, "image-plan.json": image_plan, "photo-manifest.json": planned_photos, "annotation-template.json": annotations, "vlm-verification-template.json": vlm}
    for name, document in outputs.items():
        (args.output_root / name).write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"selection_id": selection["selection_id"], "candidate_count": len(selection["candidates"]), "planned_image_count": image_plan["planned_image_count"], "bands": {band: sum(row["distance_band"] == band for row in selection["candidates"]) for band in ("lt25", "25_50", "50_100", "none")}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
