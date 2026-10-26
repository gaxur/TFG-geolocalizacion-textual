#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import canonical_bytes,compact_atomic_verdict_schema,compact_atomic_verification_prompt,parse_compact_atomic_verdict,VisualRerankingError
MODEL_ID='Qwen/Qwen3-VL-2B-Instruct';REVISION='89644892e4d85e24eaac8bacfd4f463576704203';WEIGHT_SHA='7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0';WEIGHT_SIZE=4255140312
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description='Inferencia atómica de validación sin etiquetas humanas');p.add_argument('--fixture',type=Path,required=True);p.add_argument('--photo-manifest',type=Path,required=True);p.add_argument('--model-path',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-new-tokens',type=int,default=192);p.add_argument('--guided-json',action='store_true');a=p.parse_args();f=json.loads(a.fixture.read_text());photos_doc=json.loads(a.photo_manifest.read_text());weight=a.model_path/'model.safetensors'
 if weight.stat().st_size!=WEIGHT_SIZE or digest(weight)!=WEIGHT_SHA:raise ValueError('peso VLM incorrecto')
 claims={c['claim_id']:c for g in f['claim_sets'] for c in g['claims']};photos={r['image_id']:r for r in photos_doc['photos'] if r['status']=='downloaded'};jobs=[]
 for expected in f['annotation_template']['records']:
  claim=claims[expected['claim_id']];photo=photos[expected['image_id']];path=(a.photo_manifest.parent/photo['logical_path']).resolve()
  if digest(path)!=photo['sha256']:raise ValueError('hash de imagen inválido')
  jobs.append((expected,claim,path))
 if len(jobs)!=60:raise ValueError('se esperaban 60 jobs')
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();t0=time.perf_counter();processor=AutoProcessor.from_pretrained(a.model_path,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(a.model_path,local_files_only=True,dtype=torch.bfloat16,device_map='cuda',attn_implementation='sdpa');model.eval();load=time.perf_counter()-t0;records=[];start=time.perf_counter();prefix_allowed_tokens_fn=None
 if a.guided_json:
  import transformers.tokenization_utils as tokenization_utils
  if not hasattr(tokenization_utils,'PreTrainedTokenizerBase'):
   from transformers import PreTrainedTokenizerBase
   tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
  from lmformatenforcer import JsonSchemaParser
  from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
  prefix_allowed_tokens_fn=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(compact_atomic_verdict_schema()))
 try:
  for expected,claim,path in jobs:
   if claim['requires_orientation']:
    records.append({**{k:expected[k] for k in ('candidate_id','image_id','claim_id')},'status':'policy_unverifiable','raw_output':None,'parsed_verdict':{'claim_id':claim['claim_id'],'candidate_id':expected['candidate_id'],'image_id':expected['image_id'],'verdict':'unverifiable','observed_evidence':None,'ocr_text':None,'orientation_comparable':False,'limitations':['orientation_not_comparable']},'error':None,'inference_seconds':0.0});continue
   prompt=compact_atomic_verification_prompt(claim,orientation_comparable=False);image=Image.open(path).convert('RGB');inputs=processor.apply_chat_template([{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':prompt}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device);raw=None;t=time.perf_counter()
   try:
    with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=a.max_new_tokens,do_sample=False,prefix_allowed_tokens_fn=prefix_allowed_tokens_fn)
    raw=processor.batch_decode(generated[:,inputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];parsed=parse_compact_atomic_verdict(raw,claim,candidate_id=expected['candidate_id'],image_id=expected['image_id'],orientation_comparable_allowed=False);status='valid';error=None
   except Exception as e:parsed=None;status='contract_rejected' if isinstance(e,VisualRerankingError) else 'generation_failed';error=str(e)
   records.append({**{k:expected[k] for k in ('candidate_id','image_id','claim_id')},'status':status,'raw_output':raw,'parsed_verdict':parsed,'error':error,'inference_seconds':time.perf_counter()-t})
 finally:del model;torch.cuda.empty_cache()
 version='v3-guided' if a.guided_json else 'v2-compact';doc={'schema_version':'1.0','contract_version':f'visual-atomic-validation-run-{version}','inputs':{'fixture_sha256':digest(a.fixture),'photo_manifest_sha256':digest(a.photo_manifest)},'model':{'model_id':MODEL_ID,'revision':REVISION,'weight_sha256':WEIGHT_SHA},'generation':{'prompt_version':f'visual-atomic-compact-{version}','one_claim_one_image':True,'ids_generated_by_model':False,'guided_json':a.guided_json,'max_new_tokens':a.max_new_tokens,'do_sample':False,'json_repair':False},'protocol':{'human_annotations_loaded_during_inference':False,'ground_truth_used':False,'orientation_comparable':False,'reranking_performed':False},'resources':{'model_load_seconds':load,'execution_seconds':time.perf_counter()-start,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'cuda_peak_reserved_bytes':torch.cuda.max_memory_reserved(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024},'records':records,'summary':{'jobs':len(records),'valid':sum(r['status']=='valid' for r in records),'policy_unverifiable':sum(r['status']=='policy_unverifiable' for r in records),'failed':sum(r['status'] not in {'valid','policy_unverifiable'} for r in records)}};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps(doc['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
