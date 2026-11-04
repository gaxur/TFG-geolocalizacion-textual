#!/usr/bin/env python3
"""Evalúa rankings ya congelados y selecciona una política global development."""
from __future__ import annotations
import argparse,hashlib,json,statistics
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--rankings",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();campaign=json.loads(a.campaign.read_text());frozen=json.loads(a.rankings.read_text())
 if not frozen["protocol"]["all_variants_frozen_before_evaluation"] or frozen["protocol"]["ground_truth_used"]:raise ValueError("rankings no congelados sin GT")
 refs={r["query_id"]:r["reference_asset"]["position"] for r in campaign["observations"]};variants={}
 for qid,query in frozen["queries"].items():
  ref=refs[qid];rx,ry=wgs84_to_epsg25830(ref["reported_latitude"],ref["reported_longitude"]);by={r["candidate_id"]:r for r in query["baseline_results"]}
  for name,ids in query["variants"].items():
   distances=[]
   for candidate_id in ids:
    row=by[candidate_id];x,y=wgs84_to_epsg25830(row["latitude"],row["longitude"]);distances.append(((x-rx)**2+(y-ry)**2)**.5)
   variants.setdefault(name,[]).append({"query_id":qid,"top1_distance_m":distances[0],"geo_recall":{str(t):{str(k):min(distances[:k])<=t for k in (1,5,10)} for t in (50,100)},"top1_candidate_id":ids[0],"top10_candidate_ids":ids[:10]})
 baseline={r["query_id"]:r for r in variants["baseline"]};reports={}
 for name,rows in variants.items():
  reports[name]={"rows":rows,"aggregate":{"mean_top1_distance_m":statistics.fmean(r["top1_distance_m"] for r in rows),"median_top1_distance_m":statistics.median(r["top1_distance_m"] for r in rows),"geo_recall":{str(t):{str(k):{"hits":sum(r["geo_recall"][str(t)][str(k)] for r in rows),"total":len(rows)} for k in (1,5,10)} for t in (50,100)},"top1_changes":sum(r["top1_candidate_id"]!=baseline[r["query_id"]]["top1_candidate_id"] for r in rows),"top10_set_changes":sum(set(r["top10_candidate_ids"])!=set(baseline[r["query_id"]]["top10_candidate_ids"]) for r in rows),"improved_queries":sum(r["top1_distance_m"]<baseline[r["query_id"]]["top1_distance_m"] for r in rows),"degraded_queries":sum(r["top1_distance_m"]>baseline[r["query_id"]]["top1_distance_m"] for r in rows)}}
 configured={row["name"]:row for row in frozen["protocol"].get("variants",[]) if isinstance(row,dict) and "name" in row}
 def simplicity(name):
  if name=="baseline":return (0,0,0)
  if name in configured:return (1,float(configured[name].get("beta",0)),float(configured[name].get("lambda",0)))
  family=0 if name.startswith("original") or "original" in name else 1
  try:beta=float(name.rsplit("_",1)[1])
  except ValueError:beta=999
  return (family,beta,0)
 def key(name):
  d=reports[name]["aggregate"];g=d["geo_recall"];return (-g["50"]["1"]["hits"],-g["50"]["5"]["hits"],-g["50"]["10"]["hits"],-g["100"]["1"]["hits"],d["mean_top1_distance_m"],d["degraded_queries"],simplicity(name))
 selected=min(reports,key=key);document={"schema_version":"1.0","contract_version":"h26-h37-calibration-evaluation-v1","inputs":{"campaign_sha256":digest(a.campaign),"frozen_rankings_sha256":digest(a.rankings),"ranking_set_id":frozen["ranking_set_id"]},"protocol":{"references_loaded_only_after_all_variants_frozen":True,"distance_crs":"EPSG:25830","selection_rule":"lexicographic_geo50_at_1_5_10_then_geo100_at_1_then_mean_top1_then_degradations_then_simplicity","development_only":True},"variants":reports,"selection":{"selected_variant":selected,"selected_metrics":reports[selected]["aggregate"],"ranking_key":key(selected),"not_independent_test_result":True},"limitations":["remote_camera_reference_unknown_accuracy","development_set_policy_selection","single_image_per_candidate_slot","automatic_overlap_gate_not_human_review"]};a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({"selected":selected,"metrics":reports[selected]["aggregate"],"baseline":reports["baseline"]["aggregate"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
