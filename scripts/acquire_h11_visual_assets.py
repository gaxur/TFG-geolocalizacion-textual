#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.mapillary_coverage import MapillaryClient,MapillaryCoverageError,canonical_bytes,sha256_bytes
from src.tfg_phase0.mapillary_visual_pilot import image_dimensions,reject_ground_truth

FIELDS=("id","creator","computed_geometry","captured_at","computed_compass_angle","sequence","camera_type","width","height","quality_score","thumb_1024_url")
def main():
 p=argparse.ArgumentParser(description='Adquiere assets únicos H11 ya planificados');p.add_argument('--fixture',type=Path,required=True);p.add_argument('--existing-manifest',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--max-new-downloads',type=int,default=43);p.add_argument('--max-total-bytes',type=int,default=400_000_000);p.add_argument('--confirm-terms-reviewed',action='store_true');a=p.parse_args()
 if not a.confirm_terms_reviewed:print('ERROR: confirme términos para este lote H11',file=sys.stderr);return 2
 fixture=json.loads(a.fixture.read_text());existing=json.loads(a.existing_manifest.read_text());reject_ground_truth(fixture,path='fixture');assets=fixture['assets'];old={r['image_id']:r for r in existing['photos'] if r['status']=='downloaded'};new=[i for i in assets if i not in old]
 if len(new)>a.max_new_downloads or not 1<=a.max_new_downloads<=50 or a.max_total_bytes>400_000_000:raise ValueError('presupuesto H11 excedido')
 a.output_root.mkdir(parents=True,exist_ok=True);image_root=a.output_root/'images';image_root.mkdir(exist_ok=True);records=[];total=0;client=MapillaryClient()
 for image_id in assets:
  if image_id in old:
   source=old[image_id];path=a.existing_manifest.parent/source['logical_path'];raw=path.read_bytes()
   if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('asset reutilizado con hash inválido')
   records.append({"image_id":image_id,"status":"reused","source_manifest_sha256":hashlib.sha256(a.existing_manifest.read_bytes()).hexdigest(),"logical_path":os.path.relpath(path.resolve(),a.output_root.resolve()),"sha256":source['sha256'],"size_bytes":source['size_bytes'],"media_type":source['media_type'],"downloaded_resolution":source['downloaded_resolution'],"creator":source['creator'],"creator_profile_url":source['creator_profile_url'],"attribution":source['attribution'],"license":"CC-BY-SA-4.0","license_url":source['license_url'],"source_page_url":source['source_page_url'],"modifications":source['modifications']});continue
  try:
   metadata=client.image_metadata(image_id,FIELDS);creator=metadata.get('creator') or {};username=creator.get('username') or creator.get('name')
   if not username:raise MapillaryCoverageError('autor ausente')
   raw,response_type=client.download_bytes(metadata['thumb_1024_url'],max_bytes=8_000_000);media,w,h=image_dimensions(raw);total+=len(raw)
   if total>a.max_total_bytes:raise ValueError('presupuesto total excedido')
   ext='.jpg' if media=='image/jpeg' else '.png';path=image_root/f'{image_id}{ext}';tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(raw);tmp.replace(path);license_url='https://creativecommons.org/licenses/by-sa/4.0/'
   records.append({"image_id":image_id,"status":"downloaded","logical_path":f'images/{path.name}',"sha256":sha256_bytes(raw),"size_bytes":len(raw),"media_type":media,"downloaded_resolution":[w,h],"source_resolution":[metadata.get('width'),metadata.get('height')],"captured_at":metadata.get('captured_at'),"camera_type":metadata.get('camera_type'),"creator":creator,"creator_profile_url":f'https://www.mapillary.com/app/user/{username}',"attribution":f'Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0',"license":"CC-BY-SA-4.0","license_url":license_url,"source_page_url":f'https://www.mapillary.com/app/?pKey={image_id}',"modifications":"Downloaded as a 1024 px thumbnail; no content edits by the TFG","acquired_at_utc":datetime.now(timezone.utc).isoformat().replace('+00:00','Z')})
  except MapillaryCoverageError as e:records.append({"image_id":image_id,"status":"failed","error":str(e)})
 manifest={"schema_version":"1.0","contract_version":"h11-visual-asset-manifest-v1","fixture_id":fixture['fixture_id'],"fixture_sha256":hashlib.sha256(a.fixture.read_bytes()).hexdigest(),"terms_review_confirmed_by_operator":True,"requested_unique_assets":len(assets),"new_download_budget":a.max_new_downloads,"downloaded_new":sum(r['status']=='downloaded' for r in records),"reused":sum(r['status']=='reused' for r in records),"failed":sum(r['status']=='failed' for r in records),"assets":records,"associations":fixture['associations'],"limitations":["proximity_does_not_prove_visibility","orientation_not_observer_orientation"]};(a.output_root/'asset-manifest.json').write_bytes(canonical_bytes(manifest)+b'\n');print(json.dumps({k:manifest[k] for k in ('requested_unique_assets','downloaded_new','reused','failed')},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
