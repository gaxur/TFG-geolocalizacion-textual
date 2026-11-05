#!/usr/bin/env python3
"""Adquiere una foto Mapillary de Plaza Mayor sin modelos, rankings ni GT."""
from __future__ import annotations
import argparse,hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json
from src.tfg_phase0.f4_evaluation import haversine_m
from src.tfg_phase0.mapillary_coverage import MapillaryClient,MapillaryClientConfig

BBOX={"west":-3.7082,"south":40.4147,"east":-3.7064,"north":40.4161}
CENTER=(40.41545,-3.7074)
FORBIDDEN_PARTS=("h26-h37","h38-h61","h26-h61","remote-h26-h61")

def dotenv_token(path:Path):
    for line in path.read_text().splitlines() if path.is_file() else ():
        value=line.strip()
        if value and not value.startswith('#') and '=' in value:
            key,raw=value.split('=',1)
            if key.strip()=='MAPILLARY_ACCESS_TOKEN':return raw.strip().strip('"').strip("'")
    return None

def collect_ids(value,result:set[str]):
    if isinstance(value,dict):
        for key,nested in value.items():
            if key in {'image_id','source_id'} and isinstance(nested,(str,int)):result.add(str(nested))
            else:collect_ids(nested,result)
    elif isinstance(value,list):
        for nested in value:collect_ids(nested,result)

def historical_ids():
    ids=set();sources=[];roots=(ROOT/'results/generated/mapillary',ROOT/'results/generated/visual-quality-gate-v1')
    for root in roots:
        for pattern in ('**/asset-manifest.json','**/photo-manifest.json'):
            for path in root.glob(pattern):
                relative=str(path.relative_to(ROOT)).casefold()
                if any(part in relative for part in FORBIDDEN_PARTS):continue
                try:document=json.loads(path.read_text())
                except (OSError,json.JSONDecodeError):continue
                before=len(ids);collect_ids(document,ids)
                if len(ids)>before:sources.append({"logical_path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    return ids,sources

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();output=a.output_root.resolve()
    if output.exists():raise ValueError('output-root ya existe')
    destination=ROOT/'data/madrid/observer_view_authorized'
    if output.parent!=destination.resolve():raise ValueError('output-root debe estar bajo data/madrid/observer_view_authorized')
    token=os.environ.get('MAPILLARY_ACCESS_TOKEN') or dotenv_token(ROOT/'.env')
    if not token:raise RuntimeError('MAPILLARY_ACCESS_TOKEN no está configurado')
    client=MapillaryClient(token,config=MapillaryClientConfig(page_limit=200,max_pages=3,request_interval_seconds=.2));inventory=client.inventory(BBOX,original_bbox=BBOX)
    excluded,sources=historical_ids();eligible=[]
    for row in inventory['images']:
        if row['image_id'] in excluded:continue
        distance=haversine_m(CENTER[0],CENTER[1],row['latitude'],row['longitude']);camera=row.get('camera_type') or ''
        eligible.append((0 if camera=='perspective' else 1,distance,-(row.get('quality_score') or 0),-((row.get('width_px') or 0)*(row.get('height_px') or 0)),row['image_id'],row))
    if not eligible:raise RuntimeError('no hay imágenes elegibles fuera de colecciones históricas')
    eligible.sort(key=lambda value:value[:5]);selected=eligible[0][5];image_id=selected['image_id'];metadata=client.image_metadata(image_id,('id','creator','captured_at','sequence','camera_type','width','height','quality_score','thumb_2048_url'))
    if str(metadata.get('id'))!=image_id or not metadata.get('thumb_2048_url'):raise RuntimeError('metadata seleccionada incompleta')
    payload,media_type=client.download_bytes(metadata['thumb_2048_url'],max_bytes=8_000_000);suffix='.jpg' if media_type in {None,'image/jpeg'} else '.png' if media_type=='image/png' else '.webp' if media_type=='image/webp' else None
    if suffix is None:raise RuntimeError('tipo de imagen Mapillary no permitido')
    output.mkdir(parents=False);image_path=output/f'mapillary-{image_id}{suffix}';image_path.write_bytes(payload)
    with Image.open(image_path) as image:image.verify();fmt=image.format;width,height=image.size
    sha=hashlib.sha256(payload).hexdigest();creator=metadata.get('creator') or {};username=creator.get('username') if isinstance(creator,dict) else None;captured=metadata.get('captured_at');captured_utc=datetime.fromtimestamp(captured/1000,tz=timezone.utc).isoformat().replace('+00:00','Z') if isinstance(captured,(int,float)) else None;downloaded=datetime.now(timezone.utc).isoformat().replace('+00:00','Z');app_url=f'https://www.mapillary.com/app/?focus=photo&pKey={image_id}'
    report={"schema_version":"1.0","contract_version":"mapillary-observer-image-preparation-v1","status":"MAPILLARY_OBSERVER_IMAGE_PREPARED","selection":{"target":"Plaza Mayor, Madrid, España","bbox_wgs84":BBOX,"center_used_only_for_target_proximity":{"latitude":CENTER[0],"longitude":CENTER[1]},"criterion":"non_historical_then_perspective_then_target_center_distance_then_quality_then_resolution_then_image_id","ground_truth_used":False,"ct2l_used":False,"rankings_used":False,"models_used":False,"pixels_used_for_selection":False,"inventory_count":inventory['image_count'],"historical_ids_excluded":len(excluded),"eligible_count":len(eligible)},"image":{"image_id":image_id,"logical_path":image_path.name,"sha256":sha,"size_bytes":len(payload),"media_type":media_type,"format":fmt,"width_px":width,"height_px":height,"camera_type":metadata.get('camera_type'),"quality_score":metadata.get('quality_score'),"sequence_id":str(metadata['sequence']) if metadata.get('sequence') is not None else None,"captured_at_utc":captured_utc,"downloaded_at_utc":downloaded,"author":username,"provider":"Mapillary","provenance_url":app_url,"license":"CC-BY-SA-4.0","license_url":"https://creativecommons.org/licenses/by-sa/4.0/","attribution":f'Mapillary image {image_id} by {username}, licensed under CC BY-SA 4.0' if username else f'Mapillary image {image_id}, author not returned, licensed under CC BY-SA 4.0'},"provenance":{"api":"Mapillary API v4","api_documentation":"https://www.mapillary.com/developer/api-documentation/","license_statement":"https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data","application_terms_review":"operator_confirmation_pending","download_mechanism":"official thumb_2048_url returned by image metadata; URL not persisted"},"exclusion":{"forbidden_sets_opened":False,"h26_h37_used":False,"h38_h61_used":False,"historical_photo_manifest_sources":sources,"selected_id_in_historical_photo_manifests":False,"scope":"local photo manifests only; not proof against unknown external collections"},"observer_view":{"real_street_level_candidate":metadata.get('camera_type')=='perspective',"eligible_for_operator_review":True,"authorized":False,"observer_relation":"pending_operator_decision","session_id":"dialogue-session-v2-sha256-eb52dc47db05b82a40c368fd570f8b2f87729c4a15fa9d01e4cb93fd702862a1","intent_family":"square"},"manifest":{"created":False,"reason":"operator must confirm application terms, visual suitability, observer relation, retention and authorization_id"}}
    atomic_write_json(output/'preparation.json',report);atomic_write_json(output/'inventory-metadata.json',{**inventory,"images":[{key:value for key,value in row.items() if key not in {'latitude','longitude'}} for row in inventory['images']]});print(json.dumps({'status':report['status'],'image_id':image_id,'logical_path':str(image_path),'sha256':sha}));return 0
if __name__=='__main__':raise SystemExit(main())
