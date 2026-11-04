#!/usr/bin/env python3
"""Ejecuta el inventario Commons metadata-only autorizado, reanudable por target."""
from __future__ import annotations
import argparse,hashlib,json,time,sys
from urllib.error import HTTPError
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.commons_inventory import build_query,fetch_metadata,freeze_inventory
PLAN_SHA="a2190cb0d6b1fdcd329018f301871dd86d08765bcd90dfce4683dda2499aac0e"
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def key(item):return f"{item['query_id']}|{item['target'].get('wikidata_id') or item['target'].get('label')}"
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--authorization",type=Path,required=True);p.add_argument("--raw-dir",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();plan=json.load(open(a.plan));auth=json.load(open(a.authorization))
 if digest(a.plan)!=PLAN_SHA or auth.get("plan_sha256")!=PLAN_SHA or not auth.get("approved") or not all(auth.get("operator_confirmations",{}).values()):raise PermissionError("autorización Commons incompatible")
 if len(plan["queries"])>33 or plan["policy"]["download_images"]:raise ValueError("scope Commons inválido")
 a.raw_dir.mkdir(parents=True,exist_ok=True);responses={}
 for index,item in enumerate(plan["queries"]):
  target=item["target"];record_key=key(item);path=a.raw_dir/f"{index:02d}-{item['query_id']}.json"
  if path.exists():response=json.load(open(path))
  else:
   url=build_query(wikidata_id=target.get("wikidata_id"),label=target.get("label"),limit=10);response=None
   for attempt,delay in enumerate((10,20,40,60),1):
    try:response=fetch_metadata(url);break
    except HTTPError as error:
     if error.code not in {429,503} or attempt==4:raise
     retry=error.headers.get("Retry-After") if error.headers else None;time.sleep(min(120,max(delay,int(retry) if retry and retry.isdigit() else delay)))
   path.write_text(json.dumps({"query_key":record_key,"request_url":url,"response":response},ensure_ascii=False,sort_keys=True,indent=2)+"\n");time.sleep(1.0)
  if "response" in response:response=response["response"]
  responses[record_key]=response
 inventory=freeze_inventory(plan,responses);inventory["authorization_sha256"]=digest(a.authorization);inventory["raw_responses"]=[{"logical_path":str(path),"sha256":digest(path),"size_bytes":path.stat().st_size} for path in sorted(a.raw_dir.glob("*.json"))];a.output.write_text(json.dumps(inventory,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps(inventory["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
