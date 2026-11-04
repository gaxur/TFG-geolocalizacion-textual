#!/usr/bin/env python3
"""Plan pairwise fijo rank10 vs ranks11-30, sin GT ni métricas."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--ct2l",type=Path,required=True);p.add_argument("--assets",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();plan=json.load(open(a.plan));ct2l=json.load(open(a.ct2l));assets=json.load(open(a.assets));asset_ids={r["image_id"] for r in assets["assets"]};assoc={(r["query_id"],r["candidate_id"]):r for r in plan["associations"]};rank_by={q["query_id"]:r for q,r in zip(ct2l["queries"],ct2l["rankings"],strict=True)};queries={q["query_id"]:q for q in plan["queries"]};pairs=[]
 for qid in sorted(queries):
  rows=rank_by[qid]["results"][:30];incumbent=rows[9];incumbent_view=assoc.get((qid,incumbent["candidate_id"]))
  for challenger in rows[10:30]:
   challenger_view=assoc.get((qid,challenger["candidate_id"]));status="ready" if incumbent_view and challenger_view and incumbent_view["image_id"] in asset_ids and challenger_view["image_id"] in asset_ids else "missing_view"
   pairs.append({"query_id":qid,"description":queries[qid]["text"],"description_sha256":queries[qid]["text_sha256"],"incumbent":{"candidate_id":incumbent["candidate_id"],"baseline_rank":10,"image_id":incumbent_view["image_id"] if incumbent_view else None},"challenger":{"candidate_id":challenger["candidate_id"],"baseline_rank":challenger["rank"],"image_id":challenger_view["image_id"] if challenger_view else None},"status":status})
 unique_images={side["image_id"] for row in pairs for side in (row["incumbent"],row["challenger"]) if side["image_id"]}
 document={"schema_version":"1.0","contract_version":"h26-h37-pairwise-plan-v1","plan_id":"","inputs":{"visual_plan_sha256":digest(a.plan),"ct2l_sha256":digest(a.ct2l),"assets_sha256":digest(a.assets)},"policy":{"query_ids":[f"H{i:02d}" for i in range(26,38)],"incumbent_rank":10,"challenger_ranks":[11,30],"maximum_promotions_per_query":2,"selection_uses_gt":False,"coordinates_sent_to_vlm":False,"ct2l_scores_sent_to_vlm":False,"candidate_ids_sent_to_vlm":False,"fixed_before_inference":True},"pairs":pairs,"summary":{"pairs":len(pairs),"ready":sum(r["status"]=="ready" for r in pairs),"missing_view":sum(r["status"]!="ready" for r in pairs),"unique_images":len(unique_images)}};document["plan_id"]="h26-h37-pairwise-plan-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="plan_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"plan_id":document["plan_id"],"summary":document["summary"],"estimated_8b_seconds":document["summary"]["ready"]*2.5},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
