#!/usr/bin/env python3
"""Preflight CPU del quality gate; no importa Torch, no abre red ni ejecuta VLM."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_quality_gate import quality_schema,quality_task_id,validate_policy,validate_reserves,canonical_bytes
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--reserves',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--policy',type=Path,required=True);p.add_argument('--quality-cache',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();plan=json.loads(a.reserves.read_text());assets_doc=json.loads(a.assets.read_text());policy=json.loads(a.policy.read_text());validate_policy(policy);reserves=plan.get('reserves',plan);validate_reserves(reserves);assets={str(row.get('image_id',row.get('provider_record_id'))):row for row in assets_doc['assets'] if row.get('status') not in {'failed','missing'}};cache=json.loads(a.quality_cache.read_text()) if a.quality_cache else {};cache_by={row['quality_task_id']:row for row in cache.get('records',[])};model=policy['quality_model'];physical={}
 for row in reserves:
  asset=assets.get(str(row['image_id']))
  if not asset or not asset.get('sha256'):continue
  task=quality_task_id(image_sha256=asset['sha256'],model=model);physical.setdefault(task,{'quality_task_id':task,'image_sha256':asset['sha256'],'image_ids':[],'cache_hit':task in cache_by});physical[task]['image_ids'].append(str(row['image_id']))
 calls=sum(not row['cache_hit'] for row in physical.values());limits=policy['limits'];estimated=98+calls*1.38 if model['model_id'].endswith('8B-Instruct') else 25+calls*.46;document={'schema_version':'1.0','contract_version':'visual-quality-preflight-v1','status':'blocked_real_execution_requires_authorization' if policy.get('status')!='authorized_for_real_execution' else 'ready','inputs':{'reserves_sha256':digest(a.reserves),'assets_sha256':digest(a.assets),'policy_sha256':digest(a.policy),'quality_cache_sha256':digest(a.quality_cache) if a.quality_cache else None},'protocol':{'gpu_opened':False,'network_opened':False,'model_loaded':False,'ground_truth_used':False,'rerank_feedback_used':False},'budget':{'logical_reserves':len(reserves),'physical_unique_images':len(physical),'quality_cache_hits':sum(row['cache_hit'] for row in physical.values()),'quality_calls_pending':calls,'maximum_quality_vlm_calls':limits['maximum_quality_vlm_calls'],'maximum_claim_vlm_calls':limits['maximum_claim_vlm_calls'],'maximum_downloaded_bytes':limits['maximum_downloaded_bytes'],'estimated_quality_seconds_including_load':estimated},'schema_sha256':hashlib.sha256(canonical_bytes(quality_schema())).hexdigest(),'tasks':sorted(physical.values(),key=lambda row:row['quality_task_id'])};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(document)+b'\n');print(json.dumps(document['budget'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
