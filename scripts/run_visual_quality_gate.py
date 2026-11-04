#!/usr/bin/env python3
"""Ejecuta quality gate local tras autorización; no realiza claims ni reranking."""
from __future__ import annotations
import argparse,hashlib,json,resource,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.qwen_visual_quality_verifier import LocalQwenVisualQualityVerifier
from src.tfg_phase0.visual_quality_gate import ManifestAssetResolver,refresh_run_id,run_quality_replacement,validate_policy,validate_reserves,canonical_bytes
MODEL_FILES={"model-00001-of-00004.safetensors":(4902275944,"d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa"),"model-00002-of-00004.safetensors":(4915962496,"8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5"),"model-00003-of-00004.safetensors":(4999831048,"83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192"),"model-00004-of-00004.safetensors":(2716270024,"0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5")}
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  while chunk:=stream.read(8*1024*1024):h.update(chunk)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--reserves',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--policy',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--model-path',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--quality-cache',type=Path);a=p.parse_args();plan=json.loads(a.reserves.read_text());reserves=plan.get('reserves',plan);assets_doc=json.loads(a.assets.read_text());policy=json.loads(a.policy.read_text());auth=json.loads(a.authorization.read_text());validate_policy(policy);validate_reserves(reserves)
 if not auth.get('approved') or not auth.get('gpu_authorized') or auth.get('policy_sha256')!=digest(a.policy) or auth.get('reserves_sha256')!=digest(a.reserves) or auth.get('assets_sha256')!=digest(a.assets):raise ValueError('autorización GPU/calidad ausente o incompatible')
 if policy.get('status')!='authorized_for_real_execution' or not policy.get('enabled'):raise ValueError('política real no habilitada')
 for name,(size,sha) in MODEL_FILES.items():
  path=a.model_path/name
  if path.stat().st_size!=size or digest(path)!=sha:raise ValueError(f'peso inválido: {name}')
 assets={str(row.get('image_id',row.get('provider_record_id'))):row for row in assets_doc['assets'] if row.get('status') not in {'failed','missing'}};cache_doc=json.loads(a.quality_cache.read_text()) if a.quality_cache else {};quality_cache={row['quality_task_id']:row for row in cache_doc.get('records',[])}
 import torch
 torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();load_start=time.perf_counter();verifier=LocalQwenVisualQualityVerifier(model_path=a.model_path,metadata=policy['quality_model']);load_seconds=time.perf_counter()-load_start;started=time.perf_counter()
 try:result=run_quality_replacement(reserves=reserves,claims_by_candidate={},policy=policy,resolver=ManifestAssetResolver(assets,root=a.assets.parent),quality_verifier=verifier,claim_verifier=None,quality_cache=quality_cache,mode='offline')
 finally:verifier.close()
 result['resources'].update({'model_load_seconds':load_seconds,'execution_seconds':time.perf_counter()-started,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'cuda_peak_reserved_bytes':torch.cuda.max_memory_reserved(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'authorization_sha256':digest(a.authorization),'policy_sha256':digest(a.policy),'reserves_sha256':digest(a.reserves),'assets_sha256':digest(a.assets)});result['run_id']=refresh_run_id(result);finalize_json_atomic(output_path=a.output,document=result);print(json.dumps(result['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
