#!/usr/bin/env python3
"""Adquiere delta Top-100 autorizado, reutilizando caché Top-50."""
from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.mapillary_cache import cache_from_env
from src.tfg_phase0.mapillary_coverage import MapillaryClient,canonical_bytes
from src.tfg_phase0.mapillary_visual_pilot import image_dimensions
PLAN_SHA="085ee9a8c21d79a60e1a9b5cecfde45a194a12bf00ab666f2a7b921e9a5b40dd"
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--authorization",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();plan=json.loads(a.plan.read_text());auth=json.loads(a.authorization.read_text())
 if digest(a.plan)!=PLAN_SHA or auth.get("plan_sha256")!=PLAN_SHA or not auth.get("approved") or not all(auth.get("operator_confirmations",{}).values()):raise PermissionError("plan/autorización Top-100 incompatible")
 cache=cache_from_env(ROOT);cache.prepare();client=MapillaryClient();client._require_token();rows=[];new_bytes=0
 for image_id in plan["asset_ids"]:
  meta=cache.metadata/f"{image_id}.json";status="reused_verified_cache"
  if meta.exists():record=json.loads(meta.read_text());path=cache.root/record["logical_path"]
  else:
   data=client.image_metadata(image_id,("id","creator","thumb_1024_url"));creator=data.get("creator") or {};username=creator.get("username") or creator.get("name");raw,_=client.download_bytes(data["thumb_1024_url"],max_bytes=8_000_000);new_bytes+=len(raw)
   if new_bytes>232_000_000:raise ValueError("presupuesto Top-100 excedido")
   media,w,h=image_dimensions(raw);suffix=".jpg" if media=="image/jpeg" else ".png";record=cache.store(image_id,raw,{"status":"downloaded","media_type":media,"downloaded_resolution":[w,h],"creator":creator,"creator_profile_url":f"https://www.mapillary.com/app/user/{username}","attribution":f"Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0","license":"CC-BY-SA-4.0","license_url":"https://creativecommons.org/licenses/by-sa/4.0/","source_page_url":f"https://www.mapillary.com/app/?pKey={image_id}","retention_deadline_utc":auth["retention_deadline_utc"]},suffix=suffix);path=cache.root/record["logical_path"];status="downloaded"
  if not path.exists() or digest(path)!=record["sha256"]:raise ValueError("asset Top-100 sin integridad")
  cache.pin(image_id,"h26-h37-top100-8b-v1");rows.append({**record,"acquisition_status":status,"logical_path":os.path.relpath(path.resolve(),a.output.parent.resolve())})
 doc={"schema_version":"1.0","contract_version":"h26-h37-top100-assets-v1","plan_id":plan["plan_id"],"plan_sha256":PLAN_SHA,"authorization_sha256":digest(a.authorization),"assets":rows,"summary":{"assets":len(rows),"downloaded":sum(r["acquisition_status"]=="downloaded" for r in rows),"reused":sum(r["acquisition_status"]=="reused_verified_cache" for r in rows),"new_bytes":new_bytes},"protocol":{"reference_images_excluded":True,"reference_sequences_excluded":True,"test_partition_accessed":False}};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b"\n");print(json.dumps(doc["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
