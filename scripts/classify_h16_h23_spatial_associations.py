#!/usr/bin/env python3
"""Clasifica asociaciones existentes contra toda la galería 50 m, sin GT."""

from __future__ import annotations
import argparse,collections,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.camera_candidate_spatial import annotate_ambiguity,classify_camera_candidate

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,required=True);p.add_argument("--assets",type=Path,required=True);p.add_argument("--inventory",type=Path,required=True);p.add_argument("--catalog",type=Path,required=True);p.add_argument("--run-2b",type=Path,required=True);p.add_argument("--run-8b",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();fixture=json.loads(a.fixture.read_text());assets=json.loads(a.assets.read_text());inventory=json.loads(a.inventory.read_text());catalog=json.loads(a.catalog.read_text());runs={"2b":json.loads(a.run_2b.read_text()),"8b":json.loads(a.run_8b.read_text())};images={row["image_id"]:row for row in inventory["images"]};candidates={row["candidate_id"]:row for row in catalog["candidates"]};selected_image_ids={row["image_id"] for row in assets["assets"]}
 gallery_rows=[]
 for image_id in sorted(selected_image_ids):
  image=images[image_id]
  for candidate in catalog["candidates"]:
   spatial=classify_camera_candidate(image,candidate,cell_size_m=50,round_radius_m=100)
   gallery_rows.append({"global_record_id":f"mapillary:{image_id}","candidate_id":candidate["candidate_id"],**spatial})
 gallery_rows=annotate_ambiguity(gallery_rows);gallery_index={(row["global_record_id"],row["candidate_id"]):row for row in gallery_rows};rows=[]
 for association in assets["associations"]:
  key=(f"mapillary:{association['image_id']}",association["candidate_id"]);rows.append({"query_id":association["query_id"],"image_id":association["image_id"],"candidate_id":association["candidate_id"],"baseline_rank":association.get("baseline_rank"),"sequence_id":association.get("sequence_id"),**gallery_index[key]})
 verdict_index={model:collections.defaultdict(collections.Counter) for model in runs}
 claim_sets={q["query_id"]:{c["claim_id"]:c for c in q["claims"]["claims"]} for q in fixture["queries"]}
 for model,run in runs.items():
  for record in run["records"]:verdict_index[model][(record["query_id"],record["candidate_id"],record["image_id"])][record["status"]]+=1;verdict_index[model][(record["query_id"],record["candidate_id"],record["image_id"])][record["verdict"]]+=1;verdict_index[model][(record["query_id"],record["candidate_id"],record["image_id"])]["supported_generic" if record["verdict"]=="supported" and claim_sets[record["query_id"]][record["claim_id"]]["specificity"]=="generic" else "supported_distinctive" if record["verdict"]=="supported" else "other"]+=1
 categories={}
 for category in sorted({row["classification"] for row in rows}):
  subset=[row for row in rows if row["classification"]==category];categories[category]={"physical_images":len({row["image_id"] for row in subset}),"associations":len(subset),"candidates":len({row["candidate_id"] for row in subset}),"sequences":len({row.get("sequence_id") or f"image:{row['image_id']}" for row in subset}),"verdicts":{model:dict(sum((verdict_index[model][(row["query_id"],row["candidate_id"],row["image_id"])] for row in subset),collections.Counter())) for model in runs}}
 shared=collections.defaultdict(set)
 for row in rows:shared[row["image_id"]].add((row["query_id"],row["candidate_id"]))
 doc={"schema_version":"1.0","contract_version":"camera-candidate-spatial-association-analysis-v1","inputs":{path.name:sha(path) for path in (a.fixture,a.assets,a.inventory,a.catalog,a.run_2b,a.run_8b)},"policy":{"projected_crs":"EPSG:25830","cell_size_m":50,"round_radius_m":100,"fov_basis":"hypothetical_90_degrees_for_perspective","fov_sensitivity_degrees":[60,90,120],"ambiguity_scope":"full_madrid-50m_gallery","ground_truth_used":False},"summary":{"physical_images":len(selected_image_ids),"associations":len(rows),"ambiguous_associations":sum(row["ambiguity_status"]=="spatially_ambiguous" for row in rows),"shared_physical_images":sum(len(value)>1 for value in shared.values()),"max_associations_per_image":max(map(len,shared.values()))},"categories":categories,"rows":rows,"limitations":["hypothetical_fov_not_camera_metadata","cone_intersection_not_visibility","ambiguity_against_cells_not_visible_objects","camera_accuracy_unknown","F3_not_used_as_visibility_proof"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({"summary":doc["summary"],"categories":categories},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
