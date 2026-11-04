#!/usr/bin/env python3
"""Abre referencias development solo después del freeze Top-100."""
from __future__ import annotations
import argparse,hashlib,json,statistics
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--rankings",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();campaign=json.loads(a.campaign.read_text());rankings=json.loads(a.rankings.read_text())
 if rankings["inputs"]["campaign_sha256"]!=digest(a.campaign) or rankings["inputs"]["ground_truth_used"] is not False:raise ValueError("rankings no congelados antes de referencias")
 refs={r["query_id"]:r["reference_asset"]["position"] for r in campaign["observations"]};rows=[]
 for query,ranking in zip(rankings["queries"],rankings["rankings"],strict=True):
  query_id=query["query_id"];ref=refs[query_id];rx,ry=wgs84_to_epsg25830(ref["reported_latitude"],ref["reported_longitude"]);candidates=[]
  for candidate in ranking["results"]:
   x,y=wgs84_to_epsg25830(candidate["latitude"],candidate["longitude"]);candidates.append({"rank":candidate["rank"],"candidate_id":candidate["candidate_id"],"distance_m":((x-rx)**2+(y-ry)**2)**.5})
  nearest=min(candidates,key=lambda r:(r["distance_m"],r["rank"]));rows.append({"query_id":query_id,"nearest_rank_top100":nearest["rank"],"nearest_distance_top100_m":nearest["distance_m"],"minimum_top50_m":min(r["distance_m"] for r in candidates[:50]),"minimum_top100_m":nearest["distance_m"],"oracle":{"top50":{"50":min(r["distance_m"] for r in candidates[:50])<=50,"100":min(r["distance_m"] for r in candidates[:50])<=100},"top100":{"50":nearest["distance_m"]<=50,"100":nearest["distance_m"]<=100}}})
 document={"schema_version":"1.0","contract_version":"h26-h37-recoverability-v1","inputs":{"campaign_sha256":digest(a.campaign),"rankings_sha256":digest(a.rankings),"ranking_set_id":rankings["ranking_set_id"]},"protocol":{"references_loaded_only_after_top100_freeze":True,"distance_crs":"EPSG:25830","oracle_is_candidate_set_upper_bound_only":True},"rows":rows,"aggregate":{"queries":len(rows),"oracle_hits":{"top50":{"50":sum(r["oracle"]["top50"]["50"] for r in rows),"100":sum(r["oracle"]["top50"]["100"] for r in rows)},"top100":{"50":sum(r["oracle"]["top100"]["50"] for r in rows),"100":sum(r["oracle"]["top100"]["100"] for r in rows)}},"mean_minimum_distance_m":{"top50":statistics.fmean(r["minimum_top50_m"] for r in rows),"top100":statistics.fmean(r["minimum_top100_m"] for r in rows)}}}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps(document["aggregate"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
