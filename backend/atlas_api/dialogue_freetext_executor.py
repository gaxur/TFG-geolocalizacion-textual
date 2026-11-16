"""Adaptador runtime real y aislado de DialogueVPR-FreeText-v1."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any,Mapping,Sequence
from backend.atlas_api.dialogue_executor import SequentialDialogueExecutor
from backend.atlas_api.dialogue_sessions import atomic_write
from src.tfg_phase0.dialogue_freetext_v1 import FreeTextDialogueExecutor,FreeTextQuestion,digest_text,select_freetext_question
from src.tfg_phase0.interactive_dialogue import DialoguePolicyConfig

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
  index=int(stage[1:]);request={'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-qwen-worker-request-v1','stage':stage,'transcript':transcript,'transcript_sha256':digest_text(transcript),'prompt':prompt,'prompt_version':'dialogue-vpr-freetext-qwen-v1','prompt_sha256':digest_text(prompt)};request_path=self.root/f'freetext-qwen-request-{index}.json';output=self.root/f'freetext-en-{index}.json';atomic_write(request_path,request);self.owner._emit(stage,'qwen','running');self.owner._gate(self.root,f'freetext-qwen-{index}');self.owner._run([self.owner.python,str(Path(__file__).resolve().parents[2]/'scripts/run_dialogue_freetext_worker.py'),'--request',str(request_path),'--model',str(self.owner.qwen_model),'--output',str(output)],self.root,f'freetext-qwen-{index}',360);document=json.loads(output.read_text());self.owner._emit(stage,'qwen','completed');return document
class RuntimeRetrievalPort:
 def __init__(self,owner,root):self.owner=owner;self.root=root
 def retrieve(self,*,stage:str,query_id:str,text:str):
  index=int(stage[1:]);english={'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()};self.owner._emit(stage,'crosstext2loc','running');result=self.owner._ct2l(query_id=query_id,round_index=index,english=english,root=self.root);self.owner._emit(stage,'crosstext2loc','completed');return result

class FreeTextRuntimeExecutor(SequentialDialogueExecutor):
 policy_id='dialogue-vpr-freetext-v1'
 def __init__(self,**kwargs):
  super().__init__(**kwargs);raw=json.loads((Path(__file__).resolve().parents[2]/'config/interactive_dialogue_freetext_v1.json').read_text());self.policy=DialoguePolicyConfig(reserve_size=raw['reserve_size'],cluster_radius_m=raw['cluster_radius_m'],minimum_hypotheses=raw['minimum_hypotheses'],minimum_supported_hypotheses=raw['minimum_supported_hypotheses'],maximum_supported_fraction=raw['maximum_supported_fraction'],allow_qwen_question=False,enable_controlled_rewrite=False);self.max_questions=raw['maximum_questions'];self.progress_callback=None;self._identity,self._identity_stats=self._build_identity()
 def _emit(self,stage,component,state):
  if self.progress_callback:self.progress_callback(stage,component,state)
 @property
 def identity(self):
  current=self._build_identity()[0]
  if current!=self._identity:raise RuntimeError('artefactos del ejecutor FreeText modificados')
  return dict(self._identity)
 def _artifact_paths(self):
  root=Path(__file__).resolve().parents[2];return [root/'backend/atlas_api',root/'src/tfg_phase0',root/'scripts/run_dialogue_freetext_worker.py',root/'scripts/run_mvp_dialogue_worker.py',root/'config/interactive_dialogue_freetext_v1.json',self.runtime_config,self.region_config,self.f3_bundle,self.clip_weights,self.qwen_model]
 def _artifact_stats(self):
  rows={}
  for path in self._artifact_paths():
   items=[path] if path.is_file() else sorted(candidate for candidate in path.rglob('*') if candidate.is_file())
   for item in items:
    stat=item.stat();rows[str(item)]=(stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
  return rows
 def _build_identity(self):
  base=super().identity;root=Path(__file__).resolve().parents[2];qwen_files={name:self.qwen_model/name for name in ('config.json','model.safetensors.index.json','tokenizer_config.json')};missing=[name for name,path in qwen_files.items() if not path.is_file()]
  if missing:raise RuntimeError(f"identidad Qwen incompleta: {', '.join(missing)}")
  weights=sorted(self.qwen_model.glob('*.safetensors'));base.update({'atlas_api_tree_sha256':_artifact_digest(root/'backend/atlas_api'),'phase0_tree_sha256':_artifact_digest(root/'src/tfg_phase0'),'freetext_executor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'freetext_core_sha256':hashlib.sha256((root/'src/tfg_phase0/dialogue_freetext_v1.py').read_bytes()).hexdigest(),'freetext_worker_sha256':hashlib.sha256((root/'scripts/run_dialogue_freetext_worker.py').read_bytes()).hexdigest(),'freetext_policy_sha256':hashlib.sha256((root/'config/interactive_dialogue_freetext_v1.json').read_bytes()).hexdigest(),'runtime_config_sha256':_artifact_digest(self.runtime_config),'region_config_sha256':_artifact_digest(self.region_config),'f3_bundle_sha256':_artifact_digest(self.f3_bundle),'clip_weights_sha256':_artifact_digest(self.clip_weights),'qwen_config_sha256':_artifact_digest(qwen_files['config.json']),'qwen_weight_index_sha256':_artifact_digest(qwen_files['model.safetensors.index.json']),'qwen_tokenizer_config_sha256':_artifact_digest(qwen_files['tokenizer_config.json']),'qwen_snapshot_sha256':_artifact_digest(self.qwen_model),'qwen_model_artifacts':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in weights},'python_executable_sha256':_artifact_digest(Path(self.python)),'qwen_model_id':'Qwen/Qwen3-8B','qwen_model_revision':'b968826d9c46dd6066d109eabc6255188de91218','cvg_utils_sha256':self.cvg_utils_sha256});return base,self._artifact_stats()
 def _core(self,root):return FreeTextDialogueExecutor(qwen=RuntimeQwenPort(self,root),retriever=RuntimeRetrievalPort(self,root),questions=RuntimeQuestionPort(self))
 def start(self,*,query_id,description,session_root):return self._core(session_root).start(query_id=query_id,description=description)
 def answer(self,*,state,answer,answer_kind,session_root):return self._core(session_root).answer(state=state,answer_literal=answer)
