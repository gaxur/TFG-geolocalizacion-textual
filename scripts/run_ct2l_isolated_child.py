#!/usr/bin/env python3
"""Hijo mínimo CT2L: startup CPU verificable o una transición de retrieval real."""
from __future__ import annotations
import argparse,hashlib,json,os,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,ResidentGallery,load_runtime_config
from src.tfg_phase0.interactive_dialogue import F3EvidenceIndex,QuestionIntent,ResidentCT2LAdapter
from src.tfg_phase0.interactive_dialogue_multiturn import MultiTurnConfig,MultiTurnDialogueOrchestrator,RetrievalDeferred,interpret_answer,project_visual_session_to_v2,validate_multiturn_session

def digest(path):
 value=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
 return value.hexdigest()
def write_atomic(path,document):
 payload=json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2).encode()+b'\n';temporary=path.with_name('.'+path.name+'.tmp')
 with temporary.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
 os.replace(temporary,path);descriptor=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(descriptor)
 finally:os.close(descriptor)
def load_inputs(config_path:Path):
 config=json.loads(config_path.read_text());policy_raw=json.loads((ROOT/config['dialogue_policy']).read_text());policy=__import__('src.tfg_phase0.interactive_dialogue',fromlist=['DialoguePolicyConfig']).DialoguePolicyConfig(reserve_size=policy_raw['reserve_size'],cluster_radius_m=policy_raw['cluster_radius_m'],minimum_hypotheses=policy_raw['minimum_hypotheses'],minimum_supported_hypotheses=policy_raw['minimum_supported_hypotheses'],maximum_supported_fraction=policy_raw['maximum_supported_fraction'],allow_qwen_question=policy_raw['allow_qwen_question'],enable_controlled_rewrite=policy_raw['enable_controlled_rewrite']);multi=MultiTurnConfig(max_questions=config['max_questions'],policy=policy);model,galleries=load_runtime_config(ROOT/config['ct2l_config'],project_root=ROOT,cvg_utils_sha256=config['cvg_utils_sha256'],clip_weights_path=Path(config['clip_weights']));selected=[value for value in galleries if value.gallery_id==config['gallery_id']]
 if len(selected)!=1:raise RuntimeError('galería CT2L aislada incompatible')
 evidence=F3EvidenceIndex.load_bundle(ROOT/config['f3_bundle']);return config,multi,model,selected[0],evidence
def startup(config_path:Path):
 config,multi,model,gallery,evidence=load_inputs(config_path);resident=ResidentGallery.load(gallery,region_config=ROOT/config['region_config'],deep_validate_visual_assets=False)
 if resident.gallery_id!=config['gallery_id'] or evidence.catalog_manifest_id!=resident.catalog.manifest_id or evidence.catalog_manifest_sha256!=resident.catalog.sha256:raise RuntimeError('F3, catálogo y galería no coinciden')
 if 'torch' in sys.modules or 'clip' in sys.modules:raise RuntimeError('startup CPU importó torch o clip')
 return {'schema_version':'1.0','contract_version':'ct2l-isolated-child-startup-v1','status':'CHILD_STARTUP_CPU_PASS','stage_reached':'immediately_before_CrossText2LocRetriever.load','python_executable':sys.executable,'python_prefix':sys.prefix,'gallery_id':resident.gallery_id,'gallery_count':len(resident.candidate_ids),'embedding_dataset_id':resident.embedding_manifest['embedding_dataset_id'],'f3_dataset_id':evidence.dataset_id,'checkpoint_sha256':digest(model.checkpoint),'clip_weights_sha256':digest(model.clip_weights),'torch_imported':False,'clip_imported':False,'cuda_initialized':False,'models_loaded':False}
def second_turn_startup(run_root:Path):
 config,multi,model,gallery,evidence=load_inputs(run_root/'configuration.json');state=json.loads((run_root/'state.json').read_text());answer=(state.get('pending_answer') or {}).get('literal')
 if not answer or not state.get('session_snapshot'):raise RuntimeError('run sin respuesta pendiente o snapshot')
 previous=json.loads((run_root/state['session_snapshot']).read_text());calls=[]
 turn=previous['turns'][-1];q=turn['question'];intent=QuestionIntent(q['intent_id'],q['feature'],q['label'],tuple(q['supported_hypothesis_ids']),tuple(q['unknown_hypothesis_ids']),tuple(q['evidence_refs']),q['deterministic_question'],());interpreted=interpret_answer(answer,intent,previous['claims']);claim={'claim_id':f"claim-{turn['index']:03d}",'turn_index':turn['index'],'feature':intent.feature,'label':intent.label,'polarity':interpreted['polarity'],'clarification':interpreted['clarification'],'answer_literal':answer,'active':True,'supersedes':None}
 class CaptureRetriever:
  gallery_id=config['gallery_id']
  @property
  def metadata(self):return previous['models']['retrieval']
  def count_tokens(self,text):return None
  def retrieve_full(self,**kwargs):calls.append(kwargs);raise RetrievalDeferred('second-turn startup captured retrieval')
 base=MultiTurnDialogueOrchestrator(retriever=CaptureRetriever(),evidence=evidence,config=multi,text_adapter=None)
 try:base.answer(project_visual_session_to_v2(previous),answer)
 except RetrievalDeferred:pass
 if len(calls)!=1:raise RuntimeError('segundo turno no alcanzó exactamente una recuperación')
 if 'torch' in sys.modules or 'clip' in sys.modules:raise RuntimeError('startup segundo turno importó torch o clip')
 return {'schema_version':'1.0','contract_version':'ct2l-isolated-child-second-turn-startup-v1','status':'SECOND_TURN_CHILD_STARTUP_CPU_PASS','stage_reached':'immediately_before_second_turn_retrieve_full','python_executable':sys.executable,'python_prefix':sys.prefix,'answer_literal':answer,'answer_sha256':hashlib.sha256(answer.encode()).hexdigest(),'interpretation':interpreted,'claim':claim,'retrieval_request':calls[0],'torch_imported':False,'clip_imported':False,'cuda_initialized':False,'models_loaded':False,'run_modified':False}
def execute(run_root:Path,output:Path,answer:str|None):
 config_path=run_root/'configuration.json';config,multi,model,gallery,evidence=load_inputs(config_path);started=time.perf_counter();runtime=CrossText2LocRetriever.load(model_config=model,gallery_configs=[gallery],region_config=ROOT/config['region_config'],deep_validate_visual_assets=False)
 try:
  retriever=ResidentCT2LAdapter(runtime,config['gallery_id']);base=MultiTurnDialogueOrchestrator(retriever=retriever,evidence=evidence,config=multi,text_adapter=None)
  if answer is None:session=base.start(session_label=config['session_label'],description=config['initial_description'],language=config['language'])
  else:
   state=json.loads((run_root/'state.json').read_text());previous=json.loads((run_root/state['session_snapshot']).read_text());session=base.answer(project_visual_session_to_v2(previous),answer)
  validate_multiturn_session(session);ranking=session['initial_ranking'] if answer is None else session['turns'][-1].get('posterior_ranking') or session['current_ranking'];actual=session['turns'][-1]['question']['feature'] if session['status']=='awaiting_answer' else 'none';document={'schema_version':'1.0','contract_version':'dialogue-v3-retrieval-child-result-v1','status':'completed','session_id':config['session_id'],'session_label':config['session_label'],'initial_description_sha256':hashlib.sha256(config['initial_description'].encode()).hexdigest(),'intent_family':actual,'gallery_id':config['gallery_id'],'identities':{'retrieval':session['models']['retrieval'],'clip_sha256':digest(model.clip_weights),'checkpoint_sha256':digest(model.checkpoint),'f3_dataset_id':evidence.dataset_id,'f3_source_hashes':evidence.source_hashes},'dialogue_policy':session['policy'],'ranking_initial':ranking,'candidate_ids':[row['candidate_id'] for row in ranking['results']],'scores':[row['cosine_similarity'] for row in ranking['results']],'timings_ms':{'phase_total':(time.perf_counter()-started)*1000},'provenance':{'ground_truth_used':False,'mapillary_location_used':False,'qwen_text_used':False,'isolated_process_pid':os.getpid()},'session_v2':session};write_atomic(output,document);return 0
 finally:runtime.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('--check-child-startup',action='store_true');p.add_argument('--check-second-turn-startup',action='store_true');p.add_argument('--config',type=Path);p.add_argument('--run-root',type=Path);p.add_argument('--output',type=Path);p.add_argument('--answer');a=p.parse_args()
 if a.check_child_startup:
  if a.config is None:raise ValueError('--config es obligatorio')
  print(json.dumps(startup(a.config.resolve()),sort_keys=True));return 0
 if a.check_second_turn_startup:
  if a.run_root is None:raise ValueError('--run-root es obligatorio')
  print(json.dumps(second_turn_startup(a.run_root.resolve()),ensure_ascii=False,sort_keys=True));return 0
 if a.run_root is None or a.output is None:raise ValueError('--run-root y --output son obligatorios')
 return execute(a.run_root.resolve(),a.output.resolve(),a.answer)
if __name__=='__main__':raise SystemExit(main())
