"""Envelope durable para ejecutar DialogueVPR v3 en fases aisladas."""
from __future__ import annotations
import ctypes,errno,fcntl,hashlib,json,os,shutil
from pathlib import Path
from typing import Any,Mapping

from jsonschema import Draft202012Validator
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json,utc_now
from .interactive_dialogue import InteractiveDialogueError
from .interactive_dialogue_multiturn import validate_multiturn_session
from .interactive_dialogue_visual import validate_visual_session

ROOT=Path(__file__).resolve().parents[2]
STATE_SCHEMA=json.loads((ROOT/'schemas/dialogue_v3_phased_state.schema.json').read_text())
CHECKPOINT_SCHEMA=json.loads((ROOT/'schemas/dialogue_v3_retrieval_checkpoint.schema.json').read_text())
FORK_SCHEMA=json.loads((ROOT/'schemas/dialogue_v3_fork_recovery.schema.json').read_text())

class PhasedRuntimeError(RuntimeError):pass

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def file_sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def immutable_json(path:Path,document:Mapping[str,Any]):
    if path.exists():
        if json.loads(path.read_text())!=document:raise PhasedRuntimeError(f'artefacto inmutable divergente: {path.name}')
        return
    atomic_write_json(path,document)

def rename_noreplace(source:Path,destination:Path):
    if os.name!='posix':raise PhasedRuntimeError('fork-recovery requiere Linux')
    libc=ctypes.CDLL(None,use_errno=True);function=getattr(libc,'renameat2',None)
    if function is None:raise PhasedRuntimeError('renameat2 no disponible')
    function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];function.restype=ctypes.c_int
    if function(-100,os.fsencode(source),-100,os.fsencode(destination),1)==0:return
    error=ctypes.get_errno()
    if error==errno.EEXIST:raise FileExistsError(error,os.strerror(error),destination)
    raise OSError(error,os.strerror(error),destination)

def fsync_directory(path:Path):
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(descriptor)
    finally:os.close(descriptor)

def copy_file_durable(source:Path,destination:Path):
    destination.parent.mkdir(parents=True,exist_ok=True)
    with source.open('rb') as input_stream,destination.open('xb') as output_stream:
        shutil.copyfileobj(input_stream,output_stream);output_stream.flush();os.fsync(output_stream.fileno())

class RunLock:
    def __init__(self,root:Path):self.path=root/'run.lock';self.stream=None
    def __enter__(self):
        self.stream=self.path.open('a+')
        try:fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:self.stream.close();raise
        return self
    def __exit__(self,*args):fcntl.flock(self.stream,fcntl.LOCK_UN);self.stream.close()

class PhasedRunStore:
    def __init__(self,root:Path):self.root=root;self.state_path=root/'state.json'
    @classmethod
    def prepare(cls,root:Path,configuration:Mapping[str,Any]):
        root.mkdir(parents=True,exist_ok=False);(root/'checkpoints').mkdir();(root/'snapshots').mkdir();(root/'attempts').mkdir();config_path=root/'configuration.json';atomic_write_json(config_path,configuration);store=cls(root);state={'schema_version':'1.0','contract_version':'dialogue-v3-phased-state-v1','session_id':configuration['session_id'],'phase':'prepared','generation':0,'configuration_sha256':file_sha(config_path),'retrieval_checkpoint':None,'session_snapshot':None,'pending_answer':None,'visual_attempt':None,'next_action':'retrieve','updated_at_utc':utc_now()};store.write_state(state);return store
    def load_state(self):
        try:value=json.loads(self.state_path.read_text())
        except Exception as error:raise PhasedRuntimeError('estado ausente o corrupto') from error
        errors=list(Draft202012Validator(STATE_SCHEMA).iter_errors(value))
        if errors:raise PhasedRuntimeError('estado incompatible: '+errors[0].message)
        return value
    def configuration(self):
        value=json.loads((self.root/'configuration.json').read_text());state=self.load_state()
        if file_sha(self.root/'configuration.json')!=state['configuration_sha256']:raise PhasedRuntimeError('configuración alterada')
        return value
    def write_state(self,state):Draft202012Validator(STATE_SCHEMA).validate(state);atomic_write_json(self.state_path,state)
    def transition(self,*,expected:set[str],phase:str,next_action:str,**changes):
        state=self.load_state()
        if state['phase'] not in expected:raise PhasedRuntimeError(f'transición no permitida desde {state["phase"]}')
        state={**state,**changes,'phase':phase,'generation':state['generation']+1,'next_action':next_action,'updated_at_utc':utc_now()};self.write_state(state);return state
    def snapshot(self,session):
        if session.get('contract_version')=='interactive-dialogue-session-v3':validate_visual_session(session)
        else:validate_multiturn_session(session)
        name=f'{self.load_state()["generation"]+1:03d}-{sha(session)}.json';path=self.root/'snapshots'/name;immutable_json(path,session);return str(path.relative_to(self.root))
    def checkpoint(self,document):
        ranking=document.get('ranking_initial',{});rows=ranking.get('results',[])
        if document.get('session_v2',{}).get('session_id')!=document.get('session_id') or document.get('candidate_ids')!=[row.get('candidate_id') for row in rows] or document.get('scores')!=[row.get('cosine_similarity') for row in rows]:raise PhasedRuntimeError('checkpoint retrieval incoherente')
        payload={k:v for k,v in document.items() if k!='checkpoint_id'};document={**document,'checkpoint_id':'dialogue-retrieval-checkpoint-sha256-'+sha(payload)};Draft202012Validator(CHECKPOINT_SCHEMA).validate(document);path=self.root/'checkpoints'/f'{document["checkpoint_id"]}.json';immutable_json(path,document);return str(path.relative_to(self.root)),document
    def load_checkpoint(self,relative):
        path=self.root/relative
        try:value=json.loads(path.read_text())
        except Exception as error:raise PhasedRuntimeError('checkpoint corrupto') from error
        Draft202012Validator(CHECKPOINT_SCHEMA).validate(value);payload={k:v for k,v in value.items() if k!='checkpoint_id'}
        if value['checkpoint_id']!='dialogue-retrieval-checkpoint-sha256-'+sha(payload):raise PhasedRuntimeError('checkpoint_id divergente')
        config=self.configuration()
        expected_description=hashlib.sha256(config['initial_description'].encode()).hexdigest()
        if value['session_id']!=config['session_id'] or value['session_label']!=config['session_label'] or value['gallery_id']!=config['gallery_id'] or value['initial_description_sha256']!=expected_description or value['configuration_sha256']!=self.load_state()['configuration_sha256'] or value['session_v2'].get('session_id')!=value['session_id']:raise PhasedRuntimeError('checkpoint pertenece a otra sesión')
        validate_multiturn_session(value['session_v2']);rows=value['ranking_initial'].get('results',[])
        if value['candidate_ids']!=[row.get('candidate_id') for row in rows] or value['scores']!=[row.get('cosine_similarity') for row in rows]:raise PhasedRuntimeError('checkpoint retrieval incoherente')
        return value
    def load_snapshot(self,relative):
        try:value=json.loads((self.root/relative).read_text())
        except Exception as error:raise PhasedRuntimeError('snapshot corrupto') from error
        if value.get('contract_version')=='interactive-dialogue-session-v3':validate_visual_session(value)
        else:validate_multiturn_session(value)
        return value

    @classmethod
    def fork_recovery(cls,source_root:Path,target_root:Path,reason:str):
        source_root=source_root.resolve();target_root=target_root.resolve()
        if not reason.strip():raise PhasedRuntimeError('motivo de recuperación vacío')
        if source_root==target_root or source_root.parent!=target_root.parent:raise PhasedRuntimeError('fork requiere runs hermanos distintos')
        source=cls(source_root)
        with RunLock(source_root):
            state=source.load_state();configuration=source.configuration()
            if state['phase']!='retrieval_failed' or state['next_action']!='review' or state['pending_answer'] is None or state['retrieval_checkpoint'] is None or state['session_snapshot'] is None or state['visual_attempt'] is not None:raise PhasedRuntimeError('run origen no es un retrieval_failed recuperable')
            checkpoint=source.load_checkpoint(state['retrieval_checkpoint']);snapshot=source.load_snapshot(state['session_snapshot'])
            answer=state['pending_answer']
            if answer.get('sha256')!=hashlib.sha256(answer.get('literal','').encode()).hexdigest() or answer.get('turn_index')!=snapshot['turns'][-1]['index'] or snapshot['turns'][-1]['answer'] is not None:raise PhasedRuntimeError('respuesta pendiente corrupta o ya consumida')
            failure_report=source_root/'turn-001-retrieval-report.json'
            if not failure_report.is_file():raise PhasedRuntimeError('informe de fallo ausente')
            failure=json.loads(failure_report.read_text());attempt=source_root/failure['attempt']
            if failure.get('status')!='retrieval_failed' or not attempt.is_dir():raise PhasedRuntimeError('procedencia del fallo incompatible')
            artifacts={}
            for name in ('preflight.json','supervisor.json'):
                path=attempt/name
                if not path.is_file():raise PhasedRuntimeError(f'artefacto de fallo ausente: {name}')
                artifacts[str(path.relative_to(source_root))]=file_sha(path)
            parent_run=str(source_root.relative_to(ROOT)) if source_root.is_relative_to(ROOT) else str(source_root);target_run=str(target_root.relative_to(ROOT)) if target_root.is_relative_to(ROOT) else str(target_root)
            payload={'parent_run':parent_run,'parent_state_sha256':file_sha(source.state_path),'parent_checkpoint_id':checkpoint['checkpoint_id'],'parent_checkpoint_sha256':file_sha(source_root/state['retrieval_checkpoint']),'parent_snapshot_sha256':file_sha(source_root/state['session_snapshot']),'parent_generation':state['generation'],'parent_failure_attempt':failure['attempt'],'parent_failure_artifacts':artifacts,'pending_answer':answer,'recovery_reason':reason,'target_run':target_run,'configuration_sha256':state['configuration_sha256'],'authorizations_reused':False}
            fork_id='dialogue-fork-recovery-sha256-'+sha(payload)
            if target_root.exists():
                target=cls(target_root);lineage=json.loads((target_root/'lineage.json').read_text())
                expected={key:value for key,value in lineage.items() if key not in {'status','created_at_utc','schema_version','contract_version','fork_id'}}
                if lineage.get('fork_id')!=fork_id or expected!=payload:raise PhasedRuntimeError('destino existente incompatible')
                target.validate_recovery_fork();return target,False
            stage=target_root.with_name('.'+target_root.name+f'.fork-{os.getpid()}')
            if stage.exists():shutil.rmtree(stage)
            try:
                stage.mkdir();(stage/'checkpoints').mkdir();(stage/'snapshots').mkdir();(stage/'attempts').mkdir();(stage/'run.lock').touch()
                copy_file_durable(source_root/'configuration.json',stage/'configuration.json')
                checkpoint_target=stage/state['retrieval_checkpoint'];copy_file_durable(source_root/state['retrieval_checkpoint'],checkpoint_target)
                snapshot_target=stage/state['session_snapshot'];copy_file_durable(source_root/state['session_snapshot'],snapshot_target)
                lineage={'schema_version':'1.0','contract_version':'dialogue-v3-fork-recovery-v1','fork_id':fork_id,'status':'committed',**payload,'created_at_utc':utc_now()};Draft202012Validator(FORK_SCHEMA).validate(lineage);atomic_write_json(stage/'lineage.json',lineage)
                recovered={**state,'phase':'retrieved','generation':state['generation']+1,'next_action':'retrieve','updated_at_utc':utc_now()};Draft202012Validator(STATE_SCHEMA).validate(recovered);atomic_write_json(stage/'state.json',recovered)
                staged=cls(stage);staged.validate_recovery_fork();fsync_directory(stage);rename_noreplace(stage,target_root);fsync_directory(target_root.parent)
            except Exception:
                if stage.exists():shutil.rmtree(stage)
                raise
            target=cls(target_root);target.validate_recovery_fork();return target,True
    def validate_recovery_fork(self):
        state=self.load_state();configuration=self.configuration();lineage=json.loads((self.root/'lineage.json').read_text());Draft202012Validator(FORK_SCHEMA).validate(lineage)
        if state['phase']!='retrieved' or state['next_action']!='retrieve' or state['pending_answer']!=lineage['pending_answer'] or state['generation']!=lineage['parent_generation']+1 or state['configuration_sha256']!=lineage['configuration_sha256'] or state['visual_attempt'] is not None:raise PhasedRuntimeError('estado recuperado incompatible')
        checkpoint=self.load_checkpoint(state['retrieval_checkpoint']);snapshot=self.load_snapshot(state['session_snapshot'])
        if checkpoint['checkpoint_id']!=lineage['parent_checkpoint_id'] or file_sha(self.root/state['retrieval_checkpoint'])!=lineage['parent_checkpoint_sha256'] or file_sha(self.root/state['session_snapshot'])!=lineage['parent_snapshot_sha256'] or state['session_id']!=configuration['session_id'] or snapshot['session_id']!=state['session_id']:raise PhasedRuntimeError('lineage del fork divergente')
        if any((self.root/'attempts').iterdir()):raise PhasedRuntimeError('fork nuevo contiene intentos heredados')
        return {'state':state,'configuration':configuration,'lineage':lineage,'checkpoint':checkpoint,'snapshot':snapshot}

class ReplayRetriever:
    def __init__(self,checkpoint):self.checkpoint=checkpoint;self.gallery_id=checkpoint['gallery_id'];self.used=False
    @property
    def metadata(self):return dict(self.checkpoint['session_v2']['models']['retrieval'])
    def retrieve_full(self,*,query_id,text,language):
        if self.used:raise PhasedRuntimeError('replay de retrieval consumido más de una vez')
        self.used=True;return json.loads(json.dumps(self.checkpoint['session_v2']['initial_ranking']))
    def count_tokens(self,text):return None

def status_document(store:PhasedRunStore):
    state=store.load_state();active=[]
    probe=RunLock(store.root)
    try:
        with probe:pass
    except BlockingIOError:active=['phase_command_lock_held']
    interrupted=state['phase'] in {'retrieval_reserved','visual_reserved'} and not active;effective_status=f'{state["phase"]}_uncertain_after_interruption' if interrupted else state['phase'];return {'status':state['phase'],'effective_status':effective_status,'next_action':'review' if interrupted else state['next_action'],'checkpoint':state['retrieval_checkpoint'],'session_snapshot':state['session_snapshot'],'visual_attempt':state['visual_attempt'],'own_active_processes':active}
