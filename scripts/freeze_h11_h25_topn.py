#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
from src.tfg_phase0.topn_reserve import canonical_bytes,freeze_topn,validate_top10_prefix
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--old-top10',type=Path,required=True);p.add_argument('--clip-weights',type=Path,required=True);p.add_argument('--cvg-utils-sha256',required=True);p.add_argument('--top-k',type=int,choices=(10,20,50,100,200,500),default=100);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();plan=json.loads(a.plan.read_text());old=json.loads(a.old_top10.read_text());model,galleries=load_runtime_config(ROOT/'config/madrid_f46_retriever.json',project_root=ROOT,cvg_utils_sha256=a.cvg_utils_sha256,clip_weights_path=a.clip_weights);retriever=CrossText2LocRetriever.load(model_config=model,gallery_configs=galleries,region_config=ROOT/'config/madrid.yaml',deep_validate_visual_assets=False)
 try:doc=freeze_topn(plan,retriever,top_k=a.top_k,plan_sha256=sha(a.plan))
 finally:retriever.close()
 prefix=validate_top10_prefix(doc,old)
 if not prefix['exact_prefix_match']:raise RuntimeError(f'prefijo Top-10 cambió: {prefix}')
 a.output_root.mkdir(parents=True,exist_ok=True);rankings_path=a.output_root/'rankings.json'
 payload=canonical_bytes(doc)+b'\n'
 if rankings_path.exists() and rankings_path.read_bytes()!=payload:raise RuntimeError('se rechaza sobrescribir una reserva diferente')
 rankings_path.write_bytes(payload);manifest={'schema_version':'1.0','contract_version':'h11-h25-topn-manifest-v1','reserve_id':doc['reserve_id'],'artifacts':{'plan':{'logical_path':str(a.plan.resolve().relative_to(ROOT)),'sha256':sha(a.plan)},'old_top10':{'logical_path':str(a.old_top10.resolve().relative_to(ROOT)),'sha256':sha(a.old_top10)},'rankings':{'logical_path':str(rankings_path.resolve().relative_to(ROOT)),'sha256':sha(rankings_path)}},'prefix_validation':prefix};manifest_path=a.output_root/'manifest.json';manifest_payload=canonical_bytes(manifest)+b'\n'
 if manifest_path.exists() and manifest_path.read_bytes()!=manifest_payload:raise RuntimeError('se rechaza sobrescribir un manifest diferente')
 manifest_path.write_bytes(manifest_payload);print(json.dumps({'reserve_id':doc['reserve_id'],'rows':len(doc['rows']),'top_k':a.top_k,'prefix':prefix},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
