#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import canonical_bytes,parse_verdict_only,verdict_only_prompt,verdict_only_schema
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS

MODEL_FILES={
'qwen3-vl-2b':{'model.safetensors':(4255140312,'7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0')},
'qwen3-vl-8b':{'model-00001-of-00004.safetensors':(4902275944,'d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa'),'model-00002-of-00004.safetensors':(4915962496,'8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5'),'model-00003-of-00004.safetensors':(4999831048,'83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192'),'model-00004-of-00004.safetensors':(2716270024,'0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5')},}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description='Ejecutor VLM V4 genérico posterior a CT2L, sin GT');p.add_argument('--fixture',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--reviewed-claims',type=Path,required=True);p.add_argument('--model-key',choices=sorted(MODEL_FILES),required=True);p.add_argument('--model-path',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();f=json.loads(a.fixture.read_text());assets_doc=json.loads(a.assets.read_text());review=json.loads(a.reviewed_claims.read_text());config=SUPPORTED_LOCAL_MODELS[a.model_key]
 for name,(size,sha) in MODEL_FILES[a.model_key].items():q=a.model_path/name;assert q.stat().st_size==size and digest(q)==sha
 if review.get('fixture_id')!=f['fixture_id'] or review.get('review_status')!='complete':raise ValueError('claims revisados incompatibles')
 source={c['claim_id']:c for c in f['claims']['claims']};seen=[];approved=[]
 for row in review['records']:
  claim=row['claim'];assert claim==source[claim['claim_id']] and row['decision'] in {'approved','rejected'};seen.append(claim['claim_id']);
  if row['decision']=='approved':approved.append(claim)
 if len(seen)!=len(set(seen)) or set(seen)!=set(source):raise ValueError('revisión incompleta o duplicada')
 assets={r['image_id']:r for r in assets_doc['assets'] if r['status'] in {'downloaded','reused'}};jobs=[]
 for association in f['associations']:
  asset=assets[association['image_id']];path=(a.assets.parent/asset['logical_path']).resolve();assert digest(path)==asset['sha256']
  for claim in approved:jobs.append((association,claim,path,asset['sha256']))
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,'PreTrainedTokenizerBase'):
  from transformers import PreTrainedTokenizerBase;tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 from lmformatenforcer import JsonSchemaParser
 from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
 torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();load_start=time.perf_counter();processor=AutoProcessor.from_pretrained(a.model_path,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(a.model_path,local_files_only=True,dtype=torch.bfloat16,device_map='cuda',attn_implementation='sdpa');model.eval();load=time.perf_counter()-load_start;prefix=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(verdict_only_schema()));records=[];start=time.perf_counter()
 try:
  for association,claim,path,image_sha in jobs:
   base={'candidate_id':association['candidate_id'],'image_id':association['image_id'],'claim_id':claim['claim_id'],'image_sha256':image_sha,'sequence_id':association.get('sequence_id')}
   if claim['requires_orientation'] and not association['orientation_comparable']:
    records.append({**base,'status':'policy_unverifiable','verdict':'unverifiable','raw_output':None,'error':None,'inference_seconds':0.0});continue
   image=Image.open(path).convert('RGB');prompt=verdict_only_prompt(claim);inputs=processor.apply_chat_template([{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':prompt}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device);torch.cuda.synchronize();t=time.perf_counter();raw=None
   try:
    with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=24,do_sample=False,prefix_allowed_tokens_fn=prefix)
    torch.cuda.synchronize();raw=processor.batch_decode(generated[:,inputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];verdict=parse_verdict_only(raw);status='valid';error=None
   except Exception as e:verdict=None;status='invalid_output';error=str(e)
   records.append({**base,'status':status,'verdict':verdict,'raw_output':raw,'error':error,'inference_seconds':time.perf_counter()-t})
 finally:del model;torch.cuda.empty_cache()
 doc={'schema_version':'1.0','contract_version':'visual-fixture-run-v4','fixture_id':f['fixture_id'],'approved_claims':approved,'inputs':{'fixture_sha256':digest(a.fixture),'asset_manifest_sha256':digest(a.assets),'reviewed_claims_sha256':digest(a.reviewed_claims)},'model':{'model_key':a.model_key,'model_id':config['model_id'],'revision':config['revision'],'files':{n:{'size_bytes':s,'sha256':h} for n,(s,h) in MODEL_FILES[a.model_key].items()}},'generation':{'contract':'verdict_only_v4','schema':verdict_only_schema(),'do_sample':False,'max_new_tokens':24,'explanations_generated':False},'protocol':{'ground_truth_used':False,'baseline_rank_sent_to_vlm':False,'scores_sent_to_vlm':False,'coordinates_sent_to_vlm':False,'reranking_performed':False},'records':records,'resources':{'model_load_seconds':load,'execution_seconds':time.perf_counter()-start,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'cuda_peak_reserved_bytes':torch.cuda.max_memory_reserved(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024},'summary':{'jobs':len(records),'valid':sum(r['status']=='valid' for r in records),'policy_unverifiable':sum(r['status']=='policy_unverifiable' for r in records),'invalid':sum(r['status']=='invalid_output' for r in records),'verdicts':{v:sum(r['verdict']==v for r in records) for v in ('supported','contradicted','unverifiable')}}};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps(doc['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
