"""Transacción durable de una generación DQ-Pilot, con raw privado pre-validación."""
from __future__ import annotations
import hashlib,json,os,uuid
from pathlib import Path
from typing import Any,Callable,Mapping

class GenerationTransactionError(RuntimeError):
 def __init__(self,code:str,stage:str,message:str):self.code=code;self.stage=stage;super().__init__(message)
def canonical(value:Any)->bytes:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha_bytes(value:bytes)->str:return hashlib.sha256(value).hexdigest()
def sha_file(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
class DurableJsonWriter:
 def __init__(self,fault:Callable[[str],None]|None=None):self.fault=fault or (lambda stage:None)
 def write_once(self,path:Path,document:Mapping[str,Any],*,mode:int,stage:str)->str:
  payload=canonical(document)+b"\n";expected=sha_bytes(payload);path.parent.mkdir(parents=True,exist_ok=True);os.chmod(path.parent,0o700 if "private" in path.parent.parts else 0o700)
  if path.exists():
   if path.is_symlink() or not path.is_file() or sha_file(path)!=expected:raise GenerationTransactionError("ARTIFACT_DIVERGENT",stage,"destino durable divergente")
   return expected
  temporary=path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
  try:
   self.fault(stage+":open");fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
   with os.fdopen(fd,"wb") as stream:
    self.fault(stage+":write");stream.write(payload);stream.flush();self.fault(stage+":fsync_file");os.fsync(stream.fileno())
   os.chmod(temporary,mode);self.fault(stage+":rename")
   if path.exists():raise GenerationTransactionError("ARTIFACT_RACE",stage,"destino apareció durante publicación")
   os.replace(temporary,path);os.chmod(path,mode);self.fault(stage+":fsync_dir");directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
   try:os.fsync(directory)
   finally:os.close(directory)
  except GenerationTransactionError:raise
  except Exception as error:raise GenerationTransactionError("PERSISTENCE_FAILED",stage,type(error).__name__) from error
  finally:temporary.unlink(missing_ok=True)
  if sha_file(path)!=expected:raise GenerationTransactionError("INTEGRITY_FAILED",stage,"hash post-publicación divergente")
  return expected
 def replace_state(self,path:Path,document:Mapping[str,Any],*,stage:str)->str:
  payload=canonical(document)+b"\n";temporary=path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp");path.parent.mkdir(parents=True,exist_ok=True);os.chmod(path.parent,0o700)
  try:
   self.fault(stage+":open");fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,"wb") as stream:self.fault(stage+":write");stream.write(payload);stream.flush();self.fault(stage+":fsync_file");os.fsync(stream.fileno())
   self.fault(stage+":rename");os.replace(temporary,path);os.chmod(path,0o600);self.fault(stage+":fsync_dir");directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
   try:os.fsync(directory)
   finally:os.close(directory)
  except Exception as error:raise GenerationTransactionError("JOURNAL_PERSISTENCE_FAILED",stage,type(error).__name__) from error
  finally:temporary.unlink(missing_ok=True)
  return sha_bytes(payload)
class GenerationTransaction:
 STATES=("RESERVED","GENERATE_STARTED","PRIVATE_RAW_COMMITTED","VALIDATION_STARTED","HOST_ACCEPTED","HOST_REJECTED","PUBLIC_PROJECTION_COMMITTED","TERMINAL_COMMITTED","UNCERTAIN")
 def __init__(self,root:Path,*,request_sha256:str,request_id:str,writer:DurableJsonWriter|None=None):self.root=root;self.request_sha256=request_sha256;self.request_id=request_id;self.writer=writer or DurableJsonWriter();self.journal_path=root/"request-journal.json"
 @classmethod
 def prepare(cls,root:Path,*,request_sha256:str,request_id:str,writer:DurableJsonWriter|None=None):
  value=cls(root,request_sha256=request_sha256,request_id=request_id,writer=writer);root.mkdir(parents=True,exist_ok=True);os.chmod(root,0o700)
  if not value.journal_path.exists():value._state("RESERVED")
  else:value._validate_journal()
  return value
 def journal(self)->dict[str,Any]:return json.loads(self.journal_path.read_text())
 def _validate_journal(self):
  row=self.journal()
  if row.get("contract_version")!="dq-pilot-generation-journal-v1" or row.get("request_sha256")!=self.request_sha256 or row.get("request_id")!=self.request_id or row.get("state") not in self.STATES:raise GenerationTransactionError("JOURNAL_DIVERGENT","journal","journal incompatible")
 def _state(self,state:str,**refs:Any):
  if state not in self.STATES:raise ValueError(state)
  prior=self.journal() if self.journal_path.exists() else {};document={"schema_version":"1.0","contract_version":"dq-pilot-generation-journal-v1","request_id":self.request_id,"request_sha256":self.request_sha256,"state":state,"generation":int(prior.get("generation",0))+1,"refs":{**dict(prior.get("refs",{})),**refs}};self.writer.replace_state(self.journal_path,document,stage="journal:"+state);return document
 def mark_generate_started(self):return self._state("GENERATE_STARTED")
 def commit_private(self,raw:str,metrics:Mapping[str,Any])->dict[str,Any]:
  raw_hash=hashlib.sha256(raw.encode()).hexdigest();private=self.root/"private";private.mkdir(parents=True,exist_ok=True);os.chmod(private,0o700);raw_doc={"schema_version":"1.0","contract_version":"dq-pilot-private-native-output-v2","request_sha256":self.request_sha256,"raw_output":raw,"raw_output_sha256":raw_hash,"public":False,"scientific_evidence":False};raw_file_sha=self.writer.write_once(private/"native-output.json",raw_doc,mode=0o600,stage="private_raw");metadata={"schema_version":"1.0","contract_version":"dq-pilot-private-generation-metadata-v1","request_sha256":self.request_sha256,"raw_output_sha256":raw_hash,"generation":dict(metrics),"private":True};metadata_sha=self.writer.write_once(private/"generation-metadata.json",metadata,mode=0o600,stage="private_metadata");commit={"schema_version":"1.0","contract_version":"dq-pilot-private-raw-commit-v1","request_sha256":self.request_sha256,"raw_output_sha256":raw_hash,"native_output_file_sha256":raw_file_sha,"generation_metadata_sha256":metadata_sha};commit_sha=self.writer.write_once(private/"raw-commit.json",commit,mode=0o600,stage="private_commit");self._state("PRIVATE_RAW_COMMITTED",raw_commit_sha256=commit_sha,raw_output_sha256=raw_hash);return {"raw_output_sha256":raw_hash,"raw_commit_sha256":commit_sha,"private_output_sha256":raw_file_sha,"generation_metadata_sha256":metadata_sha}
 def read_private(self)->tuple[str,dict[str,Any],dict[str,Any]]:
  raw_doc=json.loads((self.root/"private/native-output.json").read_text());metadata=json.loads((self.root/"private/generation-metadata.json").read_text());commit=json.loads((self.root/"private/raw-commit.json").read_text())
  if hashlib.sha256(raw_doc["raw_output"].encode()).hexdigest()!=raw_doc["raw_output_sha256"] or commit["native_output_file_sha256"]!=sha_file(self.root/"private/native-output.json") or commit["generation_metadata_sha256"]!=sha_file(self.root/"private/generation-metadata.json"):raise GenerationTransactionError("PRIVATE_INTEGRITY_FAILED","resume","private commit divergente")
  return raw_doc["raw_output"],metadata["generation"],commit
 def validation_started(self):return self._state("VALIDATION_STARTED")
 def host_decision(self,*,decision:str,reasons:list[str],question:str|None,raw_commit_sha256:str)->dict[str,Any]:
  if decision not in {"ACCEPT","REJECT"}:raise ValueError(decision)
  doc={"schema_version":"1.0","contract_version":"dq-pilot-host-decision-v1","request_sha256":self.request_sha256,"raw_commit_sha256":raw_commit_sha256,"decision":decision,"reason_codes":reasons,"public_question":question if decision=="ACCEPT" else None,"publishable":decision=="ACCEPT","validator_contract":"dq-pilot-host-outcome-v1","automatic_retry_permitted":False};digest=self.writer.write_once(self.root/"host-decision.json",doc,mode=0o600,stage="host_decision");self._state("HOST_ACCEPTED" if decision=="ACCEPT" else "HOST_REJECTED",host_decision_sha256=digest);return {**doc,"sha256":digest}
 def public_projection(self,document:Mapping[str,Any])->str:
  decision=json.loads((self.root/"host-decision.json").read_text())
  if decision.get("decision")!="ACCEPT":raise GenerationTransactionError("NOT_PUBLISHABLE","public_projection","host rechazó")
  digest=self.writer.write_once(self.root/"generation-projection.json",document,mode=0o600,stage="public_projection");self._state("PUBLIC_PROJECTION_COMMITTED",projection_sha256=digest);return digest
 def terminal(self,*,status:str)->str:
  journal=self.journal();doc={"schema_version":"1.0","contract_version":"dq-pilot-generation-terminal-commit-v1","request_sha256":self.request_sha256,"status":status,"journal_generation":journal["generation"],"refs":journal["refs"],"automatic_retry_permitted":False};digest=self.writer.write_once(self.root/"terminal-commit.json",doc,mode=0o600,stage="terminal_commit");self._state("TERMINAL_COMMITTED",terminal_commit_sha256=digest,terminal_status=status);return digest
 def resume_action(self)->str:
  state=self.journal()["state"]
  if state in {"GENERATE_STARTED","UNCERTAIN"}:return "UNCERTAIN_NO_RETRY"
  if state in {"PRIVATE_RAW_COMMITTED","VALIDATION_STARTED"}:return "RESUME_VALIDATION"
  if state=="HOST_ACCEPTED":return "RESUME_PUBLICATION"
  if state in {"HOST_REJECTED","TERMINAL_COMMITTED"}:return "RETURN_TERMINAL"
  if state=="PUBLIC_PROJECTION_COMMITTED":return "RESUME_TERMINAL_COMMIT"
  return "START_GENERATION"
 def resume_validation(self,validator:Callable[[str],Mapping[str,Any]])->dict[str,Any]:
  if self.resume_action()!="RESUME_VALIDATION":raise GenerationTransactionError("RESUME_NOT_ALLOWED","validation","raw no está committed para validar")
  raw,metrics,commit=self.read_private();self.validation_started()
  try:checked=dict(validator(raw))
  except Exception as error:
   reasons=list(getattr(error,"reasons",[type(error).__name__]));decision=self.host_decision(decision="REJECT",reasons=reasons,question=None,raw_commit_sha256=sha_file(self.root/"private/raw-commit.json"));self.terminal(status="HOST_REJECTED");return {"decision":decision,"generation":metrics,"resumed_without_generate":True}
  decision=self.host_decision(decision="ACCEPT",reasons=[],question=checked.get("public_question"),raw_commit_sha256=sha_file(self.root/"private/raw-commit.json"));return {"decision":decision,"generation":metrics,"resumed_without_generate":True}
