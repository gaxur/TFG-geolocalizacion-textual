#!/usr/bin/env python3
"""Genera propuestas I20 asistidas tras autorización; no materializa anotaciones humanas."""
from __future__ import annotations
import argparse,hashlib,importlib.metadata,importlib.util,json,resource,time
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob,finalize_json_atomic,run_resumable
from src.tfg_phase0.i20_assisted_annotation import annotation_evidence_draft_schema_v10,annotation_prompt_v10,cache_entry_id,canonical_bytes,content_id,materialize_annotation_evidence_draft,scene_draft_schema,scene_prompt,task_identity,validate_annotation_proposal_record,validate_annotation_proposals,validate_plan,validate_scene_proposal_record,validate_scene_proposals
from src.tfg_phase0.immutable_attempt_ledger import ImmutableAttemptLedger,execute_immutable_attempt
from src.tfg_phase0.xgrammar_guidance import build_transformers_logits_processor,build_xgrammar_profile,compile_json_schema,resolve_text_vocab_size
MODEL_FILES={"model-00001-of-00004.safetensors":(4902275944,"d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa"),"model-00002-of-00004.safetensors":(4915962496,"8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5"),"model-00003-of-00004.safetensors":(4999831048,"83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192"),"model-00004-of-00004.safetensors":(2716270024,"0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5")}
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  while chunk:=stream.read(8*1024*1024):h.update(chunk)
 return h.hexdigest()
def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def selected_job_orders(plan,*,scene_probe=False,annotation_probe=False):
 if scene_probe and annotation_probe:raise ValueError('modos de sonda mutuamente excluyentes')
 if annotation_probe:return [],plan['jobs']['annotation_order'][:1]
 if scene_probe:return plan['jobs']['scene_order'][:1],[]
 return plan['jobs']['scene_order'],plan['jobs']['annotation_order']
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--annotation-fixture',type=Path,required=True);p.add_argument('--scene-fixture',type=Path,required=True);p.add_argument('--instructions',type=Path,required=True);p.add_argument('--model-path',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);probe=p.add_mutually_exclusive_group();probe.add_argument('--probe-first-scene-only',action='store_true');probe.add_argument('--probe-first-annotation-only',action='store_true');a=p.parse_args();plan=json.loads(a.plan.read_text());auth=json.loads(a.authorization.read_text());annotation=json.loads(a.annotation_fixture.read_text());scene=json.loads(a.scene_fixture.read_text());validate_plan(plan,annotation_fixture=annotation,scene_fixture=scene)
 effective={'scene_prompt_sha256':hashlib.sha256(scene_prompt().encode()).hexdigest(),'annotation_prompt_sha256':hashlib.sha256(annotation_prompt_v10().encode()).hexdigest(),'scene_schema_sha256':hashlib.sha256(canonical_bytes(scene_draft_schema())).hexdigest(),'annotation_schema_sha256':hashlib.sha256(canonical_bytes(annotation_evidence_draft_schema_v10())).hexdigest()}
 if any(plan['generator'].get(key)!=value for key,value in effective.items()) or plan['source'].get('instructions_sha256')!=digest(a.instructions):raise ValueError('plan no coincide con prompts, schemas o instrucciones efectivos')
 validation_sha=digest(ROOT/'src/tfg_phase0/i20_assisted_annotation.py');dependencies={'validation_code_sha256':validation_sha,'materializer_code_sha256':validation_sha,'ledger_code_sha256':digest(ROOT/'src/tfg_phase0/immutable_attempt_ledger.py'),'guidance_code_sha256':digest(ROOT/'src/tfg_phase0/xgrammar_guidance.py')}
 if any(plan['generator'].get(key)!=value or auth.get(key)!=value for key,value in dependencies.items()):raise ValueError('plan no coincide con dependencias operativas efectivas')
 xgrammar_spec=importlib.util.find_spec('xgrammar')
 if xgrammar_spec is None or not xgrammar_spec.submodule_search_locations:raise ValueError('XGrammar local no disponible')
 xgrammar_root=Path(next(iter(xgrammar_spec.submodule_search_locations)));xgrammar_identity={'xgrammar_version':importlib.metadata.version('xgrammar'),'xgrammar_bindings_sha256':digest(xgrammar_root/'libxgrammar_bindings.so'),'xgrammar_hf_adapter_sha256':digest(xgrammar_root/'contrib/hf.py')}
 if any(plan['generator'].get(key)!=value or auth.get(key)!=value for key,value in xgrammar_identity.items()):raise ValueError('plan no coincide con XGrammar efectivo')
 forbidden_permissions=('network_permitted','downloads_permitted','gt_permitted','rankings_permitted','osm_permitted','h38_h61_permitted','ct2l_permitted','claims_permitted','reranking_permitted','training_permitted','fine_tuning_permitted')
 common_authorization=(auth.get('approved') is True and auth.get('gpu_authorized') is True and auth.get('plan_id')==plan['plan_id'] and auth.get('plan_sha256')==digest(a.plan) and auth.get('annotation_fixture_sha256')==digest(a.annotation_fixture) and auth.get('scene_fixture_sha256')==digest(a.scene_fixture) and auth.get('instructions_sha256')==digest(a.instructions) and auth.get('scene_prompt_sha256')==effective['scene_prompt_sha256'] and auth.get('annotation_prompt_sha256')==effective['annotation_prompt_sha256'] and auth.get('scene_schema_sha256')==effective['scene_schema_sha256'] and auth.get('annotation_schema_sha256')==effective['annotation_schema_sha256'] and auth.get('model_id')==plan['generator']['model_id'] and auth.get('model_revision')==plan['generator']['model_revision'] and auth.get('weight_sha256')==plan['generator']['weight_sha256'] and auth.get('historical_proposals_completed')==0 and auth.get('human_review_required') is True and all(auth.get(key) is False for key in forbidden_permissions))
 runner_sha=digest(Path(__file__))
 runner_matches=plan.get('generator',{}).get('runner_sha256')==runner_sha and auth.get('runner_sha256')==runner_sha
 probe_authorization=(a.probe_first_scene_only and auth.get('contract_version')=='i20-assisted-retry-authorization-v4' and runner_matches and auth.get('requested_probe_calls')==1 and auth.get('maximum_scene_calls')==1 and auth.get('maximum_annotation_calls')==0 and auth.get('maximum_total_future_calls')==1)
 annotation_probe_authorization=(a.probe_first_annotation_only and auth.get('contract_version')=='i20-assisted-retry-authorization-v10' and runner_matches and auth.get('structured_engine')=='xgrammar-0.2.1' and auth.get('text_vocab_size')==plan['generator'].get('text_vocab_size')==151936 and auth.get('eos_token_ids')==plan['generator'].get('eos_token_ids')==[151645,151643] and auth.get('probe_kind')=='annotation' and auth.get('probe_target_id')==plan['jobs']['annotation_order'][0] and auth.get('requested_probe_calls')==1 and auth.get('maximum_scene_calls')==0 and auth.get('maximum_annotation_calls')==1 and auth.get('maximum_total_future_calls')==1)
 campaign_authorization=(not a.probe_first_scene_only and not a.probe_first_annotation_only and auth.get('contract_version')=='i20-assisted-retry-authorization-v2' and auth.get('historical_calls_attempted')==1 and auth.get('replacement_calls_requested')==1 and auth.get('maximum_scene_calls')==12 and auth.get('maximum_annotation_calls')==20 and auth.get('maximum_total_future_calls')==32)
 authorization_matches=common_authorization and (probe_authorization or annotation_probe_authorization or campaign_authorization)
 if not authorization_matches:raise ValueError('autorización asistida ausente o incompatible')
 for name,(size,sha) in MODEL_FILES.items():
  path=a.model_path/name
  if path.stat().st_size!=size or digest(path)!=sha:raise ValueError(f'peso inválido: {name}')
 fixture_root=a.annotation_fixture.parent;by_obs={row['observation_id']:row for row in annotation['observations']};by_obs_sha={key:value['reference_asset_sha256'] for key,value in by_obs.items()};model={"model_id":plan['generator']['model_id'],"revision":plan['generator']['model_revision'],"weight_sha256":plan['generator']['weight_sha256'],"processor_policy":plan['generator']['processor_policy'],"decoding":plan['generator']['decoding']};instructions_sha=plan['source']['instructions_sha256'];scene_jobs=[];annotation_jobs=[]
 selected_scene_ids,annotation_order=selected_job_orders(plan,scene_probe=a.probe_first_scene_only,annotation_probe=a.probe_first_annotation_only)
 if selected_scene_ids:
  scene_by_id={row['pair_id']:row for row in scene['records']};scene_rows=[scene_by_id[pair_id] for pair_id in selected_scene_ids]
  for row in scene_rows:
   paths=[(a.scene_fixture.parent/row['left_reference_path']).resolve(),(a.scene_fixture.parent/row['right_reference_path']).resolve()];hashes=[by_obs[row['left_observation_id']]['reference_asset_sha256'],by_obs[row['right_observation_id']]['reference_asset_sha256']]
   if any(digest(path)!=sha for path,sha in zip(paths,hashes,strict=True)):raise ValueError('hash de imagen escena inválido')
   identity=task_identity(kind='scene_pair',target_id=row['pair_id'],image_sha256=hashes,model=model,prompt_sha256=plan['generator']['scene_prompt_sha256'],schema_sha256=plan['generator']['scene_schema_sha256'],instructions_sha256=instructions_sha);cache_id=cache_entry_id(identity);scene_jobs.append(PlannedJob((None,'scene',row['pair_id'],cache_id),identity,(row,paths,hashes,cache_id),True))
 for observation_id in annotation_order:
  row=by_obs[observation_id];path=(fixture_root/row['reference_asset_path']).resolve();sha=row['reference_asset_sha256']
  if digest(path)!=sha:raise ValueError('hash de imagen anotación inválido')
  identity=task_identity(kind='annotation',target_id=observation_id,image_sha256=[sha],model=model,prompt_sha256=plan['generator']['annotation_prompt_sha256'],schema_sha256=plan['generator']['annotation_schema_sha256'],instructions_sha256=instructions_sha)
  cache_id=cache_entry_id(identity)
  annotation_jobs.append(PlannedJob((None,'annotation',observation_id,cache_id),identity,(row,path,cache_id),True))
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,'PreTrainedTokenizerBase'):
  from transformers import PreTrainedTokenizerBase
  tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();load_started=time.perf_counter();processor=AutoProcessor.from_pretrained(a.model_path,local_files_only=True);vlm=Qwen3VLForConditionalGeneration.from_pretrained(a.model_path,local_files_only=True,dtype=torch.bfloat16,device_map='cuda',attn_implementation='sdpa');vlm.eval();model_load_seconds=time.perf_counter()-load_started;text_vocab_size=resolve_text_vocab_size(vlm.config,expected=plan['generator']['text_vocab_size']);configured_eos=vlm.generation_config.eos_token_id;configured_eos=[configured_eos] if isinstance(configured_eos,int) else list(configured_eos or []);expected_eos=plan['generator']['eos_token_ids'];
 if configured_eos!=expected_eos:raise ValueError(f'EOS del modelo incompatibles: {configured_eos} != {expected_eos}')
 xgrammar_profile=build_xgrammar_profile(tokenizer=processor.tokenizer,vocab_size=text_vocab_size,stop_token_ids=configured_eos);max_tokens=plan['generator']['decoding']['max_new_tokens'];execution_started=time.perf_counter()
 def generate(images,prompt,schema):
   content=[{'type':'image','image':Image.open(path).convert('RGB')} for path in images]+[{'type':'text','text':prompt}];inputs=processor.apply_chat_template([{'role':'user','content':content}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(vlm.device)
   compiled=compile_json_schema(xgrammar_profile,schema);logits_processor=build_transformers_logits_processor(compiled);all_eos=set(configured_eos)
   generation_started=time.perf_counter()
   with torch.inference_mode():generated=vlm.generate(**inputs,max_new_tokens=max_tokens,do_sample=False,logits_processor=[logits_processor],eos_token_id=configured_eos,return_dict_in_generate=True)
   generation_seconds=time.perf_counter()-generation_started;new_tokens=generated.sequences[:,inputs.input_ids.shape[1]:];token_ids=[int(token_id) for token_id in new_tokens[0].tolist()];raw=processor.batch_decode(new_tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];last=token_ids[-1] if token_ids else None;metadata={'generated_token_count':len(token_ids),'generated_token_ids':token_ids,'last_token_id':last,'terminated_by_eos':last in all_eos,'reached_max_new_tokens':len(token_ids)==max_tokens,'generation_seconds':generation_seconds,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'cuda_peak_reserved_bytes':torch.cuda.max_memory_reserved()};return raw,metadata
 ledger=ImmutableAttemptLedger(a.output_root/'diagnostics',plan_id=plan['plan_id'],maximum_attempts=auth['maximum_total_future_calls'])
 def scene_execute(job):
  row,paths,hashes,cache_id=job.payload
  def build(raw,metadata):
   draft=json.loads(raw);base={'pair_id':row['pair_id'],'left_observation_id':row['left_observation_id'],'right_observation_id':row['right_observation_id'],'left_reference_asset_sha256':hashes[0],'right_reference_asset_sha256':hashes[1],'proposal_status':'proposed','ai_draft':draft,'generation':{'input_identity_sha256':hashlib.sha256(canonical_bytes(job.fingerprint)).hexdigest(),'cache_entry_id':cache_id,'raw_output_sha256':hashlib.sha256(raw.encode()).hexdigest(),'generated_at_utc':now(),'model_id':model['model_id'],'model_revision':model['revision']}};base['proposal_id']=content_id('i20-assist-scene-proposal-sha256-',base,'proposal_id');validate_scene_proposal_record(base,fixture_row=row,asset_sha256=by_obs_sha);return {'query_id':None,'candidate_id':'scene','image_id':row['pair_id'],'claim_id':cache_id,'proposal':base}
  return execute_immutable_attempt(ledger=ledger,kind='scene',target_id=row['pair_id'],cache_entry_id=cache_id,now=now,generate_raw=lambda:generate(paths,scene_prompt(),scene_draft_schema()),parse_and_build=build)
 def annotation_execute(job):
  row,path,cache_id=job.payload
  def build(raw,metadata):
   draft=materialize_annotation_evidence_draft(json.loads(raw));base={'observation_id':row['observation_id'],'reference_asset_id':row['reference_asset_id'],'reference_asset_sha256':row['reference_asset_sha256'],'proposal_status':'proposed','ai_draft':draft,'generation':{'input_identity_sha256':hashlib.sha256(canonical_bytes(job.fingerprint)).hexdigest(),'cache_entry_id':cache_id,'raw_output_sha256':hashlib.sha256(raw.encode()).hexdigest(),'generated_at_utc':now(),'model_id':model['model_id'],'model_revision':model['revision']}};base['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',base,'proposal_id');validate_annotation_proposal_record(base,fixture_row=row);return {'query_id':None,'candidate_id':'annotation','image_id':row['observation_id'],'claim_id':cache_id,'proposal':base}
  return execute_immutable_attempt(ledger=ledger,kind='annotation',target_id=row['observation_id'],cache_entry_id=cache_id,now=now,generate_raw=lambda:generate([path],annotation_prompt_v10(),annotation_evidence_draft_schema_v10()),parse_and_build=build)
 try:
  if a.probe_first_annotation_only:
   annotation_records=run_resumable(checkpoint_path=a.output_root/'checkpoints/annotation-proposals.jsonl',provenance={'plan_id':plan['plan_id'],'kind':'annotation'},jobs=annotation_jobs,execute=annotation_execute,policy_result=lambda job:None)
   finalize_json_atomic(output_path=a.output_root/'annotation-probe-report.json',document={'schema_version':'1.0','contract_version':'i20-assisted-annotation-probe-report-v1','plan_id':plan['plan_id'],'runner_sha256':runner_sha,'probe_kind':'annotation','target_id':plan['jobs']['annotation_order'][0],'calls':ledger.summary(),'valid_annotation_proposals':len(annotation_records),'valid_scene_proposals':0,'full_campaign_executed':False});return 0
  scene_records=run_resumable(checkpoint_path=a.output_root/'checkpoints/scene-proposals.jsonl',provenance={'plan_id':plan['plan_id'],'kind':'scene'},jobs=scene_jobs[:1] if a.probe_first_scene_only else scene_jobs,execute=scene_execute,policy_result=lambda job:None)
  if a.probe_first_scene_only:
   finalize_json_atomic(output_path=a.output_root/'probe-report.json',document={'schema_version':'1.0','contract_version':'i20-assisted-probe-report-v1','plan_id':plan['plan_id'],'runner_sha256':runner_sha,'calls':ledger.summary(),'valid_scene_proposals':len(scene_records),'model_load_seconds':model_load_seconds,'full_campaign_executed':False});return 0
  annotation_records=run_resumable(checkpoint_path=a.output_root/'checkpoints/annotation-proposals.jsonl',provenance={'plan_id':plan['plan_id'],'kind':'annotation'},jobs=annotation_jobs,execute=annotation_execute,policy_result=lambda job:None)
 finally:
  del vlm;torch.cuda.empty_cache()
 scenes={'schema_version':'1.0','contract_version':'i20-assisted-scene-proposals-v1','artifact_id':'','plan_id':plan['plan_id'],'scene_fixture_sha256':scene['fixture_sha256'],'records':[row['proposal'] for row in scene_records]};scenes['artifact_id']=content_id('i20-assist-scene-proposals-sha256-',scenes,'artifact_id');annotations={'schema_version':'1.0','contract_version':'i20-assisted-annotation-proposals-v1','artifact_id':'','plan_id':plan['plan_id'],'annotation_fixture_id':annotation['fixture_id'],'records':[row['proposal'] for row in annotation_records]};annotations['artifact_id']=content_id('i20-assist-annotation-proposals-sha256-',annotations,'artifact_id');validate_scene_proposals(scenes,plan=plan,fixture=scene,annotation_fixture=annotation);validate_annotation_proposals(annotations,plan=plan,fixture=annotation);finalize_json_atomic(output_path=a.output_root/'scene-proposals.json',document=scenes);finalize_json_atomic(output_path=a.output_root/'annotation-proposals.json',document=annotations);report={'schema_version':'1.0','contract_version':'i20-assisted-execution-report-v1','plan_id':plan['plan_id'],'authorization_sha256':digest(a.authorization),'model':{'model_id':model['model_id'],'revision':model['revision'],'weight_sha256':model['weight_sha256']},'calls':{'scene':len(scene_records),'annotation':len(annotation_records),'total':len(scene_records)+len(annotation_records)},'validation':{'scene_valid':True,'annotation_valid':True,'empty_outputs':0,'truncated_outputs':0,'invalid_outputs':0},'resources':{'model_load_seconds':model_load_seconds,'execution_seconds':time.perf_counter()-execution_started,'cuda_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'cuda_peak_reserved_bytes':torch.cuda.max_memory_reserved(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024},'protocol':{'network_permitted':False,'downloads':0,'gt_used':False,'rankings_used':False,'osm_used':False,'h38_h61_used':False,'human_review_required':True}};finalize_json_atomic(output_path=a.output_root/'execution-report.json',document=report);print(json.dumps({'scene_proposals':12,'annotation_proposals':20,'plan_id':plan['plan_id'],'resources':report['resources']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
