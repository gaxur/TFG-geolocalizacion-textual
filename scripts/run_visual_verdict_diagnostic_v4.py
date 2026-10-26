#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import canonical_bytes,explanation_prompt,parse_verdict_only,verdict_only_prompt,verdict_only_schema,VisualRerankingError
MODELS={
'qwen3-vl-2b':{'model_id':'Qwen/Qwen3-VL-2B-Instruct','revision':'89644892e4d85e24eaac8bacfd4f463576704203','files':{'model.safetensors':(4255140312,'7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0')}},
'qwen3-vl-8b':{'model_id':'Qwen/Qwen3-VL-8B-Instruct','revision':'0c351dd01ed87e9c1b53cbc748cba10e6187ff3b','files':{'model-00001-of-00004.safetensors':(4902275944,'d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa'),'model-00002-of-00004.safetensors':(4915962496,'8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5'),'model-00003-of-00004.safetensors':(4999831048,'83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192'),'model-00004-of-00004.safetensors':(2716270024,'0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5')}}}
DIAGNOSTIC_KEYS=(
('1210433070142949','visual-claim-sha256-42a062a28f4c00ee4620ea91b2825e3bbf7d9e81c0c4753b181ab4415229f885'),
('1210433070142949','visual-claim-sha256-3157440ceb96fe189bd07c11968ce1d018cd39e6b0323e64f350b5935ac021f2'),
('483221386454901','visual-claim-sha256-1d44203dc48aa80897d927703e6236df01a3b582dcbeaa6fa5a8b131dd741887'),
('1000448337748748','visual-claim-sha256-8f42d2e11de2eb6698a50342211eb22a2fb5a510135198769126cabd4eb7f447'),
('1467353800748949','visual-claim-sha256-6353708fd368ee1167379e58831d5c70ba0e37203d29b3869c77b287b33252ff'),
('174852081596618','visual-claim-sha256-17efed6620edd57a0fd055b330d89e293430c92566ed112bf2358add241381bc'),
('1401333830797121','visual-claim-sha256-42a062a28f4c00ee4620ea91b2825e3bbf7d9e81c0c4753b181ab4415229f885'),
('224548649040144','visual-claim-sha256-8f42d2e11de2eb6698a50342211eb22a2fb5a510135198769126cabd4eb7f447'),
('484760569616148','visual-claim-sha256-ab624b8414d875665f37e5fb371d8f9627b51d9fcb1dad16e3faed58f4b39037'),
('1210433070142949','visual-claim-sha256-6353708fd368ee1167379e58831d5c70ba0e37203d29b3869c77b287b33252ff'),
)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--photo-manifest',type=Path,required=True);p.add_argument('--model-key',choices=sorted(MODELS),default='qwen3-vl-2b');p.add_argument('--model-path',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--with-explanations',action='store_true');p.add_argument('--all-pairs',action='store_true');p.add_argument('--smoke-one',action='store_true');a=p.parse_args();f=json.loads(a.fixture.read_text());photos_doc=json.loads(a.photo_manifest.read_text());model_config=MODELS[a.model_key]
 for filename,(size,sha) in model_config['files'].items():
  weight=a.model_path/filename;assert weight.stat().st_size==size and digest(weight)==sha
 claims={c['claim_id']:c for g in f['claim_sets'] for c in g['claims']};photos={r['image_id']:r for r in photos_doc['photos'] if r['status']=='downloaded'};jobs=[]
 selected=[(r['candidate_id'],r['image_id'],r['claim_id']) for r in f['annotation_template']['records']] if a.all_pairs else [(next(r['candidate_id'] for r in f['annotation_template']['records'] if r['image_id']==image_id and r['claim_id']==claim_id),image_id,claim_id) for image_id,claim_id in DIAGNOSTIC_KEYS]
 if a.smoke_one:selected=selected[:1]
 for candidate_id,image_id,claim_id in selected:
  photo=photos[image_id];path=(a.photo_manifest.parent/photo['logical_path']).resolve();assert digest(path)==photo['sha256'];jobs.append((candidate_id,image_id,claims[claim_id],path))
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,'PreTrainedTokenizerBase'):
  from transformers import PreTrainedTokenizerBase;tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 from lmformatenforcer import JsonSchemaParser
 from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
 torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();t=time.perf_counter();processor=AutoProcessor.from_pretrained(a.model_path,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(a.model_path,local_files_only=True,dtype=torch.bfloat16,device_map='cuda',attn_implementation='sdpa');model.eval();load=time.perf_counter()-t;prefix=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(verdict_only_schema()));records=[];start=time.perf_counter()
 try:
  for candidate_id,image_id,claim,path in jobs:
   if claim['requires_orientation']:
    records.append({'candidate_id':candidate_id,'image_id':image_id,'claim_id':claim['claim_id'],'status':'policy_unverifiable','raw_verdict':None,'verdict':'unverifiable','error':None,'decision_seconds':0.0,'explanation_status':'not_requested','explanation':None,'explanation_seconds':0.0});continue
   image=Image.open(path).convert('RGB');prompt=verdict_only_prompt(claim);inputs=processor.apply_chat_template([{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':prompt}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device);t=time.perf_counter();raw=None
   try:
    with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=24,do_sample=False,prefix_allowed_tokens_fn=prefix)
    raw=processor.batch_decode(generated[:,inputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];verdict=parse_verdict_only(raw);status='valid';error=None
   except Exception as e:verdict=None;status='invalid';error=str(e)
   explanation=None;explanation_status='not_requested';explanation_seconds=0.0
   if a.with_explanations and verdict:
    eprompt=explanation_prompt(claim,verdict);einputs=processor.apply_chat_template([{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':eprompt}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device);et=time.perf_counter()
    try:
     with torch.inference_mode():egenerated=model.generate(**einputs,max_new_tokens=48,do_sample=False)
     explanation=processor.batch_decode(egenerated[:,einputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0].strip();explanation_status='valid' if explanation else 'invalid'
    except Exception as e:explanation_status='generation_failed';explanation=str(e)
    explanation_seconds=time.perf_counter()-et
   records.append({'candidate_id':candidate_id,'image_id':image_id,'claim_id':claim['claim_id'],'status':status,'raw_verdict':raw,'verdict':verdict,'error':error,'decision_seconds':time.perf_counter()-t-explanation_seconds,'explanation_status':explanation_status,'explanation':explanation,'explanation_seconds':explanation_seconds})
 finally:del model;torch.cuda.empty_cache()
 selection='smoke_one' if a.smoke_one else 'all_development_pairs' if a.all_pairs else 'fixed_balanced_development_subset';doc={'schema_version':'1.0','contract_version':'visual-verdict-diagnostic-v4','inputs':{'fixture_sha256':digest(a.fixture),'photo_manifest_sha256':digest(a.photo_manifest),'selection':selection},'model':{'model_key':a.model_key,'model_id':model_config['model_id'],'revision':model_config['revision'],'weight_files':{name:{'size_bytes':size,'sha256':sha} for name,(size,sha) in model_config['files'].items()}},'generation':{'decision_schema':verdict_only_schema(),'decision_max_new_tokens':24,'explanation_separate':a.with_explanations,'explanation_max_new_tokens':48,'do_sample':False,'guided_decision':True},'protocol':{'human_labels_used_only_for_subset_selection':not a.all_pairs and not a.smoke_one,'human_labels_sent_to_model':False,'ground_truth_used':False,'reranking_performed':False},'records':records,'resources':{'model_load_seconds':load,'execution_seconds':time.perf_counter()-start,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'cuda_peak_reserved_bytes':torch.cuda.max_memory_reserved(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024},'summary':{'jobs':len(records),'valid_decisions':sum(r['status'] in {'valid','policy_unverifiable'} for r in records),'model_decisions':sum(r['status']=='valid' for r in records),'policy_unverifiable':sum(r['status']=='policy_unverifiable' for r in records),'verdicts':{v:sum(r['verdict']==v for r in records) for v in ('supported','contradicted','unverifiable')}}};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps(doc['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
