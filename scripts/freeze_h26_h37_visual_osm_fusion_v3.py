#!/usr/bin/env python3
"""Fusión comparable CT2L + visual 0.1 + OSM, congelada sin GT."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
GAMMAS=(0.01,0.02,0.03,0.05,0.075,0.1)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--visual-rankings",type=Path,required=True);p.add_argument("--osm-rankings",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();visual=json.load(open(a.visual_rankings));osm=json.load(open(a.osm_rankings));queries={}
 for qid,vquery in visual["queries"].items():
  oquery=osm["queries"][qid];osm_by={r["candidate_id"]:r["normalized_score"] for r in oquery["osm_evidence"]};positive={r["candidate_id"]:r["positive_evidence"] for r in vquery["original_aggregate"]["candidates"]};baseline=vquery["baseline_results"];scores=[r["cosine_similarity"] for r in baseline];low,high=min(scores),max(scores);variants={"baseline":[r["candidate_id"] for r in baseline]};decisions={}
  for gamma in GAMMAS:
   ordered=[]
   for row in baseline:
    cid=row["candidate_id"];ct=.5 if high==low else (row["cosine_similarity"]-low)/(high-low);score=ct+.1*positive[cid]+gamma*osm_by[cid];ordered.append((-score,row["rank"],cid,score))
   ordered.sort();name=f"visual01_osm_gamma_{gamma}";variants[name]=[r[2] for r in ordered];decisions[name]=[{"candidate_id":r[2],"final_rank":i+1,"score":r[3],"visual_positive":positive[r[2]],"osm_score":osm_by[r[2]]} for i,r in enumerate(ordered)]
  queries[qid]={"baseline_results":baseline,"variants":variants,"decisions":decisions}
 document={"schema_version":"1.0","contract_version":"h26-h37-visual-osm-fusion-v3","ranking_set_id":"","status":"exploratory_development_frozen_before_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"formula":"minmax_ct2l_top100 + 0.1*original_visual_positive + gamma*normalized_osm","gammas":list(GAMMAS),"osm_is_context_not_visibility":True},"inputs":{"visual_rankings_sha256":digest(a.visual_rankings),"osm_rankings_sha256":digest(a.osm_rankings)},"queries":queries};document["ranking_set_id"]="h26-h37-visual-osm-v3-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"ranking_set_id":document["ranking_set_id"],"variants":len(GAMMAS),"queries":len(queries)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
