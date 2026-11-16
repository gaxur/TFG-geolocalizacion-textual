"""Servicio persistente aislado para una sesión autorizada FreeText-v1."""
from __future__ import annotations
from datetime import datetime,timezone
import fcntl,hashlib,json,os,re,uuid
from pathlib import Path
from typing import Any,Mapping
from backend.atlas_api.dialogue_sessions import canonical,sha256_file
from src.tfg_phase0.dialogue_freetext_v1 import validate_full_ranking

class FreeTextUnavailable(RuntimeError):pass
class FreeTextConflict(ValueError):pass
def digest(v):return hashlib.sha256(canonical(v)).hexdigest()
def atomic(path:Path,document:Mapping[str,Any]):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp');payload=canonical(document)+b'\n'
 try:
  with tmp.open('xb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path);fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
 finally:tmp.unlink(missing_ok=True)
class FreeTextSessionService:
 def __init__(self,*,session_root:Path,image_root:Path,authorization_root:Path,authorization_file:str,executor=None,enabled:bool=False,policy_registry=None):self.session_root=session_root;self.image_root=image_root;self.authorization_root=authorization_root;self.authorization_file=authorization_file;self.executor=executor;self.enabled=enabled;self.policy_registry=policy_registry;session_root.mkdir(parents=True,exist_ok=True)
 def _auth(self):
  path=self.authorization_root/self.authorization_file
  if not path.is_file():raise FreeTextUnavailable('autorización FreeText ausente')
  d=json.loads(path.read_text());plan_path=self.authorization_root/d.get('plan_file','');plan=json.loads(plan_path.read_text()) if plan_path.is_file() else {};return path,d,plan_path,plan
 def _used(self,authorization_id):
  for p in self.session_root.glob('dialogue-freetext-*/session.json'):
   try:d=self.load(p.parent.name)
   except Exception:continue
   if d['authorization']['authorization_id']==authorization_id:return d
  return None
 def _authorization_status(self,d):
  if self._used(d.get('authorization_id')):return 'consumed'
  return 'authorized' if d.get('status')=='OPERATOR_AUTHORIZED' and d.get('approved') is True else 'pending'
 def pilot(self):
  try:path,a,plan_path,plan=self._auth();image=self.image_root/a.get('reference_image_filename','');available=image.is_file() and sha256_file(image)==a.get('reference_image_sha256');status=self._authorization_status(a);used=self._used(a.get('authorization_id'))
  except Exception:return {'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-pilot-public-v1','available':False,'authorization_status':'invalid'}
  return {'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-pilot-public-v1','available':self.enabled,'policy_id':'dialogue-vpr-freetext-v1','experimental_query_id':a.get('experimental_query_id'),'source_query_id':a.get('source_query_id'),'description_es':plan.get('description_es'),'description_sha256':a.get('description_sha256'),'image_url':'/api/v1/dialogue-freetext/pilot/image','image_available':available,'authorization_status':status,'session_id':used.get('session_id') if used else None,'session_status':used.get('status') if used else None,'maximum_questions':3,'maximum_qwen_calls':4,'maximum_ct2l_calls':4}
 def policies(self):return self.policy_registry.catalogue(self.pilot()) if self.policy_registry is not None else {'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-policy-catalogue-v1','policies':[{**self.pilot(),'provisional':False,'description_length':'long','variant_id':None}]}
 def start_policy(self,policy_id,variant_id):
  if self.policy_registry is None:raise FreeTextUnavailable('registro de políticas FreeText ausente')
  try:variant=self.policy_registry.resolve(policy_id,variant_id)
  except Exception as error:raise FreeTextUnavailable(str(error)) from error
  # Toda activación medium necesita una autorización/session contract nueva; no reutiliza v1.
  raise FreeTextUnavailable(f"política {policy_id} preparada pero sin autorización operativa para {variant['variant_id']}")
 def image(self):
  _,a,_,_=self._auth();path=(self.image_root/a['reference_image_filename']).resolve()
  if self.image_root.resolve() not in path.parents or not path.is_file() or sha256_file(path)!=a['reference_image_sha256']:raise FreeTextConflict('imagen FreeText inválida')
  return path
 def _validate_authorization(self,query_id,description):
  if not self.enabled or self.executor is None:raise FreeTextUnavailable('FreeText-v1 no está habilitado')
  path,a,plan_path,plan=self._auth();required={'contract_version':'atlas-dialogue-freetext-authorization-v1','policy_id':'dialogue-vpr-freetext-v1','status':'OPERATOR_AUTHORIZED','approved':True,'experimental_query_id':query_id,'description_sha256':hashlib.sha256(description.encode()).hexdigest(),'maximum_questions':3,'maximum_qwen_loads':4,'maximum_qwen_calls':4,'maximum_ct2l_loads':4,'maximum_ct2l_calls':4,'automatic_retries':0,'memory_policy':'stable-swap-v2','network_permitted':False,'ground_truth_permitted':False,'references_permitted':False,'vlm_permitted':False,'h38_h61_permitted':False,'semantic_parser_permitted':False,'literal_transcript_required':True,'full_e0_e3_required':True,'reusable_for_other_session':False}
  if any(a.get(k)!=v for k,v in required.items()):raise FreeTextUnavailable('autorización FreeText incompatible')
  expected={**self.executor.identity,'plan_sha256':sha256_file(plan_path),'reference_image_sha256':sha256_file(self.image())}
  aliases={'freetext_core_sha256':'core_sha256','freetext_executor_sha256':'runtime_executor_sha256','freetext_worker_sha256':'qwen_worker_sha256','freetext_policy_sha256':'policy_sha256'}
  if any(a.get(aliases.get(k,k))!=v for k,v in expected.items()):raise FreeTextUnavailable('hashes FreeText divergentes')
  if plan.get('experimental_query_id')!=query_id or plan.get('description_es')!=description:raise FreeTextUnavailable('plan FreeText divergente')
  return path,a,plan
 def _persist(self,d):
  d['updated_at_utc']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z');d['state_sha256']=digest(d['state']);payload={k:v for k,v in d.items() if k!='session_sha256'};d['session_sha256']=digest(payload);atomic(self.session_root/d['session_id']/'session.json',d);return d
 def _path(self,sid):
  if not re.fullmatch(r'dialogue-freetext-[0-9a-f-]{36}',sid):raise FreeTextConflict('session_id FreeText inválido')
  return self.session_root/sid/'session.json'
 def load(self,sid):
  path=self._path(sid)
  if not path.is_file():raise FreeTextConflict('sesión FreeText no encontrada')
  d=json.loads(path.read_text());payload={k:v for k,v in d.items() if k!='session_sha256'}
  if digest(payload)!=d.get('session_sha256') or digest(d.get('state'))!=d.get('state_sha256') or d.get('session_id')!=sid:raise FreeTextConflict('sesión FreeText corrupta')
  for stage in d['state'].get('stages',[]):
   validate_full_ranking(stage['ranking'],set(d['state']['candidate_universe']))
   if digest(stage['ranking'])!=stage['ranking_sha256']:raise FreeTextConflict('ranking FreeText corrupto')
  return d
 def start(self,query_id,description):
  lock=self.session_root/'.authorization.lock'
  with lock.open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);path,a,plan=self._validate_authorization(query_id,description)
   if self._used(a['authorization_id']):raise FreeTextConflict('autorización FreeText consumida')
   sid=f'dialogue-freetext-{uuid.uuid4()}';d={'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-session-v1','session_id':sid,'policy_id':'dialogue-vpr-freetext-v1','experimental_query_id':query_id,'source_query_id':a['source_query_id'],'description_es':description,'description_sha256':a['description_sha256'],'image_url':'/api/v1/dialogue-freetext/pilot/image','authorization':{'authorization_id':a['authorization_id'],'authorization_sha256':sha256_file(path),'consumed':True,'reusable_for_other_session':False,'session_id':sid},'state':{'status':'running','turns':[],'stages':[]},'status':'running','stop_reason':None,'created_at_utc':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')};self._persist(d)
  try:d['state']=self.executor.start(query_id=query_id,description=description,session_root=self._path(sid).parent);d['status']=d['state']['status'];d['stop_reason']=d['state'].get('stop_reason')
  except Exception as e:d['status']='failed';d['stop_reason']='runtime_error_no_retry';d['failure']={'stage':'start','error_type':type(e).__name__};self._persist(d);raise
  return self._persist(d)
 def answer(self,sid,answer):
  d=self.load(sid)
  if d['status']!='awaiting_answer':raise FreeTextConflict('sesión FreeText no espera respuesta')
  d['pending_answer']={'literal':answer,'sha256':hashlib.sha256(answer.encode()).hexdigest(),'human_attested':True,'external_context_used':False};d['status']='running';self._persist(d)
  try:d['state']=self.executor.answer(state=d['state'],answer=answer,answer_kind='free_text',session_root=self._path(sid).parent);d.pop('pending_answer',None);d['status']=d['state']['status'];d['stop_reason']=d['state'].get('stop_reason')
  except Exception as e:d['status']='failed';d['stop_reason']='runtime_error_no_retry';d['failure']={'stage':'answer','turn_index':len(d['state'].get('turns',[])),'error_type':type(e).__name__};self._persist(d);raise
  return self._persist(d)
 def public(self,d):
  state=d['state'];current=state['turns'][-1] if d['status']=='awaiting_answer' and state.get('turns') else None;turns=[{'index':x['index'],'question':x['question']['literal'],'question_sha256':x['question']['sha256'],'answer_literal':x['answer']['literal'] if x.get('answer') else None,'answer_sha256':x['answer']['sha256'] if x.get('answer') else None} for x in state.get('turns',[])]
  snapshots=[{'stage':x['stage'],'ranking_sha256':x['ranking_sha256'],'gallery_id':x['ranking'].get('gallery_id'),'candidate_count':len(x['ranking']['results']),'results':x['ranking']['results'][:10]} for x in state.get('stages',[])]
  return {'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-session-public-v1','session_id':d['session_id'],'policy_id':d['policy_id'],'experimental_query_id':d['experimental_query_id'],'source_query_id':d['source_query_id'],'description_es':d['description_es'],'description_sha256':d['description_sha256'],'image_url':d['image_url'],'status':d['status'],'stop_reason':d.get('stop_reason'),'turns':turns,'current_question':{'turn_index':current['index'],'question':current['question']['literal'],'question_sha256':current['question']['sha256'],'intent_key':current['question']['intent_key'],'family':current['question']['family'],'question_type':current['question']['question_type'],'grounding_kind':current['question']['grounding_kind']} if current else None,'stage_snapshots':snapshots,'final_stage':state.get('final_stage'),'session_sha256':d['session_sha256'],'updated_at_utc':d['updated_at_utc']}
