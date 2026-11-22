"""Adaptador runtime real y aislado de DialogueVPR-FreeText-v1."""
from __future__ import annotations
import hashlib,json,math,platform,threading,time
from importlib import metadata
from pathlib import Path
from typing import Any,Mapping,Sequence
from backend.atlas_api.dialogue_executor import SequentialDialogueExecutor
from backend.atlas_api.dialogue_sessions import atomic_write
from src.tfg_phase0.dialogue_freetext_v1 import FreeTextDialogueExecutor,FreeTextQuestion,digest_text,select_freetext_question,validate_full_ranking
from src.tfg_phase0.interactive_dialogue import DialoguePolicyConfig
from src.tfg_phase0.f5_text_transform import validate_transformation,GenerationConfig
from src.tfg_phase0.validation import validate_document

def observable_transcript(transcript:str)->str:
 lines=transcript.splitlines();observations=[];mode=None
 for line in lines:
  if line=='[DESCRIPCIÓN ORIGINAL]':mode='observation';continue
  if line.startswith('[TURNO ') and line.endswith('— RESPUESTA LITERAL]'):mode='observation';continue
  if line.startswith('[TURNO ') and line.endswith('— PREGUNTA]'):mode='question';continue
  if mode=='observation' and line.strip():observations.append(line)
 return '\n'.join(observations)

def _artifact_digest(path):
 if path.is_file():return hashlib.sha256(path.read_bytes()).hexdigest()
 if not path.is_dir():raise RuntimeError(f'artefacto requerido ausente: {path.name}')
 rows=[]
 for item in sorted(candidate for candidate in path.rglob('*') if candidate.is_file()):rows.append({'path':item.relative_to(path).as_posix(),'sha256':hashlib.sha256(item.read_bytes()).hexdigest()})
 if not rows:raise RuntimeError(f'bundle requerido vacío: {path.name}')
 return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class RuntimeQuestionPort:
 def __init__(self,owner):self.owner=owner
 def select(self,*,ranking:Mapping[str,Any],description:str,turns:Sequence[Mapping[str,Any]]):return select_freetext_question(ranking=ranking,evidence=self.owner.evidence,policy=self.owner.policy,description=description,turns=turns)
class RuntimeQwenPort:
 def __init__(self,owner,root):self.owner=owner;self.root=root
 def transform(self,*,stage:str,transcript:str,prompt:str):
  if self.owner.resident_models:return self.owner._resident_transform(stage=stage,transcript=transcript,prompt=prompt,root=self.root)
  index=int(stage[1:]);request={'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-qwen-worker-request-v1','stage':stage,'transcript':transcript,'transcript_sha256':digest_text(transcript),'prompt':prompt,'prompt_version':'dialogue-vpr-freetext-qwen-v1','prompt_sha256':digest_text(prompt)};request_path=self.root/f'freetext-qwen-request-{index}.json';output=self.root/f'freetext-en-{index}.json';atomic_write(request_path,request);self.owner._emit(stage,'qwen','running');self.owner._gate(self.root,f'freetext-qwen-{index}');self.owner._run([self.owner.python,str(Path(__file__).resolve().parents[2]/'scripts/run_dialogue_freetext_worker.py'),'--request',str(request_path),'--model',str(self.owner.qwen_model),'--output',str(output)],self.root,f'freetext-qwen-{index}',360);document=json.loads(output.read_text());self.owner._emit(stage,'qwen','completed');return document
class RuntimeRetrievalPort:
 def __init__(self,owner,root):self.owner=owner;self.root=root
 def retrieve(self,*,stage:str,query_id:str,text:str):
  if self.owner.resident_models:return self.owner._resident_retrieve(stage=stage,query_id=query_id,text=text,root=self.root)
  index=int(stage[1:]);english={'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()};self.owner._emit(stage,'crosstext2loc','running');result=self.owner._ct2l(query_id=query_id,round_index=index,english=english,root=self.root);self.owner._emit(stage,'crosstext2loc','completed');return result

class FreeTextRuntimeExecutor(SequentialDialogueExecutor):
 policy_id='dialogue-vpr-freetext-v1'
 def __init__(self,policy_config:Path|None=None,ollama_status_config:Path|None=None,resident_models:bool=False,qwen_factory=None,retriever_factory=None,question_policy_factory=None,final_ranking_postprocessor_factory=None,**kwargs):
  super().__init__(**kwargs);self.policy_config=policy_config or Path(__file__).resolve().parents[2]/'config/interactive_dialogue_freetext_v1.json';self.ollama_status_config=ollama_status_config;self.resident_models=resident_models;self._qwen_factory=qwen_factory;self._retriever_factory=retriever_factory;self._question_policy_factory=question_policy_factory;self._final_ranking_postprocessor_factory=final_ranking_postprocessor_factory;self._resident_qwen=None;self._resident_retriever=None;self._resident_gallery_ids=();self._resident_gated_models=set();self._resident_lock=threading.RLock();raw=json.loads(self.policy_config.read_text());self.policy=DialoguePolicyConfig(reserve_size=raw['reserve_size'],cluster_radius_m=raw['cluster_radius_m'],minimum_hypotheses=raw['minimum_hypotheses'],minimum_supported_hypotheses=raw['minimum_supported_hypotheses'],maximum_supported_fraction=raw['maximum_supported_fraction'],allow_qwen_question=False,enable_controlled_rewrite=False);self.max_questions=raw['maximum_questions'];self.progress_callback=None;self._identity,self._identity_stats=self._build_identity()
 def _emit(self,stage,component,state):
  if self.progress_callback:self.progress_callback(stage,component,state)
 @property
 def identity(self):
  if self._artifact_stats()!=self._identity_stats:raise RuntimeError('artefactos del ejecutor FreeText modificados')
  return dict(self._identity)
 def _artifact_paths(self):
  root=Path(__file__).resolve().parents[2];return [root/'backend/atlas_api',root/'src/tfg_phase0',root/'scripts/run_dialogue_freetext_worker.py',root/'scripts/run_mvp_dialogue_worker.py',self.policy_config,*([self.ollama_status_config] if self.ollama_status_config else []),self.runtime_config,self.region_config,self.f3_bundle,self.clip_weights,self.qwen_model]
 def _artifact_stats(self):
  rows={}
  for path in self._artifact_paths():
   items=[path] if path.is_file() else sorted(candidate for candidate in path.rglob('*') if candidate.is_file())
   for item in items:
    stat=item.stat();rows[str(item)]=(stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
  return rows
 def _build_identity(self):
  base=super().identity
  root=Path(__file__).resolve().parents[2]
  runtime=json.loads(self.runtime_config.read_text())
  gallery=runtime['galleries']['madrid-50m']
  embedding_manifest=json.loads((root/gallery['embedding_bundle']/'manifest.json').read_text())
  visual_manifest=json.loads((root/gallery['visual_bundle']/'manifest.json').read_text())
  checkpoint_path=root/runtime['model']['checkpoint'];checkpoint_sha256=_artifact_digest(checkpoint_path)
  if checkpoint_sha256!=embedding_manifest['checkpoint']['sha256']:raise RuntimeError('checkpoint real divergente del manifest de embeddings')
  base.update({'checkpoint_sha256':checkpoint_sha256,'madrid_50m_embedding_dataset_id':embedding_manifest['embedding_dataset_id'],'madrid_50m_visual_dataset_id':visual_manifest['visual_dataset_id']})
  if self._question_policy_factory is not None:base['question_policy_injection']='authorized_factory_required'
  if self._final_ranking_postprocessor_factory is not None:base['final_ranking_postprocessor_injection']='authorized_factory_required'
  qwen_files={name:self.qwen_model/name for name in ('config.json','model.safetensors.index.json','tokenizer_config.json')}
  missing=[name for name,path in qwen_files.items() if not path.is_file()]
  if missing:raise RuntimeError(f"identidad Qwen incompleta: {', '.join(missing)}")
  weights=sorted(self.qwen_model.glob('*.safetensors'));versions={name:metadata.version(name) for name in ('torch','transformers','numpy')};base.update({'atlas_api_tree_sha256':_artifact_digest(root/'backend/atlas_api'),'phase0_tree_sha256':_artifact_digest(root/'src/tfg_phase0'),'freetext_executor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'freetext_core_sha256':hashlib.sha256((root/'src/tfg_phase0/dialogue_freetext_v1.py').read_bytes()).hexdigest(),'freetext_worker_sha256':hashlib.sha256((root/'scripts/run_dialogue_freetext_worker.py').read_bytes()).hexdigest(),'freetext_policy_sha256':hashlib.sha256(self.policy_config.read_bytes()).hexdigest(),'runtime_config_sha256':_artifact_digest(self.runtime_config),'region_config_sha256':_artifact_digest(self.region_config),'f3_bundle_sha256':_artifact_digest(self.f3_bundle),'clip_weights_sha256':_artifact_digest(self.clip_weights),'qwen_config_sha256':_artifact_digest(qwen_files['config.json']),'qwen_weight_index_sha256':_artifact_digest(qwen_files['model.safetensors.index.json']),'qwen_tokenizer_config_sha256':_artifact_digest(qwen_files['tokenizer_config.json']),'qwen_snapshot_sha256':_artifact_digest(self.qwen_model),'qwen_model_artifacts':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in weights},'python_executable_sha256':_artifact_digest(Path(self.python)),'python_version':platform.python_version(),'runtime_distribution_versions':versions,'qwen_model_id':'Qwen/Qwen3-8B','qwen_model_revision':'b968826d9c46dd6066d109eabc6255188de91218','cvg_utils_sha256':self.cvg_utils_sha256,'ollama_ps_url':self.ollama_ps_url,'ollama_status_config_sha256':_artifact_digest(self.ollama_status_config) if self.ollama_status_config else 'not_configured','runtime_lifecycle':'resident-sequential-lazy-v1' if self.resident_models else 'ephemeral-sequential-v1'});return base,self._artifact_stats()
 def _load_qwen(self,root):
  if self._resident_qwen is not None:return 0.0
  self._resident_gate(root,'qwen');started=time.perf_counter()
  try:
   if self._qwen_factory:self._resident_qwen=self._qwen_factory()
   else:
    from src.tfg_phase0.f5_text_transform import QwenTransformersAdapter
    self._resident_qwen=QwenTransformersAdapter(self.qwen_model,model_id='Qwen/Qwen3-8B',revision='b968826d9c46dd6066d109eabc6255188de91218')
  except Exception:
   self._resident_gated_models.discard('qwen')
   try:
    import gc,torch;gc.collect();torch.cuda.empty_cache()
   except Exception:pass
   raise
  return (time.perf_counter()-started)*1000
 def _load_retriever(self,root,gallery_ids):
  wanted=tuple(gallery_ids)
  if self._resident_retriever is not None and self._resident_gallery_ids==wanted:return 0.0
  if self._resident_retriever is not None:self._resident_retriever.close();self._resident_retriever=None
  self._resident_gate(root,'crosstext2loc');started=time.perf_counter()
  try:
   if self._retriever_factory:self._resident_retriever=self._retriever_factory(wanted)
   else:
    from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
    model,galleries=load_runtime_config(self.runtime_config,project_root=Path(__file__).resolve().parents[2],cvg_utils_sha256=self.cvg_utils_sha256,clip_weights_path=self.clip_weights);by_id={row.gallery_id:row for row in galleries};selected=[by_id[row] for row in wanted];self._resident_retriever=CrossText2LocRetriever.load(model_config=model,gallery_configs=selected,region_config=self.region_config,deep_validate_visual_assets=False)
  except Exception:
   self._resident_gated_models.discard('crosstext2loc');raise
  self._resident_gallery_ids=wanted;return (time.perf_counter()-started)*1000
 def _resident_gate(self,root,component):
  if component in self._resident_gated_models:return
  self._gate(root,f'resident-{component}-load');self._resident_gated_models.add(component)
 def _write_telemetry(self,root,stage,component,load_ms,inference_ms,cache_hit,status,error=None):
  atomic_write(root/f'{stage.lower()}-{component}-runtime.json',{'schema_version':'1.0','contract_version':'atlas-freetext-resident-runtime-telemetry-v1','stage':stage,'component':component,'lifecycle':'resident-sequential-lazy-v1','model_load_ms':load_ms,'inference_wall_ms':inference_ms,'cache_hit':cache_hit,'status':status,'error':error})
 def _resident_transform(self,*,stage,transcript,prompt,root):
  with self._resident_lock:
   self._emit(stage,'qwen','running');load_ms=0.0;started=None
   try:
    load_ms=self._load_qwen(root);started=time.perf_counter();result=self._resident_qwen.generate_prompt(prompt,GenerationConfig());inference_ms=(time.perf_counter()-started)*1000
    if not isinstance(result.text,str) or not isinstance(result.raw_output,str) or not result.text or len(result.text)>2400 or result.text.startswith(('```','{')) or self._resident_qwen.metadata.model_id!='Qwen/Qwen3-8B' or self._resident_qwen.metadata.revision!='b968826d9c46dd6066d109eabc6255188de91218':raise ValueError('salida o identidad FreeText inválida')
    validation=validate_transformation(observable_transcript(transcript),result.text,'translate_en_cartographic',[],GenerationConfig())
    if not validation['structurally_valid']:raise ValueError('salida FreeText rechazada por validación')
    document={'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-en-v1','stage':stage,'transcript_sha256':digest_text(transcript),'prompt_version':'dialogue-vpr-freetext-qwen-v1','prompt_sha256':digest_text(prompt),'text':result.text,'raw_output':result.raw_output,'text_sha256':hashlib.sha256(result.text.encode()).hexdigest(),'duration_ms':result.duration_ms,'model':self._resident_qwen.metadata.__dict__};atomic_write(root/f'freetext-en-{int(stage[1:])}.json',document);self._write_telemetry(root,stage,'qwen',load_ms,inference_ms,load_ms==0.0,'completed');self._emit(stage,'qwen','completed');return document
   except Exception as error:
    if started is None:self._resident_gated_models.discard('qwen')
    self._write_telemetry(root,stage,'qwen',load_ms,(time.perf_counter()-started)*1000 if started else 0.0,self._resident_qwen is not None and load_ms==0.0,'failed',type(error).__name__);self._emit(stage,'qwen','failed');raise
 def _resident_retrieve(self,*,stage,query_id,text,root):
  gallery_ids=('madrid-50m',)
  with self._resident_lock:
   self._emit(stage,'crosstext2loc','running');load_ms=0.0;started=None
   try:
    load_ms=self._load_retriever(root,gallery_ids);started=time.perf_counter();response=self._resident_retriever.retrieve_many(gallery_ids=gallery_ids,query_id=query_id,text=text,language='en',k=253);inference_ms=(time.perf_counter()-started)*1000
    validate_document(response,'crosstext2loc_retrieval_response')
    if set(response)!={'schema_version','contract_version','query','model','retrievals','timings_ms'} or response.get('contract_version')!='crosstext2loc-retrieval-response-v1' or response.get('query')!={'query_id':query_id,'text':text,'language':'en'} or len(response.get('retrievals',[]))!=1:raise ValueError('envelope CT2L residente inválido')
    if response.get('model',{}).get('checkpoint_sha256')!=self._identity['checkpoint_sha256']:raise ValueError('checkpoint CT2L residente divergente')
    document=response['retrievals'][0]
    if document.get('gallery_id')!='madrid-50m' or document.get('gallery_count')!=253 or document.get('requested_k')!=253 or document.get('effective_k')!=253 or document.get('ranking_method')!='exhaustive_cosine' or document.get('tie_break')!='candidate_id_ascending' or document.get('visual_dataset_id')!=self._identity['madrid_50m_visual_dataset_id'] or document.get('embedding_dataset_id')!=self._identity['madrid_50m_embedding_dataset_id']:raise ValueError('galería CT2L residente inválida')
    for index,row in enumerate(document.get('results',[]),1):
     if set(row)!={'rank','candidate_id','latitude','longitude','cosine_similarity'} or row.get('rank')!=index or not isinstance(row.get('candidate_id'),str) or not row['candidate_id'] or not all(isinstance(row.get(key),(int,float)) and math.isfinite(row[key]) for key in ('latitude','longitude','cosine_similarity')) or not -90<=row['latitude']<=90 or not -180<=row['longitude']<=180:raise ValueError('fila CT2L residente inválida')
    validate_full_ranking(document);atomic_write(root/f'ranking-{int(stage[1:])}.json',document);self._write_telemetry(root,stage,'crosstext2loc',load_ms,inference_ms,load_ms==0.0,'completed');self._emit(stage,'crosstext2loc','completed');return document
   except Exception as error:
    if started is None:self._resident_gated_models.discard('crosstext2loc')
    self._write_telemetry(root,stage,'crosstext2loc',load_ms,(time.perf_counter()-started)*1000 if started else 0.0,self._resident_retriever is not None and load_ms==0.0,'failed',type(error).__name__);self._emit(stage,'crosstext2loc','failed');raise
 def close(self):
  with self._resident_lock:
   errors=[]
   for name in ('_resident_retriever','_resident_qwen'):
    value=getattr(self,name)
    try:
     if value is not None:value.close()
    except Exception as error:errors.append(error)
    finally:setattr(self,name,None)
   self._resident_gallery_ids=();self._resident_gated_models.clear()
   if errors:raise RuntimeError('falló el cierre de recursos residentes') from errors[0]
 def _core(self,root):
  common={'qwen':RuntimeQwenPort(self,root),'retriever':RuntimeRetrievalPort(self,root),'final_ranking_postprocessor':self._final_ranking_postprocessor_factory(self,root) if self._final_ranking_postprocessor_factory is not None else None}
  if self._question_policy_factory is None:return FreeTextDialogueExecutor(**common,questions=RuntimeQuestionPort(self))
  return FreeTextDialogueExecutor(**common,question_policy=self._question_policy_factory(self,root))
 def start(self,*,query_id,description,session_root):return self._core(session_root).start(query_id=query_id,description=description)
 def answer(self,*,state,answer,answer_kind,session_root):return self._core(session_root).answer(state=state,answer_literal=answer)
