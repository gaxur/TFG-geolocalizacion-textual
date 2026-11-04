#!/usr/bin/env python3
"""Congela políticas pairwise antes de consultar GT development."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
EVIDENCE_PRIORITY={"text":0,"landmark":1,"geometry":2,"attribute":3,"generic":4,"none":5}
def main():
 p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--ct2l",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();run=json.load(open(a.run));ct2l=json.load(open(a.ct2l));rank_by={q["query_id"]:r for q,r in zip(ct2l["queries"],ct2l["rankings"],strict=True)};queries={}
 policies=[]
 for scope in ("local","deep","combined"):
  for confidence in ("high","medium_or_high"):
   for maximum in (1,2):policies.append({"name":f"pairwise_{scope}_{confidence}_max{maximum}","scope":scope,"confidence":confidence,"maximum_promotions":maximum})
 for qid,ranking in rank_by.items():
  baseline=ranking["results"][:100];base_ids=[r["candidate_id"] for r in baseline];rows=[r for r in run["projections"] if r["query_id"]==qid];variants={"baseline":base_ids};audits={}
  for policy in policies:
   eligible=[]
   for row in rows:
    scope_ok=policy["scope"]=="combined" or row["strategy"]==policy["scope"]
    confidence_ok=row["confidence"]=="high" if policy["confidence"]=="high" else row["confidence"] in {"medium","high"}
    evidence_ok=row["evidence_type"] not in {"generic","none"}
    if scope_ok and confidence_ok and evidence_ok and row["winner"]=="B" and row["b_specific_match"]=="yes":
     eligible.append((0 if row["confidence"]=="high" else 1,EVIDENCE_PRIORITY[row["evidence_type"]],row["challenger"]["baseline_rank"],row))
   selected=[];seen=set()
   for *_,row in sorted(eligible):
    cid=row["challenger"]["candidate_id"]
    if cid in seen:continue
    seen.add(cid);selected.append(row)
    if len(selected)==policy["maximum_promotions"]:break
   final=list(base_ids[:10]);operations=[]
   for row in reversed(selected):
    cid=row["challenger"]["candidate_id"]
    if cid in final:continue
    displaced=final[-1];final=[cid,*final[:-1]];operations.append({"promoted_candidate_id":cid,"baseline_rank":row["challenger"]["baseline_rank"],"displaced_candidate_id":displaced,"strategy":row["strategy"],"confidence":row["confidence"],"evidence_type":row["evidence_type"]})
   remainder=[cid for cid in base_ids if cid not in final];variants[policy["name"]]=final+remainder;audits[policy["name"]]={"eligible":len(eligible),"selected":len(selected),"operations":operations}
  queries[qid]={"baseline_results":baseline,"variants":variants,"pairwise_audit":audits}
 document={"schema_version":"1.0","contract_version":"h26-h37-pairwise-rankings-v1","ranking_set_id":"","status":"frozen_before_development_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"input_top_n":100,"output_top_k":10,"policies":policies,"invalid_unverifiable_tie_neutral":True,"generic_evidence_not_promotable":True},"inputs":{"run_sha256":digest(a.run),"ct2l_sha256":digest(a.ct2l)},"queries":queries};document["ranking_set_id"]="h26-h37-pairwise-rankings-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"ranking_set_id":document["ranking_set_id"],"policies":len(policies),"queries":len(queries)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
