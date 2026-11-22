"""Servicio HTTP durable para IterativeDialogueController, sin cargar modelos implícitamente."""
from __future__ import annotations
import fcntl,hashlib,json,os,re,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping
from research.dq_pilot_iterative_controller_v1 import IterativeRunStore,digest_text
from .freetext_sessions import FreeTextConflict,FreeTextUnavailable

POLICY_ID="dialogue-vpr-dq-pilot-v1"
REVIEW_STATES={"AWAITING_PANEL_REVIEW","AWAITING_QUESTION_REVIEW","AWAITING_TRANSLATION_REVIEW"}
COMPONENTS={
 "LLM_INTERPRETATION":("qwen","Interpretando la descripción con Qwen."),
 "CT2L_RETRIEVAL":("crosstext2loc","Recuperando candidatos con CrossText2Loc."),
 "MAPILLARY_PANEL":("panel","Preparando el panel visual con el ranking actualizado."),
 "DQ_GENERATION":("dq_pilot","Generando la pregunta visual con DQ-Pilot."),
 "QUESTION_VALIDATION":("validation","Comprobando la pregunta visual."),
 "SPANISH_TRANSLATION":("translation","Traduciendo la pregunta al español."),
}
def session_status(controller_state):
 if controller_state in REVIEW_STATES:return "waiting_review"
 return {"AWAITING_USER":"waiting_user","COMPLETED":"completed","FAILED":"failed"}.get(controller_state,"running")

class DQIterativeConflict(FreeTextConflict):pass
class DQIterativeUnavailable(FreeTextUnavailable):pass
def utcnow():return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def atomic(path,document):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
 try:
  with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"wb") as stream:
   stream.write(canonical(document)+b"\n");stream.flush();os.fsync(stream.fileno())
  os.replace(tmp,path);fd=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
  try:os.fsync(fd)
  finally:os.close(fd)
 finally:tmp.unlink(missing_ok=True)
class IterativeDialogueSessionService:
 def __init__(self,*,session_root:Path,controller_factory=None,enabled:bool=False,real_inference_available:bool=False,translation_available:bool=False,quality_gate_available:bool=False,fixture_mode:bool=False,supervised_inbox:Path|None=None,historical_root:Path|None=None,host_lease_receipts:Path|None=None,final_visual_depth:int=50,cells_geojson:Path|None=None):
  if fixture_mode and real_inference_available:raise ValueError("fixture y ejecución real son excluyentes")
  if supervised_inbox is not None and not fixture_mode and controller_factory is not None:raise ValueError("el pipeline supervisado no admite un ejecutor directo")
  self.session_root=session_root;self.session_root.mkdir(parents=True,exist_ok=True);self.controller_factory=controller_factory;self.enabled=enabled;self.real_inference_available=real_inference_available;self.translation_available=translation_available;self.quality_gate_available=quality_gate_available;self.fixture_mode=fixture_mode;self._controllers={}
  self.supervisor=None
  self.historical=None
  if enabled and historical_root is not None:
   from .dq_historical_replay import HistoricalReplay
   self.historical=HistoricalReplay(historical_root)
  if enabled and supervised_inbox is not None:
   from .dq_supervised_sessions import SupervisedSessions
   self.supervisor=SupervisedSessions(self,supervised_inbox,fixture=fixture_mode,host_lease_receipts=host_lease_receipts,final_visual_depth=final_visual_depth,cells_geojson=cells_geojson)
 @property
 def executable(self):return self.enabled and self.controller_factory is not None and (self.real_inference_available or self.fixture_mode) and self.translation_available and self.quality_gate_available
 def policy(self):return {"schema_version":"1.0","contract_version":"atlas-dialogue-freetext-policy-public-v1","policy_id":POLICY_ID,"version":"1.0.0","status":"available" if self.executable else "blocked","available":self.executable,"enabled":self.enabled,"provisional":True,"description_length":"arbitrary","input_language":"es","requires_cohort":False,"requires_image":True,"maximum_questions":3,"stages":["E0","E1","E2","E3"],"ground_truth":False,"vlm":True,"execution_mode":"cpu_fixture" if self.fixture_mode else "real" if self.executable else "prepare_only","translation_mode":{"mode":"PILOT_TRANSLATION_UNVALIDATED","enabled_for_preparation":True,"formal_translation_validated":False,"per_question_human_acceptance_required":True},"execution_readiness":{"runtime_connected":self.controller_factory is not None,"artifacts_ready":self.real_inference_available,"authorization_ready":self.real_inference_available,"translation_ready":self.translation_available,"quality_gate_ready":self.quality_gate_available},"blockers":{"real_inference":not self.real_inference_available,"translation":not self.translation_available,"quality_gate":not self.quality_gate_available}}
 def _path(self,session_id):
  if not re.fullmatch(r"dq-iterative-[0-9a-f-]{36}",session_id):raise DQIterativeConflict("session_id iterativo inválido")
  return self.session_root/session_id
 def _metadata(self,session_id):return self._path(session_id)/"session.json"
 def _events(self,session_id):return self._path(session_id)/"events.json"
 def _load_meta(self,session_id):
  path=self._metadata(session_id)
  if not path.is_file():raise DQIterativeConflict("sesión iterativa no encontrada")
  document=json.loads(path.read_text());expected=digest({k:v for k,v in document.items() if k!="session_sha256"})
  if document.get("session_sha256")!=expected:raise DQIterativeConflict("sesión iterativa corrupta")
  return document
 def _persist_meta(self,document):
  document["updated_at_utc"]=utcnow();document["session_sha256"]=digest({k:v for k,v in document.items() if k!="session_sha256"});atomic(self._metadata(document["session_id"]),document);return document
 def _append_event(self,meta,stage,state,message,error_code=None):
  path=self._events(meta["session_id"]);rows=json.loads(path.read_text()) if path.is_file() else [];row={"event_id":str(len(rows)+1),"stage":stage,"state":state,"message":message,"error_code":error_code,"created_at_utc":utcnow()};rows.append(row);atomic(path,rows);return row
 def _operation(self,session_id,kind,operation_id,body,*,reserve=True):
  root=self._path(session_id)/"operations";key=hashlib.sha256(operation_id.encode()).hexdigest();path=root/f"{kind}-{key}.json";body_sha=digest(body)
  if path.exists():
   row=json.loads(path.read_text());
   if row["body_sha256"]!=body_sha:raise DQIterativeConflict("Idempotency-Key reutilizada con otro cuerpo")
   return row,False
  if not reserve:return None,True
  row={"kind":kind,"operation_id_sha256":key,"body_sha256":body_sha,"status":"reserved","created_at_utc":utcnow()};atomic(path,row);return row,True
 def prepare_start(self,description,client_operation_id,idempotency_key):
  if not self.executable:raise DQIterativeUnavailable("DQ-Pilot iterativo bloqueado por traducción/calidad/autorización")
  if not isinstance(description,str) or not 3<=len(description)<=2400 or client_operation_id!=idempotency_key or client_operation_id.startswith('dq-replay-'):raise DQIterativeConflict("inicio iterativo inválido")
  index=self.session_root/"create-operations";index.mkdir(exist_ok=True);key=hashlib.sha256(client_operation_id.encode()).hexdigest();pointer=index/f"{key}.json";body={"description_es":description,"client_operation_id":client_operation_id}
  if pointer.exists():
   row=json.loads(pointer.read_text());
   if row["body_sha256"]!=digest(body):raise DQIterativeConflict("operación create reutilizada")
   return self._load_meta(row["session_id"]),False
  session_id=f"dq-iterative-{uuid.uuid4()}";root=self._path(session_id);root.mkdir(mode=0o700);controller,identities=self.controller_factory(session_id,description);IterativeRunStore.prepare(root/"run",session_id=session_id,query_id=session_id,original_description=description,top_n=20,identities=identities);self._controllers[session_id]=controller;meta={"schema_version":"1.0","contract_version":"atlas-dq-iterative-session-v1","session_id":session_id,"policy_id":POLICY_ID,"description_es":description,"description_sha256":digest_text(description),"status":"pending","stop_reason":None,"created_at_utc":utcnow(),"controller_root":"run","current_operation":client_operation_id,"expected_generation":0}
  meta["execution_mode"]="cpu_fixture" if self.fixture_mode else "real"
  if self.fixture_mode:meta["gpu_used"]=False
  self._persist_meta(meta);atomic(pointer,{"session_id":session_id,"body_sha256":digest(body)});self._append_event(meta,"session","pending","Sesión DQ-Pilot persistida antes de E0.");return meta,True
 def prepare_waiting_authorization(self,description,client_operation_id,idempotency_key):
  if not self.enabled or not isinstance(description,str) or not 3<=len(description)<=2400 or client_operation_id!=idempotency_key or not client_operation_id or client_operation_id.startswith('dq-replay-'):raise DQIterativeConflict("preparación iterativa inválida")
  index=self.session_root/"create-operations";index.mkdir(exist_ok=True);key=hashlib.sha256(client_operation_id.encode()).hexdigest();pointer=index/f"{key}.json";body={"mode":"prepare_only","description_es":description,"client_operation_id":client_operation_id}
  if pointer.exists():
   row=json.loads(pointer.read_text());
   if row["body_sha256"]!=digest(body):raise DQIterativeConflict("operación prepare reutilizada")
   return self._load_meta(row["session_id"]),False
  session_id=f"dq-iterative-{uuid.uuid4()}";self._path(session_id).mkdir(mode=0o700);meta={"schema_version":"1.0","contract_version":"atlas-dq-iterative-session-v1","session_id":session_id,"policy_id":POLICY_ID,"description_es":description,"description_sha256":digest_text(description),"status":"waiting_authorization","stop_reason":None,"created_at_utc":utcnow(),"controller_root":None,"current_operation":client_operation_id,"expected_generation":0,"preparation_status":"PREPARED","current_stage":"QWEN_E0","gpu_used":False,"search_executed":False,"rankings_available":False};self._persist_meta(meta);atomic(pointer,{"session_id":session_id,"body_sha256":digest(body)});self._append_event(meta,"authorization_qwen_e0","waiting_authorization","Sesión persistida sin inferencia; espera autorización Qwen E0.");return meta,True
 def run_start(self,session_id):return self._transition(session_id,lambda controller,store:controller.start(store),"E0")
 def prepare_answer(self,session_id,*,answer,turn_index,question_id,question_sha256,client_operation_id,idempotency_key,user_requests_stop=False):
  if client_operation_id!=idempotency_key or not answer.strip() or len(answer)>1200:raise DQIterativeConflict("respuesta iterativa inválida")
  meta=self.load(session_id)
  if meta.get('execution_mode')=='historical_replay':
   from .dq_historical_replay import record_answer
   return record_answer(self,session_id,answer=answer,turn_index=turn_index,question_id=question_id,question_sha256=question_sha256,client_operation_id=client_operation_id,idempotency_key=idempotency_key,user_requests_stop=user_requests_stop),False
  if supervisor:=self._supervised_or_none(meta):
   return supervisor.answer(session_id,answer=answer,turn_index=turn_index,question_id=question_id,question_sha256=question_sha256,operation_id=client_operation_id,user_requests_stop=user_requests_stop),False
  lock=self._path(session_id)/".transition.lock"
  with lock.open("a+b") as handle:
   fcntl.flock(handle,fcntl.LOCK_EX);meta=self._load_meta(session_id);public=self.public(meta);current=public.get("current_question");body={"answer":answer,"turn_index":turn_index,"question_id":question_id,"question_sha256":question_sha256,"client_operation_id":client_operation_id,"user_requests_stop":user_requests_stop};_,execute=self._operation(session_id,"answer",client_operation_id,body,reserve=False)
   if not execute:return meta,False
   if meta["status"]!="waiting_user" or not current or current["turn_index"]!=turn_index or (question_id and current["question_id"]!=question_id) or (question_sha256 and current["question_sha256"]!=question_sha256):raise DQIterativeConflict("respuesta ligada a otra pregunta")
   if session_id not in self._controllers:raise DQIterativeUnavailable("runtime iterativo no residente; la respuesta no se reservó")
   self._operation(session_id,"answer",client_operation_id,body)
   meta["status"]="running";meta["pending_answer"]={"literal":answer,"turn_index":turn_index,"question_sha256":current["question_sha256"],"user_requests_stop":user_requests_stop};meta["current_operation"]=client_operation_id;self._persist_meta(meta);self._append_event(meta,f"E{turn_index}","running",f"E{turn_index} iniciado con respuesta humana persistida.");return meta,True
 def run_answer(self,session_id):
  meta=self._load_meta(session_id);pending=meta.get("pending_answer");
  if not pending:raise DQIterativeConflict("respuesta pendiente ausente")
  return self._transition(session_id,lambda controller,store:controller.answer(store,answer_literal=pending["literal"],user_requests_stop=pending["user_requests_stop"]),f"E{pending['turn_index']}")
 def stop(self,session_id,**kwargs):return self.prepare_answer(session_id,user_requests_stop=True,**kwargs)
 def cancel_waiting_authorization(self,session_id,*,operation_id,reason="user_cancelled_incomplete_description"):
  lock=self._path(session_id)/".transition.lock"
  with lock.open("a+b") as handle:
   fcntl.flock(handle,fcntl.LOCK_EX);meta=self._load_meta(session_id);body={"session_id":session_id,"reason":reason,"operation_id":operation_id};_,execute=self._operation(session_id,"cancel",operation_id,body,reserve=False)
   if not execute:return meta
   if meta["status"]!="waiting_authorization" or meta.get("gpu_used") is not False or meta.get("search_executed") is not False or meta.get("rankings_available") is not False or meta.get("controller_root") is not None:raise DQIterativeConflict("sesión no cancelable antes de inferencia")
   self._operation(session_id,"cancel",operation_id,body)
   invalidated=[];auth_root=self._path(session_id)/"authorizations"
   if auth_root.is_dir():
    for path in sorted(auth_root.glob("*.pending.json")):
     document=json.loads(path.read_text());atomic(path,{**document,"status":"INVALIDATED_BY_SESSION_CANCELLATION","approved":False,"gpu_authorized":False,"invalidated_at_utc":utcnow(),"invalidated_reason":reason});invalidated.append(path.name)
   cancellation={"schema_version":"1.0","contract_version":"dq-pilot28-session-cancellation-v1","session_id":session_id,"previous_status":"waiting_authorization","reason":reason,"operation_id_sha256":hashlib.sha256(operation_id.encode()).hexdigest(),"gpu_used":False,"search_executed":False,"rankings_available":False,"invalidated_pending_authorizations":invalidated,"cancelled_at_utc":utcnow()};atomic(self._path(session_id)/"cancellation.json",cancellation);meta["status"]="cancelled";meta["preparation_status"]="CANCELLED";meta["current_stage"]=None;meta["stop_reason"]=reason;meta["cancelled_at_utc"]=cancellation["cancelled_at_utc"];meta["invalidated_pending_authorizations"]=invalidated;self._persist_meta(meta);self._append_event(meta,"session","cancelled","Sesión cancelada antes de autorización e inferencia.");return meta
 def _transition(self,session_id,operation,stage):
  lock=self._path(session_id)/".transition.lock"
  with lock.open("a+b") as handle:
   fcntl.flock(handle,fcntl.LOCK_EX);meta=self._load_meta(session_id);controller=self._controllers.get(session_id)
   if controller is None:raise DQIterativeUnavailable("runtime iterativo no residente tras restart; no se reintenta automáticamente")
   store=self._observed_store(meta)
   try:state=operation(controller,store)
   except Exception as error:meta["status"]="failed";meta["stop_reason"]="iterative_transition_failed_no_retry";meta["failure"]={"type":type(error).__name__,"message":str(error)[:500]};self._persist_meta(meta);self._append_event(meta,stage,"failed","Transición DQ-Pilot falló; no se reintenta.","DQ_ITERATIVE_FAILED");raise
   meta.pop("pending_answer",None);return self._publish_state(meta,state,stage)
 def _observed_store(self,meta):
  def on_transition(state):
   stage=f"E{state['round_index']}";current=state["controller_state"]
   if current in {"MAPILLARY_PANEL","CHECK_CONTINUATION"} and state["rounds"] and state["rounds"][-1]["round_index"]==state["round_index"] and not any(row["stage"]==f"{stage}_ranking" for row in self.events(meta["session_id"])):
    self._append_event(meta,f"{stage}_ranking","completed","Ranking completo guardado; Top-10 disponible.")
   if current in COMPONENTS:
    component,message=COMPONENTS[current];self._append_event(meta,f"{stage}_{component}","running",message)
  return IterativeRunStore(self._path(meta["session_id"])/meta["controller_root"],on_transition=on_transition)
 def _publish_state(self,meta,state,stage):
  meta["status"]=session_status(state["controller_state"]);meta["stop_reason"]=state.get("stop_reason");meta["expected_generation"]=state["generation"];self._persist_meta(meta);self._append_event(meta,stage,meta["status"],"Estado iterativo persistido.");return meta
 def load(self,session_id):return self._load_meta(session_id)
 def session_for_create_operation(self,client_operation_id):
  if client_operation_id.startswith('dq-replay-'):
   from .dq_historical_replay import replay_session_id
   meta=self.load(replay_session_id(client_operation_id))
   if meta.get('execution_mode')!='historical_replay' or meta['historical']['start_operation']!=client_operation_id:raise DQIterativeConflict('operación histórica no encontrada')
   return meta
  path=self.session_root/"create-operations"/f"{hashlib.sha256(client_operation_id.encode()).hexdigest()}.json"
  if not path.is_file():raise DQIterativeConflict("operación create iterativa no encontrada")
  return self.load(json.loads(path.read_text())["session_id"])
 def _supervised_or_none(self,meta):
  if meta.get('supervised') is None:return None
  if self.supervisor is None:raise DQIterativeUnavailable('buzón supervisado no configurado')
  return self.supervisor
 def review_panel(self,session_id,*,approved,review,operation_id):
  if supervisor:=self._supervised_or_none(self.load(session_id)):return supervisor.panel_review(session_id,approved=approved,review=review,operation_id=operation_id)
  return self._review(session_id,"panel-review",operation_id,{"approved":approved,"review":dict(review)},lambda controller,store:controller.apply_panel_review(store,approved=approved,review=review))
 def review_question(self,session_id,*,approved,review,operation_id):
  meta=self.load(session_id)
  if meta.get('execution_mode')=='historical_replay':raise DQIterativeConflict('reproducción sin operación de generación nueva')
  if supervisor:=self._supervised_or_none(meta):return supervisor.question_review(session_id,approved=approved,review=review,operation_id=operation_id)
  required={"grounded","discriminative","user_answerable","novel","single_clear_question","no_internal_reference"};checks=review.get("checks",{})
  if set(checks)!=required or any(type(value)is not bool for value in checks.values()):raise DQIterativeConflict("rúbrica perceptual incompleta")
  state=json.loads((self._path(session_id)/"run"/"state.json").read_text());round_index=state["round_index"];panel=json.loads((self._path(session_id)/"run"/"rounds"/f"round-{round_index}"/"mapillary-panel.json").read_text());expected=[row["sha256"] for row in panel["images"]]
  if review.get("image_sha256s")!=expected:raise DQIterativeConflict("revisión perceptual no está ligada a las cuatro imágenes exactas")
  effective=approved and all(checks.values());return self._review(session_id,"question-review",operation_id,{"approved":effective,"review":dict(review)},lambda controller,store:controller.apply_question_review(store,approved=effective,review=review))
 def review_translation(self,session_id,*,approved,review,operation_id):return self._review(session_id,"translation-review",operation_id,{"approved":approved,"review":dict(review)},lambda controller,store:controller.apply_translation_review(store,approved=approved,review=review))
 def decide_pilot_translation(self,session_id,*,decision,review,operation_id):
  meta=self.load(session_id)
  if meta.get('execution_mode')=='historical_replay':
   from .dq_historical_replay import decide_translation
   return decide_translation(self,session_id,decision=decision,review=review,operation_id=operation_id)
  if supervisor:=self._supervised_or_none(meta):return supervisor.translation_decision(session_id,decision=decision,review=review,operation_id=operation_id)
  return self._review(session_id,"pilot-translation-decision",operation_id,{"decision":decision,"review":dict(review)},lambda controller,store:controller.apply_pilot_translation_decision(store,decision=decision,review=review))
 def _review(self,session_id,kind,operation_id,body,apply):
  lock=self._path(session_id)/".transition.lock"
  with lock.open("a+b") as handle:
   fcntl.flock(handle,fcntl.LOCK_EX);meta=self._load_meta(session_id)
   if meta.get('execution_mode')=='historical_replay':raise DQIterativeConflict('la revisión histórica usa su propia decisión de traducción')
   _,execute=self._operation(session_id,kind,operation_id,body,reserve=False)
   if not execute:return meta
   controller=self._controllers.get(session_id)
   if controller is None:raise DQIterativeUnavailable("runtime iterativo no residente")
   self._operation(session_id,kind,operation_id,body)
   state=apply(controller,self._observed_store(meta));return self._publish_state(meta,state,f"E{state['round_index']}")
 def events(self,session_id,last_event_id=None):
  meta=self._load_meta(session_id);bridge=meta.get("supervised")
  if bridge is not None:
   # No publicar el outbox durante el renombrado/fsync del mismo snapshot.
   with (self._path(session_id)/".transition.lock").open("rb") as lock:
    fcntl.flock(lock,fcntl.LOCK_SH);rows=self._load_meta(session_id)["supervised"]["events"]
  elif meta.get('execution_mode')=='historical_replay':
   with (self._path(session_id)/'.transition.lock').open('rb') as lock:
    fcntl.flock(lock,fcntl.LOCK_SH);rows=self._load_meta(session_id)['historical']['events']
  else:rows=json.loads(self._events(session_id).read_text()) if self._events(session_id).is_file() else []
  if last_event_id is None:return rows
  return [row for row in rows if int(row["event_id"])>int(last_event_id)]
 def public(self,meta):
  if meta.get('execution_mode')=='historical_replay':
   from .dq_historical_replay import project
   return project(meta)
  root=self._path(meta["session_id"]);state_path=root/meta["controller_root"]/"state.json" if meta.get("controller_root") else None;bridge=meta.get("supervised");state=bridge["state"] if bridge is not None else json.loads(state_path.read_text()) if state_path and state_path.is_file() else {"turns":[],"rounds":[],"questions_asked":0,"round_index":0,"controller_state":"WAITING_AUTHORIZATION" if meta["status"]=="waiting_authorization" else "CANCELLED" if meta["status"]=="cancelled" else "INITIAL_DESCRIPTION"};snapshots=[]
  for round_row in state.get("rounds",[]):
   ranking=bridge["artifacts"][round_row["ranking_ref"]] if bridge is not None else json.loads((root/meta["controller_root"]/round_row["ranking_ref"]).read_text());snapshots.append({"stage":f"E{round_row['round_index']}","gallery_id":ranking.get("gallery_id","madrid-50m"),"candidate_count":len(ranking["results"]),"ranking_sha256":round_row["ranking_sha256"],"results":ranking["results"][:10]})
  turns=[{"index":turn["index"],"question":turn["question_es"],"question_id":turn.get("question_id",turn["question_es_sha256"]),"question_sha256":turn["question_es_sha256"],"answer_literal":turn["answer"]["literal"] if turn.get("answer") else None} for turn in state.get("turns",[])];pending=state.get("pending_question");current=None if meta["status"]!="waiting_user" or not pending else {"turn_index":pending["turn_index"],"question_id":pending.get("question_id",digest_text(pending["question_es"])),"question":pending["question_es"],"question_sha256":digest_text(pending["question_es"])}
  translation_review=None
  if state.get("controller_state")=="AWAITING_TRANSLATION_REVIEW" and state.get("pending_translation"):
   path=f"rounds/round-{state['round_index']}/spanish-translation.json";translation=bridge['artifacts'][path] if bridge is not None else json.loads((root/meta['controller_root']/path).read_text());translation_review={"mode":"PILOT_TRANSLATION_UNVALIDATED","source_question_en":translation["source_question"],"source_question_sha256":translation["source_question_sha256"],"translated_question_es":translation["translated_question"],"translated_question_sha256":translation["translated_question_sha256"],"translation_sha256":digest(translation),"translator":translation["translator"],"formal_translation_validated":False,"human_decision_required":True}
  visual={}
  if bridge is not None:
   from .dq_supervised_visual import visual_public
   visual=visual_public(meta,bridge)
   if 'final_visual' in bridge:
    final=bridge['final_visual'];request=final['request']
    snapshots[-1]['visual_postprocessing']={key:final[key] for key in ('status','reason','mode','model','baseline_results','final_results','evidence')}
    snapshots[-1]['visual_postprocessing'].update(contract_version=final['contract_version'],depth=request['depth'],source_ranking_sha256=request['ranking_sha256'])
  return {"schema_version":"1.0","contract_version":"atlas-dq-iterative-session-public-v1","session_id":meta["session_id"],"policy_id":POLICY_ID,"description_es":meta["description_es"],"accumulated_description_es":state.get("accumulated_description",meta["description_es"]),"execution_mode":meta.get("execution_mode","prepare_only" if not meta.get("controller_root") else "unconfirmed"),"supervised":bridge is not None,"status":meta["status"],"stop_reason":meta.get("stop_reason"),"turns":turns,"current_question":current,"pending_translation_review":translation_review,"stage_snapshots":snapshots,"final_stage":snapshots[-1]["stage"] if snapshots else None,"maximum_questions":3,"controller_state":state.get("controller_state"),"round_index":state.get("round_index"),"preparation_status":meta.get("preparation_status"),"current_stage":meta.get("current_stage"),"gpu_used":meta.get("gpu_used"),"search_executed":meta.get("search_executed"),"rankings_available":meta.get("rankings_available"),"session_sha256":meta["session_sha256"],"updated_at_utc":meta["updated_at_utc"],**visual}
