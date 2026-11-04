#!/usr/bin/env python3
"""Análisis post-hoc pareado y leave-one-out de resultados v4 ya evaluados."""
from __future__ import annotations
import argparse,hashlib,json,statistics
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--evaluation",type=Path,required=True);p.add_argument("--rankings",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();evaluation=json.loads(a.evaluation.read_text());rankings=json.loads(a.rankings.read_text());baseline={row["query_id"]:row for row in evaluation["variants"]["baseline"]["rows"]};variants={}
 for name,report in evaluation["variants"].items():
  rows=[]
  for row in report["rows"]:
   base=baseline[row["query_id"]];delta=row["top1_distance_m"]-base["top1_distance_m"];rows.append({"query_id":row["query_id"],"top1_delta_m":delta,"improved":delta<0,"degraded":delta>0,"nearest_rank_gain":row["nearest_rank_shift_from_baseline"],"promotion":row["promotion"]})
  leave_one_out=[]
  for omitted in rows:
   kept=[row for row in rows if row["query_id"]!=omitted["query_id"]];leave_one_out.append({"omitted_query_id":omitted["query_id"],"mean_top1_delta_m":statistics.fmean(row["top1_delta_m"] for row in kept)})
  variants[name]={"rows":rows,"leave_one_out":{"minimum_mean_delta_m":min(row["mean_top1_delta_m"] for row in leave_one_out),"maximum_mean_delta_m":max(row["mean_top1_delta_m"] for row in leave_one_out),"improves_in_all_folds":all(row["mean_top1_delta_m"]<0 for row in leave_one_out),"folds":leave_one_out}}
 coverage={"queries":len(rankings["queries"]),"abstentions":sum(query["promotion_audit"]["abstained"] for query in rankings["queries"].values()),"informative_queries":sum(not query["promotion_audit"]["abstained"] for query in rankings["queries"].values()),"strong_promotions_available":sum(query["promotion_audit"]["evidence_level"]=="strong" for query in rankings["queries"].values()),"moderate_promotions_available":sum(query["promotion_audit"]["evidence_level"]=="moderate" for query in rankings["queries"].values())}
 doc={"schema_version":"1.0","contract_version":"h26-h37-structured-osm-analysis-v4","inputs":{"evaluation_sha256":digest(a.evaluation),"rankings_sha256":digest(a.rankings)},"protocol":{"posthoc_ground_truth_analysis":True,"no_ranking_modified":True,"leave_one_out_is_sensitivity_not_independent_evaluation":True},"coverage":coverage,"variants":variants,"decision":{"policy_replacement":False,"preferred_direction":"strong_uniqueness_aware_top5_promotion","full_structured_ranking":"promising_but_unstable","rrf":"promising_but_one_large_degradation","independent_osm_retriever":"not_yet_justified"},"limitations":["small_development_set","leave_one_out_does_not_create_independent_test","no_parameter_selected_from_leave_one_out"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({"coverage":coverage,"decision":doc["decision"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
