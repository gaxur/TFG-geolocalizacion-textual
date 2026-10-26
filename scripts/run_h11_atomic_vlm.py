#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import atomic_verification_prompt,canonical_bytes,parse_atomic_verdict,VisualRerankingError
MODEL_ID='Qwen/Qwen3-VL-2B-Instruct';REVISION='89644892e4d85e24eaac8bacfd4f463576704203';WEIGHT_SHA='7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0';WEIGHT_SIZE=4255140312
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description='Ejecutor atómico H11 sin GT');p.add_argument('--fixture',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--reviewed-claims',type=Path,required=True);p.add_argument('--model-path',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-new-tokens',type=int,default=192);a=p.parse_args();f=json.loads(a.fixture.read_text());assets_doc=json.loads(a.assets.read_text());review=json.loads(a.reviewed_claims.read_text())
 if review.get('contract_version')!='visual-reviewed-claim-set-v1' or review.get('fixture_id')!=f['fixture_id'] or review.get('review_status')!='complete':raise ValueError('claims H11 no revisados completamente')
 source={c['claim_id']:c for c in f['claims']['claims']};approved=[];reviewed_ids=[]
 for r in review['records']:
  c=r['claim'];
  if c['claim_id'] not in source or c!=source[c['claim_id']]:raise ValueError('claim revisado modificado o ajeno')
  if r.get('decision') not in {'approved','rejected'} or not r.get('reviewer') or not r.get('reviewed_at_utc'):raise ValueError('decisión de claim incompleta')
  reviewed_ids.append(c['claim_id'])
  if r['decision']=='approved':approved.append(c)
 if len(reviewed_ids)!=len(set(reviewed_ids)) or set(reviewed_ids)!=set(source):raise ValueError('revisión no cubre exactamente todos los claims H11')
 if not approved:raise ValueError('ningún claim aprobado')
 weight=a.model_path/'model.safetensors'
 if weight.stat().st_size!=WEIGHT_SIZE or digest(weight)!=WEIGHT_SHA:raise ValueError('peso VLM incorrecto')
 assets={r['image_id']:r for r in assets_doc['assets'] if r['status'] in {'downloaded','reused'}}
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 load=time.perf_counter();torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();processor=AutoProcessor.from_pretrained(a.model_path,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(a.model_path,local_files_only=True,dtype=torch.bfloat16,device_map='cuda',attn_implementation='sdpa');model.eval();load_seconds=time.perf_counter()-load;records=[];start=time.perf_counter()
 try:
  for association in f['associations']:
   asset=assets[association['image_id']];path=(a.assets.parent/asset['logical_path']).resolve();
   if digest(path)!=asset['sha256']:raise ValueError('hash de asset cambió')
   for claim in approved:
    if claim['requires_orientation'] and not association['orientation_comparable']:
     records.append({'candidate_id':association['candidate_id'],'image_id':association['image_id'],'claim_id':claim['claim_id'],'status':'policy_unverifiable','parsed_verdict':None,'error':'orientation_not_comparable'});continue
    prompt=atomic_verification_prompt(claim,candidate_id=association['candidate_id'],image_id=association['image_id'],orientation_comparable=association['orientation_comparable']);image=Image.open(path).convert('RGB');messages=[{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':prompt}]}];inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device);t=time.perf_counter()
    raw=None
    try:
     with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=a.max_new_tokens,do_sample=False)
     raw=processor.batch_decode(generated[:,inputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];parsed=parse_atomic_verdict(raw,claim,candidate_id=association['candidate_id'],image_id=association['image_id'],orientation_comparable_allowed=association['orientation_comparable']);status='valid';error=None
    except Exception as e:parsed=None;status='contract_rejected' if isinstance(e,VisualRerankingError) else 'generation_failed';error=str(e)
    records.append({'candidate_id':association['candidate_id'],'image_id':association['image_id'],'claim_id':claim['claim_id'],'status':status,'raw_output':raw,'parsed_verdict':parsed,'error':error,'inference_seconds':time.perf_counter()-t})
 finally:del model;torch.cuda.empty_cache()
 doc={'schema_version':'1.0','contract_version':'h11-visual-atomic-run-v1','fixture_id':f['fixture_id'],'approved_claims':approved,'inputs':{'fixture_sha256':digest(a.fixture),'asset_manifest_sha256':digest(a.assets),'reviewed_claims_sha256':digest(a.reviewed_claims)},'model':{'model_id':MODEL_ID,'revision':REVISION,'weight_sha256':WEIGHT_SHA},'generation':{'one_claim_one_image':True,'do_sample':False,'max_new_tokens':a.max_new_tokens,'json_repair':False},'protocol':{'ground_truth_used':False,'baseline_rank_sent_to_vlm':False,'coordinates_sent_to_vlm':False,'reranking_performed':False},'resources':{'model_load_seconds':load_seconds,'execution_seconds':time.perf_counter()-start,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024},'records':records,'summary':{'jobs':len(records),'valid':sum(r['status']=='valid' for r in records),'policy_unverifiable':sum(r['status']=='policy_unverifiable' for r in records),'failed':sum(r['status'] not in {'valid','policy_unverifiable'} for r in records)}};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps(doc['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
