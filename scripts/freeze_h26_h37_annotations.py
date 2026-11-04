#!/usr/bin/env python3
"""Congela técnicamente anotaciones aprobadas sin inventar fecha humana."""
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def observation_hash(row):
 payload=json.loads(json.dumps(row));payload["freeze"]["canonical_sha256"]=None;payload["freeze"]["frozen_at_utc"]=None;payload["lifecycle_status"]="approved"
 return hashlib.sha256(canonical(payload)).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--input",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();document=json.loads(a.input.read_text());rows=document["observations"]
 if [r["query_id"] for r in rows]!=[f"H{i:02d}" for i in range(26,38)]:raise ValueError("freeze exige H26-H37 completos y ordenados")
 if any(r["lifecycle_status"]!="approved" or r["human_review"]["status"]!="approved" or r["human_review"]["primary_reviewer"]!="marcos" or r["human_review"]["rankings_seen"] or r["human_review"]["vlm_outputs_seen"] for r in rows):raise ValueError("anotación no aprobada o contaminada")
 frozen_at=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
 for row in rows:
  row["freeze"]["canonical_sha256"]=observation_hash(row);row["freeze"]["frozen_at_utc"]=frozen_at;row["lifecycle_status"]="frozen"
 document["freeze"]={"frozen_at_utc":frozen_at,"source_sha256":hashlib.sha256(a.input.read_bytes()).hexdigest(),"observation_hash_method":"sha256_canonical_approved_observation_excluding_technical_freeze_fields","rankings_executed_before_freeze":False,"vlm_outputs_seen_before_freeze":False,"human_overlap_review_status":"pending"}
 a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({"frozen":len(rows),"frozen_at_utc":frozen_at,"sha256":hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
