#!/usr/bin/env python3
"""Promociones OSM exclusivas y auditables, congeladas sin GT."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
POLICIES=(("exact_name_rank1","exact",1),("exact_name_rank5","exact",5),("exact_name_rank10","exact",10),("exact_name_visual_rank1","exact_visual",1),("exact_name_visual_rank5","exact_visual",5),("unique_max_visual_rank5","unique_visual",5),("unique_max_visual_rank10","unique_visual",10))
def promote(ids,candidate_id,target):
 if candidate_id in ids[:10]:return list(ids)
 output=[x for x in ids if x!=candidate_id];output.insert(target-1,candidate_id);return output
def main():
 p=argparse.ArgumentParser();p.add_argument("--osm",type=Path,required=True);p.add_argument("--visual",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();osm=json.load(open(a.osm));visual=json.load(open(a.visual));queries={}
 for qid,oquery in osm["queries"].items():
  vquery=visual["queries"][qid];baseline=[r["candidate_id"] for r in oquery["baseline_results"]];visual_positive={r["candidate_id"]:r["positive_evidence"] for r in vquery["original_aggregate"]["candidates"]};evidence={r["candidate_id"]:r for r in oquery["osm_evidence"]};variants={"baseline":baseline};audits={}
  exact=[r for r in evidence.values() if any(m["kind"]=="exact_name" for m in r["matches"])];ordered=sorted(evidence.values(),key=lambda r:(-r["raw_score"],baseline.index(r["candidate_id"]),r["candidate_id"]));max_unique=ordered[0] if ordered and (len(ordered)==1 or ordered[0]["raw_score"]-ordered[1]["raw_score"]>=1.5) else None
  for name,kind,target in POLICIES:
   eligible=[]
   if kind=="exact":eligible=exact
   elif kind=="exact_visual":eligible=[r for r in exact if visual_positive[r["candidate_id"]]>0]
   elif kind=="unique_visual" and max_unique and visual_positive[max_unique["candidate_id"]]>0:eligible=[max_unique]
   selected=sorted(eligible,key=lambda r:(-sum(m["weight"] for m in r["matches"] if m["kind"]=="exact_name"),-r["raw_score"],baseline.index(r["candidate_id"]),r["candidate_id"]))[:1];final=promote(baseline,selected[0]["candidate_id"],target) if selected else list(baseline);variants[name]=final;audits[name]={"eligible_candidate_ids":[r["candidate_id"] for r in eligible],"selected_candidate_id":selected[0]["candidate_id"] if selected else None,"target_rank":target,"operation_applied":bool(selected and selected[0]["candidate_id"] not in baseline[:10]),"evidence":selected[0]["matches"] if selected else []}
  queries[qid]={"baseline_results":oquery["baseline_results"],"variants":variants,"promotion_audit":audits}
 document={"schema_version":"1.0","contract_version":"h26-h37-osm-promotions-v4","ranking_set_id":"","status":"exploratory_development_frozen_before_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"maximum_promotions_per_query":1,"exact_name_requires_literal_osm_tag_match":True,"unique_max_margin":1.5,"policies":[{"name":n,"eligibility":k,"target_rank":r} for n,k,r in POLICIES]},"inputs":{"osm_sha256":digest(a.osm),"visual_sha256":digest(a.visual)},"queries":queries};document["ranking_set_id"]="h26-h37-osm-promotions-v4-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"ranking_set_id":document["ranking_set_id"],"queries":len(queries),"policies":len(POLICIES)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
