#!/usr/bin/env python3
"""Evalúa post-freeze rankings v4; GT solo se carga en este proceso."""
from __future__ import annotations
import argparse,hashlib,json,statistics,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--rankings",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();started=time.perf_counter();frozen=json.loads(a.rankings.read_text())
 if frozen["protocol"]["ground_truth_used"] or not frozen["protocol"]["all_variants_frozen_before_evaluation"]:raise ValueError("rankings no congelados sin GT")
 campaign=json.loads(a.campaign.read_text());refs={row["query_id"]:row["reference_asset"]["position"] for row in campaign["observations"]};variants={}
 for qid,query in frozen["queries"].items():
  ref=refs[qid];rx,ry=wgs84_to_epsg25830(ref["reported_latitude"],ref["reported_longitude"]);by={row["candidate_id"]:row for row in query["baseline_results"]};baseline_rank={row["candidate_id"]:row["rank"] for row in query["baseline_results"]}
  for name,ids in query["variants"].items():
   distances=[]
   for cid in ids:
    row=by[cid];x,y=wgs84_to_epsg25830(row["latitude"],row["longitude"]);distances.append(((x-rx)**2+(y-ry)**2)**.5)
   near50=next((index+1 for index,value in enumerate(distances) if value<=50),None);near100=next((index+1 for index,value in enumerate(distances) if value<=100),None)
   variants.setdefault(name,[]).append({"query_id":qid,"top1_candidate_id":ids[0],"top1_distance_m":distances[0],"top10_candidate_ids":ids[:10],"geo_recall":{str(t):{str(k):min(distances[:k])<=t for k in (1,5,10)} for t in (50,100)},"nearest_rank":{ "50":near50,"100":near100},"nearest_rank_shift_from_baseline":{"50":None,"100":None},"promotion":query["promotion_audit"]})
 baseline_rows={row["query_id"]:row for row in variants["baseline"]}
 for name,rows in variants.items():
  for row in rows:
   base=baseline_rows[row["query_id"]]
   for threshold in ("50","100"):
    row["nearest_rank_shift_from_baseline"][threshold]=None if row["nearest_rank"][threshold] is None or base["nearest_rank"][threshold] is None else base["nearest_rank"][threshold]-row["nearest_rank"][threshold]
 reports={}
 for name,rows in variants.items():
  reports[name]={"rows":rows,"aggregate":{"mean_top1_distance_m":statistics.fmean(row["top1_distance_m"] for row in rows),"median_top1_distance_m":statistics.median(row["top1_distance_m"] for row in rows),"geo_recall":{str(t):{str(k):{"hits":sum(row["geo_recall"][str(t)][str(k)] for row in rows),"total":len(rows)} for k in (1,5,10)} for t in (50,100)},"improved_queries":sum(row["top1_distance_m"]<baseline_rows[row["query_id"]]["top1_distance_m"]-1e-9 for row in rows),"degraded_queries":sum(row["top1_distance_m"]>baseline_rows[row["query_id"]]["top1_distance_m"]+1e-9 for row in rows),"top1_changes":sum(row["top1_candidate_id"]!=baseline_rows[row["query_id"]]["top1_candidate_id"] for row in rows),"top10_set_changes":sum(set(row["top10_candidate_ids"])!=set(baseline_rows[row["query_id"]]["top10_candidate_ids"]) for row in rows),"mean_nearest_rank_gain":{str(t):statistics.fmean(row["nearest_rank_shift_from_baseline"][str(t)] for row in rows if row["nearest_rank_shift_from_baseline"][str(t)] is not None) for t in (50,100)}}}
 doc={"schema_version":"1.0","contract_version":"h26-h37-structured-osm-evaluation-v4","inputs":{"campaign_sha256":digest(a.campaign),"frozen_rankings_sha256":digest(a.rankings),"ranking_set_id":frozen["ranking_set_id"]},"protocol":{"references_loaded_only_after_all_variants_frozen":True,"distance_crs":"EPSG:25830","development_only":True,"no_policy_selected_automatically":True},"variants":reports,"resources":{"evaluation_cpu_seconds":time.perf_counter()-started},"limitations":["twelve_development_queries_only","remote_camera_reference_unknown_accuracy","no_generalization_claim","oracle_recoverability_is_not_reranking_performance"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({name:report["aggregate"] for name,report in reports.items()},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
