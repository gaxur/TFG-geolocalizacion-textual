#!/usr/bin/env python3
"""Ejecuta I02-I04 v10 una vez, fail-fast, sin resume ni retries."""
from __future__ import annotations
import argparse,hashlib,importlib.metadata,importlib.util,json,resource,time
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import canonical_bytes
from src.tfg_phase0.bounded_annotation_pilot import PilotJob,TARGET_IDS,execute_bounded_pilot,validate_pilot_scope
from src.tfg_phase0.i20_assisted_annotation import annotation_evidence_draft_schema_v10,annotation_prompt_v10,cache_entry_id,content_id,materialize_annotation_evidence_draft,task_identity,validate_annotation_proposal_record
from src.tfg_phase0.xgrammar_guidance import build_transformers_logits_processor,build_xgrammar_profile,compile_json_schema,resolve_text_vocab_size
MODEL_FILES={"model-00001-of-00004.safetensors":(4902275944,"d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa"),"model-00002-of-00004.safetensors":(4915962496,"8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5"),"model-00003-of-00004.safetensors":(4999831048,"83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192"),"model-00004-of-00004.safetensors":(2716270024,"0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5")}
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  while chunk:=stream.read(8*1024*1024):h.update(chunk)
 return h.hexdigest()
def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def prepare_preflight(*,plan_path,authorization_path,annotation_fixture_path,scene_fixture_path,instructions_path,model_path,require_approval=True,verify_model_files=True):
 plan=json.loads(plan_path.read_text());auth=json.loads(authorization_path.read_text());fixture=json.loads(annotation_fixture_path.read_text());validate_pilot_scope(plan,auth)
 if require_approval and (not auth.get('approved') or not auth.get('gpu_authorized')):raise ValueError('autorización de piloto ausente')
 if auth.get('plan_id')!=plan.get('plan_id') or auth.get('plan_sha256')!=digest(plan_path):raise ValueError('autorización no vinculada al plan')
 runtime_root=plan_path.parent/plan['runtime_relative_path']
 if authorization_path.parent!=plan_path.parent or runtime_root.exists():raise ValueError('runtime o rutas del piloto incompatibles')
 checks={'pilot_runner_sha256':digest(Path(__file__)),'orchestrator_sha256':digest(ROOT/'src/tfg_phase0/bounded_annotation_pilot.py'),'validation_materializer_sha256':digest(ROOT/'src/tfg_phase0/i20_assisted_annotation.py'),'ledger_sha256':digest(ROOT/'src/tfg_phase0/immutable_attempt_ledger.py'),'guidance_sha256':digest(ROOT/'src/tfg_phase0/xgrammar_guidance.py')}
 if any(plan['generator'].get(key)!=value or auth.get(key)!=value for key,value in checks.items()):raise ValueError('código efectivo no coincide con plan')
 if digest(annotation_fixture_path)!=plan['source']['annotation_fixture_sha256'] or digest(scene_fixture_path)!=plan['source']['scene_fixture_sha256'] or digest(instructions_path)!=plan['source']['instructions_sha256']:raise ValueError('fixtures o instrucciones incompatibles')
 if hashlib.sha256(annotation_prompt_v10().encode()).hexdigest()!=plan['generator']['annotation_prompt_sha256'] or hashlib.sha256(canonical_bytes(annotation_evidence_draft_schema_v10())).hexdigest()!=plan['generator']['annotation_schema_sha256']:raise ValueError('prompt/schema v10 incompatibles')
 xspec=importlib.util.find_spec('xgrammar')
 if xspec is None or not xspec.submodule_search_locations:raise ValueError('XGrammar local ausente')
 xroot=Path(next(iter(xspec.submodule_search_locations)));xidentity={'xgrammar_version':importlib.metadata.version('xgrammar'),'xgrammar_bindings_sha256':digest(xroot/'libxgrammar_bindings.so'),'xgrammar_hf_adapter_sha256':digest(xroot/'contrib/hf.py')}
 if any(plan['generator'].get(key)!=value for key,value in xidentity.items()):raise ValueError('XGrammar incompatible')
 if verify_model_files:
  for name,(size,sha) in MODEL_FILES.items():
   path=model_path/name
   if path.stat().st_size!=size or digest(path)!=sha:raise ValueError(f'peso inválido: {name}')
 by={row['observation_id']:row for row in fixture['observations']};model={"model_id":plan['generator']['model_id'],"revision":plan['generator']['model_revision'],"weight_sha256":plan['generator']['weight_sha256'],"processor_policy":plan['generator']['processor_policy'],"decoding":plan['generator']['decoding']};jobs=[]
 for index,target in enumerate(TARGET_IDS):
  planned=plan['targets'][index]
  if planned.get('observation_id')!=target:raise ValueError('target del plan alterado')
  row=by[target];path=(annotation_fixture_path.parent/row['reference_asset_path']).resolve()
  if any(planned.get(key)!=row.get(key) for key in ('reference_asset_id','reference_asset_sha256','reference_asset_path')):raise ValueError(f'fixture/plan incompatibles: {target}')
  if not path.is_file() or path.is_symlink() or digest(path)!=row['reference_asset_sha256']:raise ValueError(f'imagen inválida: {target}')
  identity=task_identity(kind='annotation',target_id=target,image_sha256=[row['reference_asset_sha256']],model=model,prompt_sha256=plan['generator']['annotation_prompt_sha256'],schema_sha256=plan['generator']['annotation_schema_sha256'],instructions_sha256=plan['source']['instructions_sha256']);cid=cache_entry_id(identity);jobs.append(PilotJob(index,target,cid,identity,(row,path)))
 return {'plan':plan,'authorization':auth,'fixture':fixture,'model':model,'jobs':jobs,'runtime_root':runtime_root}
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--annotation-fixture',type=Path,required=True);p.add_argument('--scene-fixture',type=Path,required=True);p.add_argument('--instructions',type=Path,required=True);p.add_argument('--model-path',type=Path,required=True);a=p.parse_args();prepared=prepare_preflight(plan_path=a.plan,authorization_path=a.authorization,annotation_fixture_path=a.annotation_fixture,scene_fixture_path=a.scene_fixture,instructions_path=a.instructions,model_path=a.model_path);plan,auth,fixture,model,jobs,runtime_root=(prepared[key] for key in ('plan','authorization','fixture','model','jobs','runtime_root'))
 def load_runtime():
  import torch
  from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
  processor=AutoProcessor.from_pretrained(a.model_path,local_files_only=True);vlm=Qwen3VLForConditionalGeneration.from_pretrained(a.model_path,local_files_only=True,dtype=torch.bfloat16,device_map='cuda',attn_implementation='sdpa');vlm.eval();vocab=resolve_text_vocab_size(vlm.config,expected=plan['generator']['text_vocab_size']);eos=vlm.generation_config.eos_token_id;eos=[eos] if isinstance(eos,int) else list(eos or [])
  if eos!=plan['generator']['eos_token_ids']:raise ValueError('EOS incompatibles')
  profile=build_xgrammar_profile(tokenizer=processor.tokenizer,vocab_size=vocab,stop_token_ids=eos);compiled=compile_json_schema(profile,annotation_evidence_draft_schema_v10());return {'torch':torch,'processor':processor,'vlm':vlm,'compiled':compiled,'eos':eos}
 def generate(runtime,job):
  from PIL import Image
  row,path=job.payload;processor,vlm,torch=runtime['processor'],runtime['vlm'],runtime['torch'];content=[{'type':'image','image':Image.open(path).convert('RGB')},{'type':'text','text':annotation_prompt_v10()}];inputs=processor.apply_chat_template([{'role':'user','content':content}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(vlm.device);lp=build_transformers_logits_processor(runtime['compiled']);start=time.perf_counter()
  with torch.inference_mode():generated=vlm.generate(**inputs,max_new_tokens=2048,do_sample=False,logits_processor=[lp],eos_token_id=runtime['eos'],return_dict_in_generate=True)
  elapsed=time.perf_counter()-start;new=generated.sequences[:,inputs.input_ids.shape[1]:];ids=[int(x) for x in new[0].tolist()];raw=processor.batch_decode(new,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];last=ids[-1] if ids else None;return raw,{'generated_token_count':len(ids),'generated_token_ids':ids,'last_token_id':last,'terminated_by_eos':last in runtime['eos'],'reached_max_new_tokens':len(ids)==2048,'generation_seconds':elapsed,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'cuda_peak_reserved_bytes':torch.cuda.max_memory_reserved()}
 def build(job,raw,metadata):
  row,path=job.payload;draft=materialize_annotation_evidence_draft(json.loads(raw));base={'proposal_id':'','observation_id':row['observation_id'],'reference_asset_id':row['reference_asset_id'],'reference_asset_sha256':row['reference_asset_sha256'],'proposal_status':'proposed','ai_draft':draft,'generation':{'input_identity_sha256':hashlib.sha256(canonical_bytes(job.identity)).hexdigest(),'cache_entry_id':job.cache_entry_id,'raw_output_sha256':hashlib.sha256(raw.encode()).hexdigest(),'generated_at_utc':now(),'model_id':model['model_id'],'model_revision':model['revision']}};base['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',base,'proposal_id');validate_annotation_proposal_record(base,fixture_row=row);return {'query_id':None,'candidate_id':'annotation','image_id':job.target_id,'claim_id':job.cache_entry_id,'proposal':base}
 def release(runtime):
  del runtime['vlm'];runtime['torch'].cuda.empty_cache()
 execute_bounded_pilot(runtime_root=runtime_root,plan_id=plan['plan_id'],jobs=jobs,load_runtime=load_runtime,generate_raw=generate,parse_and_build=build,release_runtime=release,now=now);return 0
if __name__=='__main__':raise SystemExit(main())
