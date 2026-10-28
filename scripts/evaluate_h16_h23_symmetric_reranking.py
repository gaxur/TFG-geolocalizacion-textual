#!/usr/bin/env python3
"""Evalúa post hoc baseline/asimétrico/simétrico en EPSG:25830."""

from __future__ import annotations
import argparse,hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830
from src.tfg_phase0.symmetric_visual_reranking import canonical_bytes,restore_baseline

def distance(ref,row):
 a=wgs84_to_epsg25830(ref["latitude"],ref["longitude"]);b=wgs84_to_epsg25830(row["latitude"],row["longitude"]);return ((a[0]-b[0])**2+(a[1]-b[1])**2)**.5
def metrics(ids,by,ref):
 d=[distance(ref,by[x]) for x in ids];return {"top1_distance_m":d[0],"geo_recall":{str(t):{str(k):min(d[:k])<=t for k in (1,5,10)} for t in (50,100)},"minimum_distance_m":{str(k):min(d[:k]) for k in (1,5,10)}}
def main():
 p=argparse.ArgumentParser();p.add_argument("--symmetric",type=Path,required=True);p.add_argument("--asymmetric-geography",type=Path,required=True);p.add_argument("--dataset",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();sym=json.loads(a.symmetric.read_text());asym=json.loads(a.asymmetric_geography.read_text());dataset=json.loads(a.dataset.read_text());refs={r["query_id"]:r["reference"] for r in dataset["observations"]};models={}
 for model,data in sym["models"].items():
  rows=[]
  for q in data["queries"]:
   art=q["reranking"];base=restore_baseline(art);by={r["candidate_id"]:r for r in base};baseline_ids=[r["candidate_id"] for r in base[:10]];final=art["final_top10_candidate_ids"];bm=metrics(baseline_ids,by,refs[q["query_id"]]);sm=metrics(final,by,refs[q["query_id"]]);entries=[op for op in art["operations"] if op["type"]=="enter_top10"];exits=[op for op in art["operations"] if op["type"]=="leave_top10"];rows.append({"query_id":q["query_id"],"baseline":bm,"symmetric":sm,"rank_changes":art["rank_changes"],"operations":art["operations"],"entry_distances":[{"candidate_id":op["candidate_id"],"distance_m":distance(refs[q["query_id"]],by[op["candidate_id"]])} for op in entries],"exit_distances":[{"candidate_id":op["candidate_id"],"distance_m":distance(refs[q["query_id"]],by[op["candidate_id"]])} for op in exits]})
  topb=[r["baseline"]["top1_distance_m"] for r in rows];tops=[r["symmetric"]["top1_distance_m"] for r in rows];models[model]={"rows":rows,"aggregate":{"mean_top1_distance_m":{"baseline":statistics.fmean(topb),"symmetric":statistics.fmean(tops)},"geo_recall":{str(t):{str(k):{"baseline_hits":sum(r["baseline"]["geo_recall"][str(t)][str(k)] for r in rows),"symmetric_hits":sum(r["symmetric"]["geo_recall"][str(t)][str(k)] for r in rows),"total":len(rows)} for k in (1,5,10)} for t in (50,100)},"top10_entries":sum(op["type"]=="enter_top10" for r in rows for op in r["operations"])}}
 doc={"schema_version":"1.0","contract_version":"h16-h23-symmetric-partial-geography-v1","inputs":{"symmetric_sha256":hashlib.sha256(a.symmetric.read_bytes()).hexdigest(),"asymmetric_geography_sha256":hashlib.sha256(a.asymmetric_geography.read_bytes()).hexdigest(),"dataset_sha256":hashlib.sha256(a.dataset.read_bytes()).hexdigest()},"protocol":{"references_loaded_only_after_symmetric_artifact":True,"distance_crs":"EPSG:25830","availability_conditioned_counterfactual":True},"asymmetric_reference":asym["models"],"models":models,"limitations":["partial_unbalanced_coverage","two_retrospective_queries","not_complete_top50"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b"\n");print(json.dumps({m:d["aggregate"] for m,d in models.items()},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
