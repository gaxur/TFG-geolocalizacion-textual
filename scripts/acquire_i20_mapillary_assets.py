#!/usr/bin/env python3
"""Adquiere el lote Mapillary I20 congelado, sin selección adaptativa ni modelos."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,time
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.i20_remote_acquisition import dhash,validate_shortlist
from src.tfg_phase0.mapillary_cache import cache_from_env
from src.tfg_phase0.mapillary_coverage import MapillaryClient,MapillaryClientConfig,canonical_bytes
from src.tfg_phase0.mapillary_visual_pilot import image_dimensions
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def main():
 p=argparse.ArgumentParser();p.add_argument('--selection',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();selection=json.loads(a.selection.read_text());authorization=json.loads(a.authorization.read_text());validate_shortlist(selection)
 if not authorization.get('approved') or not authorization.get('terms_reviewed') or authorization.get('selection_sha256')!=digest(a.selection) or authorization.get('maximum_downloads')!=60 or not authorization.get('retention_deadline_utc'):raise ValueError('autorización I20 ausente o incompatible')
 max_total=int(authorization['maximum_total_bytes']);max_asset=int(authorization['maximum_asset_bytes']);client=MapillaryClient(config=MapillaryClientConfig(request_interval_seconds=.25));cache=cache_from_env(ROOT);cache.prepare();assets_dir=a.output_root/'images';assets_dir.mkdir(parents=True,exist_ok=True);records=[];total=0;attempted=0;succeeded=0
 for slot in selection['slots']:
  for item in slot['ordered_candidates']:
   image_id=item['image_id'];attempted+=1;role=item['role'];source_page=f'https://www.mapillary.com/app/?pKey={image_id}';base={"observation_id":slot['observation_id'],"slot_order":item['order'],"role":role,"provider_record_id":image_id,"sequence_id":item['sequence_id'],"license_identifier":"CC-BY-SA-4.0","license_url":"https://creativecommons.org/licenses/by-sa/4.0/","source_page_url":source_page,"retention_deadline_utc":authorization['retention_deadline_utc']}
   try:
    metadata=client.image_metadata(image_id,('id','creator','computed_geometry','captured_at','computed_compass_angle','sequence','camera_type','width','height','quality_score','thumb_1024_url'))
    if str(metadata.get('id'))!=image_id or not metadata.get('thumb_1024_url'):raise ValueError('metadata Mapillary no corresponde al ID')
    metadata_sha=hashlib.sha256(canonical_bytes(metadata)).hexdigest();creator=metadata.get('creator') or {};username=creator.get('username') or 'unknown-contributor';cached=next(iter(cache.images.glob(f'{image_id}.*')),None)
    if cached:
     raw=cached.read_bytes();status='reused_verified_cache';media,width,height=image_dimensions(raw)
    else:
     if total>=max_total:raise ValueError('presupuesto total agotado antes de descargar')
     raw,declared=client.download_bytes(metadata['thumb_1024_url'],max_bytes=min(max_asset,max_total-total));media,width,height=image_dimensions(raw)
     if declared and declared not in {media,'application/octet-stream'}:raise ValueError('MIME declarado no coincide')
     suffix='.jpg' if media=='image/jpeg' else '.png';cache.store(image_id,raw,{"status":"downloaded","media_type":media,"downloaded_resolution":[width,height],"creator":creator,"creator_profile_url":f'https://www.mapillary.com/app/user/{username}',"attribution":f'Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0',"license":"CC-BY-SA-4.0","license_url":"https://creativecommons.org/licenses/by-sa/4.0/","source_page_url":source_page,"retention_deadline_utc":authorization['retention_deadline_utc'],"metadata_sha256":metadata_sha},suffix=suffix);status='downloaded'
    total+=len(raw)
    if total>max_total:raise ValueError('presupuesto total excedido')
    suffix='.jpg' if media=='image/jpeg' else '.png';destination=assets_dir/f'{slot["observation_id"]}-{role}-{image_id}{suffix}';tmp=destination.with_suffix(destination.suffix+'.tmp');tmp.write_bytes(raw);os.replace(tmp,destination);sha=hashlib.sha256(raw).hexdigest();ph=dhash(destination);succeeded+=1
    records.append({**base,"status":status,"logical_path":str(destination.relative_to(a.output_root)),"sha256":sha,"perceptual_hash":ph,"perceptual_hash_algorithm":"dhash-9x8-grayscale-v1","size_bytes":len(raw),"media_type":media,"width_px":width,"height_px":height,"creator":creator,"attribution":f'Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0',"metadata_sha256":metadata_sha,"acquired_at_utc":now()})
   except Exception as error:
    records.append({**base,"status":"failed","logical_path":None,"sha256":None,"perceptual_hash":None,"perceptual_hash_algorithm":"dhash-9x8-grayscale-v1","size_bytes":None,"media_type":None,"width_px":None,"height_px":None,"creator":None,"attribution":None,"metadata_sha256":None,"acquired_at_utc":None,"error_type":type(error).__name__})
   time.sleep(.25)
 document={"schema_version":"1.0","contract_version":"i20-remote-asset-manifest-v1","manifest_id":"","status":"acquired" if succeeded==60 else "partially_acquired" if succeeded else "blocked","provider":"mapillary","selection_sha256":digest(a.selection),"authorization_sha256":digest(a.authorization),"budget":{"maximum_downloads":60,"maximum_total_bytes":max_total,"downloads_attempted":attempted,"downloads_succeeded":succeeded,"bytes_acquired":total},"assets":records};identity={k:v for k,v in document.items() if k!='manifest_id'};document['manifest_id']='i20-remote-assets-sha256-'+hashlib.sha256(canonical_bytes(identity)).hexdigest();(a.output_root/'asset-manifest.json').write_bytes(canonical_bytes(document)+b'\n');print(json.dumps({"manifest_id":document['manifest_id'],"attempted":attempted,"succeeded":succeeded,"bytes":total,"new":sum(r['status']=='downloaded' for r in records),"reused":sum(r['status']=='reused_verified_cache' for r in records),"failed":sum(r['status']=='failed' for r in records)},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
