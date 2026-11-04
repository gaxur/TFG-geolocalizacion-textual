#!/usr/bin/env python3
"""Aplica el gate automático congelado al plan multivista propuesto."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--ai",type=Path,required=True);p.add_argument("--vlm",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();plan=json.load(open(a.plan));ai=json.load(open(a.ai));vlm=json.load(open(a.vlm));metrics={(r["query_id"],r["candidate_image_id"]):r for r in ai["pairs"]};verdicts={(r["query_id"],r["candidate_image_id"]):r for r in vlm["records"]};retained=set();decisions=[]
 for key,row in metrics.items():
  v=verdicts[key];clip=row["ai_metrics"]["clip_l14_336_cosine"];color=row["ai_metrics"]["rgb_histogram_cosine"];keep=v["verdict"]=="different_scene" and v["facade_match"]=="no" and v["geometry_match"]=="no" and v["distinctive_elements_match"]=="no" and not row["exact_duplicate"] and row["dhash_distance"]>12 and not(clip>=.96 and color>=.97)
  if keep:retained.add(key)
  decisions.append({"query_id":key[0],"image_id":key[1],"decision":"retain" if keep else "exclude","vlm_verdict":v["verdict"],"dhash_distance":row["dhash_distance"],"clip_cosine":clip,"color_cosine":color})
 associations=[r for r in plan["associations"] if (r["query_id"],r["image_id"]) in retained];assets=sorted({r["image_id"] for r in associations});document={**plan,"contract_version":"h26-h37-multiview-ocr-plan-filtered-v1","source_plan_id":plan["plan_id"],"plan_id":"","associations":associations,"asset_ids":assets,"overlap_gate":{"kind":"automated_conservative_overlap_gate_v1","human_review":False,"pairs":len(decisions),"retained":sum(r["decision"]=="retain" for r in decisions),"excluded":sum(r["decision"]=="exclude" for r in decisions),"decisions":decisions},"summary":{**plan["summary"],"additional_associations":len(associations),"additional_unique_assets":len(assets)}};document["plan_id"]="h26-h37-multiview-filtered-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="plan_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"plan_id":document["plan_id"],"associations":len(associations),"assets":len(assets),"excluded":document["overlap_gate"]["excluded"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
