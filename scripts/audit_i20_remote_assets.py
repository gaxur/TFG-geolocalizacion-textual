#!/usr/bin/env python3
"""Audita assets I20, aplica reservas congeladas y prepara paquetes separados."""
from __future__ import annotations
import argparse,hashlib,json,math,shutil
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.i20_preparation import build_empty_annotation_package,build_empty_gt_package,canonical_bytes,content_id
from src.tfg_phase0.i20_remote_acquisition import dhash,hamming,projected_distance,validate_shortlist
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def main():
 p=argparse.ArgumentParser();p.add_argument('--selection',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--historical-manifest',type=Path,action='append',required=True);p.add_argument('--annotation-template',type=Path,required=True);p.add_argument('--gt-template',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();selection=load(a.selection);manifest=load(a.assets);validate_shortlist(selection);by={(r['observation_id'],r['slot_order']):r for r in manifest['assets']};historical_hash=set();historical_ph=set();historical_ids=set();historical_sources=[]
 for path in a.historical_manifest:
  document=load(path);rows=document.get('photos',document.get('assets',[]));available=0
  for row in rows:
   image_id=str(row.get('image_id'));historical_ids.add(image_id)
   if row.get('sha256'):historical_hash.add(row['sha256'])
   if row.get('perceptual_hash'):historical_ph.add(row['perceptual_hash'])
   logical=row.get('logical_path')
   if logical:
    image=(path.parent/logical).resolve()
    if image.is_file():
     available+=1
     if row.get('sha256') and digest(image)!=row['sha256']:raise ValueError(f'hash histórico inválido: {image_id}')
     historical_ph.add(dhash(image))
  historical_sources.append({'logical_path':str(path),'sha256':digest(path),'records':len(rows),'pixel_files_available':available})
 all_hash={};all_ph={};exact=[];near=[]
 for row in manifest['assets']:
  if row['status']=='failed':continue
  previous=all_hash.setdefault(row['sha256'],row['provider_record_id'])
  if previous!=row['provider_record_id']:exact.append([previous,row['provider_record_id']])
  if row['provider_record_id'] in historical_ids:exact.append(['H01-H37-id',row['provider_record_id']])
  if row['sha256'] in historical_hash:exact.append(['H01-H37-sha256',row['provider_record_id']])
  for old_id,old_ph in all_ph.items():
   distance=hamming(row['perceptual_hash'],old_ph)
   if distance<=6:near.append({'left':old_id,'right':row['provider_record_id'],'hamming_distance':distance,'scope':'i20_internal'})
  minimum_historical=min((hamming(row['perceptual_hash'],ph) for ph in historical_ph),default=64)
  if minimum_historical<=6:near.append({'left':'H01-H37','right':row['provider_record_id'],'hamming_distance':minimum_historical,'scope':'historical'})
  all_ph[row['provider_record_id']]=row['perceptual_hash']
 invalid_ids={item for pair in exact for item in pair if item!='H01-H37'}|{row['right'] for row in near}
 observations=[];scene_queue=[];selected_rows=[]
 for slot in selection['slots']:
  candidates=[]
  for item in slot['ordered_candidates']:
   asset=by[(slot['observation_id'],item['order'])];reasons=[]
   if asset['status']=='failed':reasons.append('acquisition_failed')
   if asset['provider_record_id'] in invalid_ids:reasons.append('exact_or_perceptual_duplicate')
   candidates.append({'order':item['order'],'provider_record_id':asset['provider_record_id'],'technical_pass':not reasons,'reasons':reasons,'asset':asset,'metadata':item})
  selected=next((row for row in candidates if row['technical_pass']),None)
  if selected:
   asset=selected['asset'];metadata=selected['metadata'];selected_rows.append((slot,selected));state='PENDING_BLIND_EXCLUSION';scene_queue.append({'observation_id':slot['observation_id'],'reference_asset_path':asset['logical_path'],'provider_record_id':asset['provider_record_id'],'block_id':slot['block_id'],'sequence_id':asset['sequence_id'],'review_required':True,'review_fields':['same_scene_as_H01_H37','distinctive_objects_shared','field_of_view_overlap','same_place_different_frame'],'decision':None})
   observations.append({'observation_id':slot['observation_id'],'state':state,'selected_order':selected['order'],'selected_provider_record_id':asset['provider_record_id'],'block_id':slot['block_id'],'sequence_id':asset['sequence_id'],'technical_quality':'pass','blind_exclusion':'pending_custodian','human_annotation':'not_started','human_review':'not_started','eligible':False,'limitations':['provider_camera_coordinate_unknown_accuracy','scene_overlap_human_review_pending','blind_holdout_exclusion_pending','human_annotation_pending']})
  else:observations.append({'observation_id':slot['observation_id'],'state':'EXCLUDED','selected_order':None,'selected_provider_record_id':None,'block_id':slot['block_id'],'sequence_id':None,'technical_quality':'failed','blind_exclusion':'not_submitted','human_annotation':'not_started','human_review':'not_started','eligible':False,'limitations':['all_frozen_candidates_failed']})
 annotation=load(a.annotation_template);annotation['status']='template_not_collected';annotation['source_ledger']=None;annotation['observations']=[];annotation['package_id']='';annotation['package_id']=content_id('i20-annotation-package-sha256-',annotation,'package_id')
 gt=load(a.gt_template);gt['status']='review_open';gt['references']=[]
 geo=[]
 for slot,selected in selected_rows:
  metadata=selected['metadata'];asset=selected['asset'];geo.append({'observation_id':slot['observation_id'],'provider':'mapillary','provider_record_id':asset['provider_record_id'],'sequence_id':asset['sequence_id'],'captured_at_epoch_ms':metadata.get('captured_at_epoch_ms'),'latitude':metadata['latitude'],'longitude':metadata['longitude'],'coordinate_source':metadata['coordinate_source'],'position_role':'provider_reported_camera_position','reported_accuracy_m':None,'uncertainty_status':'unknown','orientation_degrees':metadata.get('orientation_degrees'),'orientation_source':metadata.get('orientation_source'),'orientation_meaning':'camera_heading_not_body_heading','width_px':asset['width_px'],'height_px':asset['height_px'],'quality_score':metadata.get('quality_score'),'metadata_sha256':asset['metadata_sha256'],'limitations':['provider_accuracy_not_reported','camera_heading_reliability_unknown']})
 gt_doc={'schema_version':'1.0','contract_version':'i20-remote-geographic-package-v1','status':'quality_checked_approximate_reference','annotation_content_seen':False,'predictions_seen':False,'references':geo}
 annotations_dir=a.output_root/'annotation-package';annotations_dir.mkdir(exist_ok=True);references_dir=annotations_dir/'references';references_dir.mkdir(exist_ok=True)
 for slot,selected in selected_rows:
  asset=selected['asset'];source=a.output_root/asset['logical_path'];destination=references_dir/source.name
  if not destination.exists():shutil.copyfile(source,destination)
 (annotations_dir/'observations.json').write_bytes(canonical_bytes(annotation)+b'\n');(a.output_root/'geographic-package.json').write_bytes(canonical_bytes(gt_doc)+b'\n');(a.output_root/'observation-status.json').write_bytes(canonical_bytes({'schema_version':'1.0','contract_version':'i20-observation-status-v1','allowed_states':['DISCOVERED','ACQUIRED','QUALITY_CHECKED','PENDING_BLIND_EXCLUSION','PENDING_HUMAN_ANNOTATION','PENDING_HUMAN_REVIEW','ELIGIBLE','EXCLUDED'],'observations':observations})+b'\n');(a.output_root/'duplicate-audit.json').write_bytes(canonical_bytes({'schema_version':'1.0','contract_version':'i20-duplicate-audit-v1','algorithm':'dhash-9x8-grayscale-v1','maximum_hamming_distance':6,'exact_duplicates':exact,'near_duplicates':near,'historical_sources':historical_sources,'historical_ids':len(historical_ids),'historical_exact_hashes':len(historical_hash),'historical_perceptual_hashes':len(historical_ph),'historical_comparison_scope':'H01-H37 explicit accessible manifests and bytes only','holdout_compared':False})+b'\n');(a.output_root/'scene-review-queue.json').write_bytes(canonical_bytes({'schema_version':'1.0','contract_version':'i20-scene-review-queue-v1','status':'pending_human_review','records':scene_queue})+b'\n');print(json.dumps({'selected':len(selected_rows),'excluded':sum(r['state']=='EXCLUDED' for r in observations),'pending_blind':sum(r['state']=='PENDING_BLIND_EXCLUSION' for r in observations),'exact_duplicates':len(exact),'near_duplicates':len(near),'blocks':len({r['block_id'] for r in observations if r['state']!='EXCLUDED'}),'eligible':0,'historical_ids':len(historical_ids),'historical_perceptual_hashes':len(historical_ph)},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
