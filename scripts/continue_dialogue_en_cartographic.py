#!/usr/bin/env python3
"""Prepara E1-E3 o compone E0-E3 sin sobrescribir el bundle histórico."""

from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.dialogue_en_cartographic import DialogueEnCartographicError,compose_query_bundle,materialize_continuation,prepare_continuation_bundle,sha256_file
from src.tfg_phase0.f5_text_transform import TransformResult,hash_tree_manifest

def _write(path,doc):
 payload=json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2).encode()+b'\n'
 with path.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
def _publish(root,documents):
 if root.exists():raise DialogueEnCartographicError('output-root ya existe')
 root.parent.mkdir(parents=True,exist_ok=True);stage=root.with_name('.'+root.name+f'.stage-{os.getpid()}')
 if stage.exists():shutil.rmtree(stage)
 try:
  stage.mkdir()
  for name,doc in documents.items():_write(stage/name,doc)
  manifest={'schema_version':'1.0','contract_version':'dialogue-v3-en-cartographic-continuation-manifest-v2','status':'committed','files':{name:sha256_file(stage/name) for name in sorted(documents)}};_write(stage/'manifest.json',manifest);os.replace(stage,root)
 except Exception:
  if stage.exists():shutil.rmtree(stage)
  raise
class Fake:
 def __init__(self,outputs):self.outputs=outputs;self.calls=[]
 def generate_prompt(self,prompt,config):
  round_id=('E1','E2','E3')[len(self.calls)];self.calls.append(round_id);text=self.outputs[round_id];return TransformResult(text,text,0.0)
def _authorization(path,plan,parent,e0_review,output,model_path):
 d=json.loads(path.read_text());expected={'schema_version','contract_version','status','stage','approved','gpu_authorized','model_id','model_revision','model_snapshot_sha256','plan_sha256','prompt_sha256','parent_manifest_sha256','parent_queries_sha256','historical_E0_output_sha256','e0_human_review_sha256','runner_sha256','validator_sha256','target_rounds','maximum_model_loads','maximum_calls','maximum_calls_per_round','automatic_retries','continue_after_failure','regenerate_historical_rounds','stable_swap_required','output_root','authorization_source'}
 if set(d)!=expected or d['contract_version']!='dialogue-v3-en-cartographic-qwen-continuation-authorization-v2' or d['status']!='OPERATOR_AUTHORIZED' or d['stage']!='query_generation_continuation' or d['approved'] is not True or d['gpu_authorized'] is not True:raise DialogueEnCartographicError('autorización de continuación incompatible')
 limits=(d['target_rounds'],d['maximum_model_loads'],d['maximum_calls'],d['maximum_calls_per_round'],d['automatic_retries'],d['continue_after_failure'],d['regenerate_historical_rounds'],d['stable_swap_required'])
 if limits!=(['E1','E2','E3'],1,3,1,0,False,False,True):raise DialogueEnCartographicError('límites de continuación incompatibles')
 if d['model_id']!='Qwen/Qwen3-8B' or d['model_revision']!='b968826d9c46dd6066d109eabc6255188de91218' or d['model_snapshot_sha256']!=hash_tree_manifest(model_path):raise DialogueEnCartographicError('modelo de continuación incompatible')
 if d['plan_sha256']!=sha256_file(plan/'experiment-plan.json') or d['prompt_sha256']!='91c620bf3f255912e7dfdd1a524a728f9ce48f31180f9c4ca15bb3f3967de64c' or d['parent_manifest_sha256']!=sha256_file(parent/'manifest.json') or d['parent_queries_sha256']!=sha256_file(parent/'queries.json') or d['historical_E0_output_sha256']!='3d97a4a1966f36ece2755059f47fc2d946efcbbbbc620420d9b107820627aa11' or d['e0_human_review_sha256']!=sha256_file(e0_review) or d['runner_sha256']!=sha256_file(Path(__file__)) or d['validator_sha256']!=sha256_file(ROOT/'src/tfg_phase0/dialogue_en_cartographic.py') or Path(d['output_root']).resolve()!=output:raise DialogueEnCartographicError('hashes o output de continuación divergentes')
 return d
def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 q=sub.add_parser('prepare');q.add_argument('--plan-root',type=Path,required=True);q.add_argument('--parent-root',type=Path,required=True);q.add_argument('--e0-review',type=Path,required=True);q.add_argument('--output-root',type=Path,required=True)
 q=sub.add_parser('fake');q.add_argument('--plan-root',type=Path,required=True);q.add_argument('--parent-root',type=Path,required=True);q.add_argument('--e0-review',type=Path,required=True);q.add_argument('--fake-outputs',type=Path,required=True);q.add_argument('--output-root',type=Path,required=True)
 q=sub.add_parser('real');q.add_argument('--plan-root',type=Path,required=True);q.add_argument('--parent-root',type=Path,required=True);q.add_argument('--e0-review',type=Path,required=True);q.add_argument('--authorization',type=Path,required=True);q.add_argument('--model-path',type=Path,required=True);q.add_argument('--output-root',type=Path,required=True)
 q=sub.add_parser('compose');q.add_argument('--parent-root',type=Path,required=True);q.add_argument('--continuation-root',type=Path,required=True);q.add_argument('--e0-review',type=Path,required=True);q.add_argument('--output-root',type=Path,required=True)
 a=p.parse_args();output=a.output_root.resolve()
 if a.command=='compose':bundle=compose_query_bundle(a.parent_root.resolve(),a.continuation_root.resolve(),a.e0_review.resolve());_publish(output,{'queries.json':bundle});print(json.dumps({'status':bundle['status'],'output':str(output)}));return 0
 plan=a.plan_root.resolve();parent=a.parent_root.resolve();review=a.e0_review.resolve();prepared=prepare_continuation_bundle(plan,parent,review)
 if a.command=='prepare':bundle=prepared
 elif a.command=='fake':bundle=materialize_continuation(prepared,Fake(json.loads(a.fake_outputs.read_text())),synthetic_fixture=True)
 else:
  model=a.model_path.resolve();_authorization(a.authorization.resolve(),plan,parent,review,output,model)
  from scripts.run_dialogue_v3_visual_worker_smoke import STABLE_SWAP_INTERVAL_SECONDS,STABLE_SWAP_SAMPLES,collect_stable_swap_samples,evaluate_memory_gate
  from scripts.run_qwen3_vl_8b_memory_smoke import compute_processes
  ollama=subprocess.run(['ollama','ps'],capture_output=True,text=True,timeout=10);status='no_model_resident' if ollama.returncode==0 and len(ollama.stdout.splitlines())<=1 else 'model_resident_or_unverified';samples=collect_stable_swap_samples(count=STABLE_SWAP_SAMPLES,interval_seconds=STABLE_SWAP_INTERVAL_SECONDS);gate=evaluate_memory_gate(policy='stable-swap',host_compute_process_count=len(compute_processes()),host_ollama_status=status,samples=samples)
  if not gate['passed']:raise DialogueEnCartographicError('stable-swap-v1 bloquea continuación: '+','.join(gate['blocking_reasons']))
  from src.tfg_phase0.f5_text_transform import QwenTransformersAdapter
  transformer=QwenTransformersAdapter(model,model_id='Qwen/Qwen3-8B',revision='b968826d9c46dd6066d109eabc6255188de91218')
  try:bundle=materialize_continuation(prepared,transformer,synthetic_fixture=False)
  finally:transformer.close()
 _publish(output,{'queries.json':bundle,'lineage.json':bundle['parent']});print(json.dumps({'status':bundle['status'],'output':str(output),'calls':bundle.get('execution',{}).get('calls',0)}));return 0
if __name__=='__main__':raise SystemExit(main())
