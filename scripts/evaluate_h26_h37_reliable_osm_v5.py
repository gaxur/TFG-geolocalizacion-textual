#!/usr/bin/env python3
"""Evaluación post-freeze v5 con métricas geográficas y de seguridad."""
from __future__ import annotations
import argparse,hashlib,json,statistics,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--rankings",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();started=time.perf_counter();frozen=json.loads(a.rankings.read_text())
 if frozen["protocol"]["ground_truth_used"] or not frozen["protocol"]["all_variants_frozen_before_evaluation"]:raise ValueError("ranking v5 no congelado sin GT")
 campaign=json.loads(a.campaign.read_text());refs={row["query_id"]:row["reference_asset"]["position"] for row in campaign["observations"]};variants={}
 for qid,query in frozen["queries"].items():
  ref=refs[qid];rx,ry=wgs84_to_epsg25830(ref["reported_latitude"],ref["reported_longitude"]);by={row["candidate_id"]:row for row in query["baseline_results"]};base_ids=query["variants"]["baseline"]
  for name,ids in query["variants"].items():
   distances=[]
   for cid in ids:
    row=by[cid];x,y=wgs84_to_epsg25830(row["latitude"],row["longitude"]);distances.append(((x-rx)**2+(y-ry)**2)**.5)
   is_v5_policy=name in {"top1_protected","top1_conditioned","confidence_abstention"} or name.startswith("ablation_")
   selected=query["promotion_audit"]["selected_candidate_id"] if is_v5_policy else None
   source_rank=next((index+1 for index,cid in enumerate(base_ids) if cid==selected),None) if selected else None
   selected_final_rank=next((index+1 for index,cid in enumerate(ids) if cid==selected),None) if selected else None
   variants.setdefault(name,[]).append({"query_id":qid,"top1_candidate_id":ids[0],"top1_distance_m":distances[0],"top10_candidate_ids":ids[:10],"geo_recall":{str(t):{str(k):min(distances[:k])<=t for k in (1,5,10)} for t in (50,100)},"minimum_distance":{str(k):min(distances[:k]) for k in (1,5,10)},"promotion":query["promotion_audit"],"promotion_applied":selected is not None and ids!=query["variants"]["atlas_v3"],"promotion_source_rank":source_rank,"promotion_final_rank":selected_final_rank,"promotion_from_11_100":bool(selected is not None and ids!=query["variants"]["atlas_v3"] and source_rank and source_rank>10 and selected_final_rank and selected_final_rank<=10)})
 baseline={row["query_id"]:row for row in variants["baseline"]};atlas={row["query_id"]:row for row in variants["atlas_v3"]};reports={}
 for name,rows in variants.items():
  deltas=[row["top1_distance_m"]-baseline[row["query_id"]]["top1_distance_m"] for row in rows];atlas_deltas=[row["top1_distance_m"]-atlas[row["query_id"]]["top1_distance_m"] for row in rows]
  reports[name]={"rows":rows,"aggregate":{"mean_top1_distance_m":statistics.fmean(row["top1_distance_m"] for row in rows),"median_top1_distance_m":statistics.median(row["top1_distance_m"] for row in rows),"geo_recall":{str(t):{str(k):{"hits":sum(row["geo_recall"][str(t)][str(k)] for row in rows),"total":len(rows)} for k in (1,5,10)} for t in (50,100)},"improved_queries_vs_baseline":sum(delta<0 for delta in deltas),"degraded_queries_vs_baseline":sum(delta>0 for delta in deltas),"maximum_degradation_m_vs_baseline":max(deltas),"improved_queries_vs_atlas":sum(delta<0 for delta in atlas_deltas),"degraded_queries_vs_atlas":sum(delta>0 for delta in atlas_deltas),"maximum_degradation_m_vs_atlas":max(atlas_deltas),"top1_changes_vs_atlas":sum(row["top1_candidate_id"]!=atlas[row["query_id"]]["top1_candidate_id"] for row in rows),"top10_set_changes_vs_atlas":sum(set(row["top10_candidate_ids"])!=set(atlas[row["query_id"]]["top10_candidate_ids"]) for row in rows),"promotions_applied":sum(row["promotion_applied"] for row in rows),"promotions_from_ranks_11_100":sum(row["promotion_from_11_100"] for row in rows),"abstentions":sum(row["promotion"]["abstained"] for row in rows)}}
 doc={"schema_version":"1.0","contract_version":"h26-h37-reliable-osm-evaluation-v5","inputs":{"campaign_sha256":digest(a.campaign),"frozen_rankings_sha256":digest(a.rankings),"ranking_set_id":frozen["ranking_set_id"]},"protocol":{"references_loaded_only_after_all_variants_frozen":True,"distance_crs":"EPSG:25830","development_only":True,"no_policy_selected_automatically":True},"variants":reports,"resources":{"evaluation_cpu_seconds":time.perf_counter()-started},"limitations":["twelve_reused_development_queries","remote_camera_reference_unknown_accuracy","heuristic_confidence_not_probability","no_generalization_claim"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({name:report["aggregate"] for name,report in reports.items()},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
