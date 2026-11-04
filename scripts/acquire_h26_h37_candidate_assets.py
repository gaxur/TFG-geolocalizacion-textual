#!/usr/bin/env python3
"""Adquiere exactamente assets candidate-neutral de un plan H26-H37 autorizado."""
from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.mapillary_cache import cache_from_env
from src.tfg_phase0.mapillary_coverage import MapillaryClient,canonical_bytes
from src.tfg_phase0.mapillary_visual_pilot import image_dimensions
EXPECTED_PLAN_SHA="ef5417b75eac4cf68f2d214f5d9b0da74223252edad63179b2d97bc2b5a25748"
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--authorization",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 if digest(a.plan)!=EXPECTED_PLAN_SHA:raise ValueError("plan Top-50 incompatible")
 plan=json.loads(a.plan.read_text());auth=json.loads(a.authorization.read_text());confirm=auth.get("operator_confirmations",{});approved=auth.get("approved") and auth.get("terms_reviewed") and confirm and all(confirm.values()) and auth.get("frozen_inputs",{}).get("visual_plan_sha256")==EXPECTED_PLAN_SHA
 if not approved:raise PermissionError("autorización Top-50 incompleta")
 cache=cache_from_env(ROOT);cache.prepare();client=MapillaryClient();client._require_token();records=[];total_new=0
 for image_id in plan["asset_ids"]:
  meta=cache.metadata/f"{image_id}.json";acquisition="reused_verified_cache"
  if meta.exists():
   record=json.loads(meta.read_text());path=cache.root/record["logical_path"]
   if not path.exists() or digest(path)!=record["sha256"]:raise ValueError("caché sin integridad")
  else:
   data=client.image_metadata(image_id,("id","creator","thumb_1024_url"));creator=data.get("creator") or {};username=creator.get("username") or creator.get("name")
   if not username:raise ValueError("autor ausente")
   raw,_=client.download_bytes(data["thumb_1024_url"],max_bytes=8_000_000);total_new+=len(raw)
   if total_new>448_000_000:raise ValueError("presupuesto excedido")
   media,width,height=image_dimensions(raw);suffix=".jpg" if media=="image/jpeg" else ".png";record=cache.store(image_id,raw,{"status":"downloaded","media_type":media,"downloaded_resolution":[width,height],"creator":creator,"creator_profile_url":f"https://www.mapillary.com/app/user/{username}","attribution":f"Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0","license":"CC-BY-SA-4.0","license_url":"https://creativecommons.org/licenses/by-sa/4.0/","source_page_url":f"https://www.mapillary.com/app/?pKey={image_id}","retention_deadline_utc":auth["retention_deadline_utc"]},suffix=suffix);path=cache.root/record["logical_path"];acquisition="downloaded"
  cache.pin(image_id,"h26-h37-top50-calibration-v1");records.append({**record,"acquisition_status":acquisition,"logical_path":os.path.relpath(path.resolve(),a.output.parent.resolve())})
 doc={"schema_version":"1.0","contract_version":"h26-h37-candidate-assets-v1","plan_id":plan["plan_id"],"plan_sha256":EXPECTED_PLAN_SHA,"authorization_sha256":digest(a.authorization),"assets":records,"summary":{"assets":len(records),"downloaded":sum(r["acquisition_status"]=="downloaded" for r in records),"reused":sum(r["acquisition_status"]=="reused_verified_cache" for r in records),"new_bytes":total_new},"protocol":{"reference_images_excluded":True,"reference_sequences_excluded":True,"test_partition_accessed":False,"atomic_cache":True,"sha256_required":True}};a.output.parent.mkdir(parents=True,exist_ok=True);tmp=a.output.with_suffix(".tmp");tmp.write_bytes(canonical_bytes(doc)+b"\n");tmp.replace(a.output);print(json.dumps(doc["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
