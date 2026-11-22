"""Supervisor CT2L v3 con universo independiente del orden y scores estrictos."""
from __future__ import annotations
import hashlib,json,math,os,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping,Sequence
from research.dialogue_transition_runner_dqdev2 import DialogueTransitionError,canonical

def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def sha(path:Path)->str:
 d=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):d.update(block)
 return d.hexdigest()
def atomic(path:Path,doc:Mapping[str,Any]):
 payload=canonical(doc)+b'\n';path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  if path.read_bytes()!=payload:raise DialogueTransitionError('checkpoint divergente')
  return
 tmp=path.with_name('.'+path.name+f'.{os.getpid()}.tmp')
 try:
  with tmp.open('xb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path);fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
 finally:tmp.unlink(missing_ok=True)
def bounded(value:str,limit:int=16384)->dict[str,Any]:
 raw=value.encode();return {'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'truncated':len(raw)>limit,'text':raw[:limit].decode(errors='replace')}
def redact(command:Sequence[str])->list[str]:
 secret_flags={'--token','--password','--secret','--api-key'};out=[];hide=False
 for value in command:
  if hide:out.append('[REDACTED]');hide=False
  else:out.append(value);hide=value in secret_flags
 return out
def _ids(ids:Sequence[str])->list[str]:
 if isinstance(ids,(str,bytes)) or not isinstance(ids,Sequence) or any(type(x) is not str or not x for x in ids) or len(set(ids))!=len(ids):raise DialogueTransitionError('candidate IDs inválidos')
 return list(ids)
def candidate_id_set_sha256(ids:Sequence[str])->str:return hashlib.sha256(canonical(sorted(_ids(ids)))).hexdigest()
def ranking_order_sha256(ids:Sequence[str])->str:return hashlib.sha256(canonical(_ids(ids))).hexdigest()
def validate_ranking(doc:Mapping[str,Any],*,call_id:str,expected_candidate_set_sha256:str,expected_candidate_count:int=253)->dict[str,Any]:
 if not isinstance(doc,Mapping) or doc.get('call_id')!=call_id:raise DialogueTransitionError('call_id de ranking divergente')
 if doc.get('gallery_id')!='madrid-50m' or doc.get('ranking_method')!='exhaustive_cosine':raise DialogueTransitionError('galería o método de ranking divergente')
 if type(doc.get('candidate_count')) is not int or doc['candidate_count']!=expected_candidate_count:raise DialogueTransitionError('candidate_count divergente')
 rows=doc.get('results')
 if not isinstance(rows,list) or len(rows)!=expected_candidate_count or any(not isinstance(x,Mapping) for x in rows):raise DialogueTransitionError('ranking incompleto')
 ranks=[x.get('rank') for x in rows]
 if any(type(x) is not int for x in ranks) or ranks!=list(range(1,expected_candidate_count+1)):raise DialogueTransitionError('ranks no consecutivos')
 ids=[x.get('candidate_id') for x in rows];_ids(ids);observed_set=candidate_id_set_sha256(ids)
 if observed_set!=expected_candidate_set_sha256:raise DialogueTransitionError('universo de ranking divergente')
 scores=[];ties=0
 for index,row in enumerate(rows):
  score=row.get('cosine_similarity')
  if type(score) not in (int,float) or (type(score) is float and not math.isfinite(score)) or not -1<=score<=1:raise DialogueTransitionError('score ausente, no numérico, no finito o fuera de rango')
  for field,low,high in (('latitude',-90,90),('longitude',-180,180)):
   value=row.get(field)
   if type(value) not in (int,float) or (type(value) is float and not math.isfinite(value)) or not low<=value<=high:raise DialogueTransitionError(f'{field} inválida')
  scores.append(score)
  if index:
   previous=scores[index-1]
   if score>previous:raise DialogueTransitionError('scores no monótonos')
   if score==previous:
    ties+=1
    if ids[index]<ids[index-1]:raise DialogueTransitionError('tie-break candidate_id_ascending incumplido')
 return {'candidate_count':expected_candidate_count,'candidate_id_set_sha256':observed_set,'ranking_order_sha256':ranking_order_sha256(ids),'scores_sha256':hashlib.sha256(canonical(scores)).hexdigest(),'scores_finite':True,'scores_non_increasing':True,'exact_tie_count':ties,'tie_break':'candidate_id_ascending','positions':[{'rank':row['rank'],'candidate_id':row['candidate_id'],'cosine_similarity':row['cosine_similarity']} for row in rows]}
def run_once(*,root:Path,attempt:Mapping[str,Any],command:Sequence[str],ranking_path:Path,expected_candidate_set_sha256:str,expected_candidate_count:int=253,timeout:int=240,executor=subprocess.run)->dict[str,Any]:
 attempt_path=root/'attempt.json';supervisor_path=root/'supervisor.json'
 if attempt_path.exists():
  existing=json.loads(attempt_path.read_text())
  if existing!=attempt:raise DialogueTransitionError('output reservado por otro intento')
  if supervisor_path.exists():return json.loads(supervisor_path.read_text())
  raise DialogueTransitionError('autorización consumida por intento no terminal')
 atomic(attempt_path,attempt);started=now();tick=time.perf_counter();status='FAILED';kind='PROCESS_INIT_FAILED';stdout='';stderr='';returncode=None;timed_out=False;validation=None
 try:
  result=executor(list(command),capture_output=True,text=True,timeout=timeout);stdout=result.stdout or '';stderr=result.stderr or '';returncode=result.returncode;kind=('MODEL_INIT_FAILED' if 'MODEL_INIT_STARTED' in stderr else 'WORKER_PRE_MODEL_FAILED') if returncode else 'OUTPUT_MISSING'
  if returncode==0 and ranking_path.is_file():
   try:validation=validate_ranking(json.loads(ranking_path.read_text()),call_id=attempt['call_id'],expected_candidate_set_sha256=expected_candidate_set_sha256,expected_candidate_count=expected_candidate_count);status='SUCCEEDED';kind=None
   except Exception as error:kind='OUTPUT_CONTRACT_INVALID';stderr+=(('\n' if stderr else '')+f'{type(error).__name__}: {error}')
 except subprocess.TimeoutExpired as error:timed_out=True;kind='WORKER_TIMEOUT';stdout=(error.stdout or '') if isinstance(error.stdout,str) else '';stderr=(error.stderr or '') if isinstance(error.stderr,str) else ''
 except KeyboardInterrupt:kind='INTERRUPTED';stderr='KeyboardInterrupt'
 except BaseException as error:kind='PROCESS_INIT_FAILED';stderr=f'{type(error).__name__}: {error}'
 doc={'schema_version':'1.0','contract_version':'dq-dev51-ct2l-supervisor-v3','attempt_id':attempt['attempt_id'],'call_id':attempt['call_id'],'authorization_sha256':attempt['authorization_sha256'],'request_sha256':attempt['request_sha256'],'status':status,'failure_kind':kind,'started_at_utc':started,'finished_at_utc':now(),'duration_ms':(time.perf_counter()-tick)*1000,'command':redact(command),'cwd':str(Path.cwd()),'returncode':returncode,'timed_out':timed_out,'stdout':bounded(stdout),'stderr':bounded(stderr),'artifacts':{'request':{'path':attempt['request_path'],'sha256':attempt['request_sha256']},'ranking':{'path':str(ranking_path),'exists':ranking_path.is_file(),'sha256':sha(ranking_path) if ranking_path.is_file() else None}},'validation':validation,'automatic_retries':0};atomic(supervisor_path,doc);return doc
