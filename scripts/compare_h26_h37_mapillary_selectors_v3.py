#!/usr/bin/env python3
"""Selector Mapillary multivista metadata-only y comparación con una vista."""
from __future__ import annotations
import argparse,collections,hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.camera_candidate_spatial import annotate_ambiguity,classify_camera_candidate
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--rankings",type=Path,required=True);p.add_argument("--inventory",type=Path,required=True);p.add_argument("--catalog",type=Path,required=True);p.add_argument("--campaign",type=Path,required=True);p.add_argument("--old-plan",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();rankings=json.load(open(a.rankings));inventory=json.load(open(a.inventory));catalog=json.load(open(a.catalog));campaign=json.load(open(a.campaign));old=json.load(open(a.old_plan));candidate_by={r["candidate_id"]:r for r in catalog["candidates"]};rank_by={q["query_id"]:r for q,r in zip(rankings["queries"],rankings["rankings"],strict=True)};reference_sequences={r["reference_asset"]["sequence_id"] for r in campaign["observations"]};images=[r for r in inventory["images"] if r.get("sequence_id") not in reference_sequences];slots=[{"query_id":qid,"candidate_id":r["candidate_id"],"baseline_rank":r["rank"]} for qid,ranking in rank_by.items() for r in ranking["results"][:20]];candidate_ids=sorted({r["candidate_id"] for r in slots});spatial=[]
 for image in images:
  for cid in candidate_ids:
   row=classify_camera_candidate(image,candidate_by[cid],round_radius_m=100);spatial.append({"global_record_id":f"mapillary:{image['image_id']}","candidate_id":cid,**row})
 geo={(r["global_record_id"],r["candidate_id"]):r for r in annotate_ambiguity(spatial)};selected=[]
 for slot in slots:
  eligible=[]
  for image in images:
   g=geo[(f"mapillary:{image['image_id']}",slot["candidate_id"])]
   if g["center_distance_m"]>100:continue
   class_rank={"camera_inside_candidate":0,"camera_outside_view_compatible":1,"spatially_ambiguous":2,"orientation_incompatible":4,"insufficient_orientation_metadata":4,"not_eligible":5}.get(g["classification"],5);quality=image.get("quality_score") or 0;heading=image.get("orientation_degrees");band=-1 if image.get("camera_type") in {"equirectangular","spherical"} else int((heading or 0)//90);priority=(class_rank,g["competing_candidate_count"],0 if quality>=.6 else 1,-quality,-(image.get("width_px") or 0)*(image.get("height_px") or 0),g["surface_distance_m"],image["image_id"]);eligible.append((priority,image,g,band))
  used_sequences=set();used_bands=set()
  for _,image,g,band in sorted(eligible):
   if image.get("sequence_id") in used_sequences:continue
   # Primero diversidad angular; se relaja solo si no hay tres bandas.
   if band in used_bands and len({value[3] for value in eligible})>=3:continue
   used_sequences.add(image.get("sequence_id"));used_bands.add(band);selected.append({**slot,"image_id":image["image_id"],"sequence_id":image.get("sequence_id"),"orientation_band":band,"classification":g["classification"],"competing_candidate_count":g["competing_candidate_count"],"center_distance_m":g["center_distance_m"],"surface_distance_m":g["surface_distance_m"],"quality_score":image.get("quality_score"),"width_px":image.get("width_px"),"height_px":image.get("height_px")})
   if len(used_sequences)==3:break
 old_rows=[r for r in old["associations"] if r["baseline_rank"]<=20]
 def stats(rows):
  quality=[r["quality_score"] for r in rows if r.get("quality_score") is not None]
  return {"associations":len(rows),"covered_slots":len({(r["query_id"],r["candidate_id"]) for r in rows}),"unique_assets":len({r["image_id"] for r in rows}),"unique_sequences":len({r.get("sequence_id") for r in rows}),"quality_metadata_count":len(quality),"mean_quality":statistics.fmean(quality) if quality else None,"quality_below_0_5":sum(value<.5 for value in quality) if quality else None,"spatially_ambiguous":sum(r.get("classification")=="spatially_ambiguous" for r in rows),"orientation_incompatible":sum(r.get("classification")=="orientation_incompatible" for r in rows),"camera_inside":sum(r.get("classification")=="camera_inside_candidate" for r in rows),"mean_competing_candidates":statistics.fmean(r.get("competing_candidate_count",0) for r in rows) if rows else 0,"ambiguity_fraction":sum(r.get("classification")=="spatially_ambiguous" for r in rows)/len(rows) if rows else 0}
 new_stats=stats(selected);old_stats=stats(old_rows);numeric_delta={key:new_stats[key]-old_stats[key] for key in old_stats if isinstance(new_stats[key],(int,float)) and isinstance(old_stats[key],(int,float))};document={"schema_version":"1.0","contract_version":"h26-h37-mapillary-selector-comparison-v3","status":"metadata_only_no_download_no_inference","inputs":{"rankings_sha256":digest(a.rankings),"inventory_sha256":digest(a.inventory),"catalog_sha256":digest(a.catalog),"campaign_sha256":digest(a.campaign),"old_plan_sha256":digest(a.old_plan)},"protocol":{"query_ids":[f"H{i:02d}" for i in range(26,38)],"candidate_rank_block":[1,20],"ground_truth_used":False,"pixels_used":False,"vlm_outputs_used":False,"reference_sequences_excluded":True,"maximum_views_per_slot":3,"sequence_diversity":True,"orientation_band_diversity":True,"quality_preferred_threshold":.6},"old_selector":old_stats,"new_selector":new_stats,"delta":numeric_delta,"associations":selected,"limitations":["metadata_potential_not_visible_claim_coverage","hypothetical_fov","quality_score_not_human_quality","old_plan_does_not_retain_quality_metadata"]};document["plan_id"]="h26-h37-mapillary-selector-v3-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="plan_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"plan_id":document["plan_id"],"old":old_stats,"new":new_stats},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
