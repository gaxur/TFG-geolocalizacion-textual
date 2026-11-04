#!/usr/bin/env python3
"""Presupuesta piloto multivista/OCR posterior sin adquirir ni inferir."""
from __future__ import annotations
import argparse,collections,hashlib,json,math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--inventory",type=Path,required=True);p.add_argument("--catalog",type=Path,required=True);p.add_argument("--assets",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();plan=json.load(open(a.plan));inventory=json.load(open(a.inventory));catalog=json.load(open(a.catalog));assets=json.load(open(a.assets));cached={r["image_id"] for r in assets["assets"]};candidate_by={r["candidate_id"]:r for r in catalog["candidates"]};existing=collections.defaultdict(set)
 for row in plan["associations"]:existing[(row["query_id"],row["candidate_id"])].add(row["image_id"])
 # Scope predefinido: ranks1-20 por consulta. No usa GT, errores ni métricas.
 slots=[row for row in plan["associations"] if row["baseline_rank"]<=20];selected=[];new_assets=set();reused=set()
 for slot in slots:
  candidate=candidate_by[slot["candidate_id"]];cx,cy=wgs84_to_epsg25830(candidate["latitude"],candidate["longitude"]);used=existing[(slot["query_id"],slot["candidate_id"])];used_sequences={r.get("sequence_id") for r in plan["associations"] if r["query_id"]==slot["query_id"] and r["candidate_id"]==slot["candidate_id"]};eligible=[]
  for image in inventory["images"]:
   if image["image_id"] in used or image.get("sequence_id") in used_sequences:continue
   ix,iy=wgs84_to_epsg25830(image["latitude"],image["longitude"]);distance=math.hypot(cx-ix,cy-iy)
   if distance>100:continue
   priority=(distance,-(image.get("quality_score") or -1),-(image.get("width_px") or 0)*(image.get("height_px") or 0),image["image_id"]);eligible.append((priority,image))
  seen=set()
  for _,image in sorted(eligible):
   if image.get("sequence_id") in seen:continue
   seen.add(image.get("sequence_id"));selected.append({"query_id":slot["query_id"],"candidate_id":slot["candidate_id"],"baseline_rank":slot["baseline_rank"],"image_id":image["image_id"],"sequence_id":image.get("sequence_id"),"role":"additional_multiview"});(reused if image["image_id"] in cached else new_assets).add(image["image_id"])
   if len(seen)==2:break
 claims={q["query_id"]:q["claims"] for q in plan["queries"]};jobs=sum(len(claims[r["query_id"]]) for r in selected);document={"schema_version":"1.0","contract_version":"h26-h37-multiview-ocr-plan-v3","status":"proposal_not_authorized","inputs":{"source_plan_sha256":digest(a.plan),"inventory_sha256":digest(a.inventory),"catalog_sha256":digest(a.catalog),"asset_manifest_sha256":digest(a.assets)},"scope":{"query_ids":[f"H{i:02d}" for i in range(26,38)],"baseline_rank_block":[1,20],"additional_views_per_slot":2,"maximum_radius_m":100,"ground_truth_used":False},"selection":{"sequence_diversity_required":True,"pixels_used":False,"vlm_outputs_used":False,"quality_is_tie_break_only":True},"associations":selected,"summary":{"candidate_slots":len({(r["query_id"],r["candidate_id"]) for r in slots}),"additional_associations":len(selected),"additional_unique_assets":len({r["image_id"] for r in selected}),"cached_assets":len(reused),"new_assets":len(new_assets),"estimated_new_bytes":round(len(new_assets)*133000),"hard_maximum_new_bytes":len(new_assets)*8_000_000,"claim_image_jobs":jobs,"estimated_8b_seconds":jobs*1.9222,"estimated_pairwise_calls":12*20}};document["plan_id"]="h26-h37-multiview-ocr-plan-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="plan_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"plan_id":document["plan_id"],"summary":document["summary"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
