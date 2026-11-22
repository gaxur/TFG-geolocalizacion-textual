"""Motor CPU-inyectable DQ-DEV.2 para transiciones answer y paired."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


class DialogueTransitionError(ValueError): pass
def canonical(value:Any)->bytes:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value:Any)->str:return hashlib.sha256(canonical(value)).hexdigest()
def file_sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

@dataclass(frozen=True)
class AuthorizedCall:
    call_id:str;transition_id:str;stage:str;arm:str;query_id:str;round_index:int;input_sha256:str;worker_sha256:str;model_id:str;model_revision:str;model_artifact_sha256:str

class CompilerPort(Protocol):
    def compile(self,*,call:AuthorizedCall,spanish_source:Mapping[str,Any])->Mapping[str,Any]:...
class RetrieverPort(Protocol):
    def retrieve(self,*,call:AuthorizedCall,query_id:str,text:str,language:str)->Mapping[str,Any]:...

def transition_id(plan:Mapping[str,Any])->str:return 'dialogue-transition-sha256-'+digest({k:v for k,v in plan.items() if k!='transition_id'})
def call_id(*,transition_id_value:str,stage:str,arm:str,query_id:str,round_index:int,input_sha256:str,worker_sha256:str,model_revision:str)->str:
    return 'dialogue-call-sha256-'+digest({'transition_id':transition_id_value,'stage':stage,'arm':arm,'query_id':query_id,'round_index':round_index,'input_sha256':input_sha256,'worker_sha256':worker_sha256,'model_revision':model_revision})

def validate_plan(plan:Mapping[str,Any])->None:
    if plan.get('contract_version')!='dialogue-transition-plan-v1' or plan.get('status')!='prepared_not_authorized' or plan.get('mode') not in {'answer','paired','retrieval'}:raise DialogueTransitionError('plan de transición incompatible')
    if plan.get('transition_id')!=transition_id(plan) or not str(plan.get('query_id','')).startswith('H') or not isinstance(plan.get('target_round'),int):raise DialogueTransitionError('identidad de transición divergente')
    restrictions=plan.get('restrictions',{})
    if any(restrictions.get(key) is not False for key in ('network','ground_truth','references','coordinates','vlm','h38_h61','automatic_retries')):raise DialogueTransitionError('transición permite contexto/ retry prohibido')

def expected_call(plan:Mapping[str,Any],spec:Mapping[str,Any])->AuthorizedCall:
    cid=call_id(transition_id_value=plan['transition_id'],stage=spec['stage'],arm=spec['arm'],query_id=plan['query_id'],round_index=spec['round_index'],input_sha256=spec['input_sha256'],worker_sha256=spec['worker_sha256'],model_revision=spec['model_revision'])
    return AuthorizedCall(cid,plan['transition_id'],spec['stage'],spec['arm'],plan['query_id'],spec['round_index'],spec['input_sha256'],spec['worker_sha256'],spec['model_id'],spec['model_revision'],spec['model_artifact_sha256'])

def validate_authorization(document:Mapping[str,Any],call:AuthorizedCall)->None:
    if document.get('contract_version')!='dialogue-transition-authorization-v1' or document.get('status')!='OPERATOR_AUTHORIZED' or document.get('approved') is not True or not document.get('approved_by') or not str(document.get('approved_at_utc','')).endswith('Z'):raise DialogueTransitionError('autorización de llamada ausente')
    expected={'call_id':call.call_id,'transition_id':call.transition_id,'stage':call.stage,'arm':call.arm,'query_id':call.query_id,'round_index':call.round_index,'input_sha256':call.input_sha256,'worker_sha256':call.worker_sha256,'model_id':call.model_id,'model_revision':call.model_revision,'model_artifact_sha256':call.model_artifact_sha256,'maximum_calls':1,'maximum_model_loads':1,'automatic_retries':0}
    if any(document.get('call',{}).get(key)!=value for key,value in expected.items()):raise DialogueTransitionError('autorización no corresponde a call exacta')
    if any(document.get('restrictions',{}).get(key) is not False for key in ('network','downloads','ground_truth','references','coordinates','vlm','h38_h61')):raise DialogueTransitionError('autorización permite contexto prohibido')

def _atomic(path:Path,document:Mapping[str,Any])->None:
    payload=canonical(document)+b'\n';path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=payload:raise DialogueTransitionError('artefacto existente divergente')
        return
    tmp=path.with_name('.'+path.name+'.'+str(os.getpid())+'.tmp')
    try:
        with tmp.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path);fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
    finally:tmp.unlink(missing_ok=True)

class TransitionStore:
    def __init__(self,root:Path):self.root=root
    def publish(self,name:str,document:Mapping[str,Any])->dict[str,Any]:
        path=self.root/name;_atomic(path,document);return {'logical_path':name,'sha256':file_sha(path)}
    def checkpoint(self,plan:Mapping[str,Any],index:int,step:str,inputs:Mapping[str,Any],output:Mapping[str,Any],call:str|None=None)->dict[str,Any]:
        doc={'schema_version':'1.0','contract_version':'dialogue-transition-step-v1','transition_id':plan['transition_id'],'step_index':index,'step':step,'status':'completed','inputs':dict(inputs),'output':dict(output),'call_id':call};ref=self.publish(f'checkpoints/{index:04d}-{step}.json',doc);return {**doc,'checkpoint_ref':ref}
    def completed_result(self,plan:Mapping[str,Any],mode:str)->dict[str,Any]|None:
        path=self.root/'transition-result.json'
        if not path.exists():return None
        document=json.loads(path.read_text())
        if document.get('transition_id')!=plan['transition_id'] or document.get('mode')!=mode:raise DialogueTransitionError('resultado final pertenece a otra transición')
        return document

def validate_ranking(ranking:Mapping[str,Any])->None:
    rows=ranking.get('results',[])
    if len(rows)!=253 or [x.get('rank') for x in rows]!=list(range(1,254)) or len({x.get('candidate_id') for x in rows})!=253:raise DialogueTransitionError('ranking no contiene universo 253')
    scores=[x.get('cosine_similarity') for x in rows]
    if any(not isinstance(x,(int,float)) for x in scores) or any(scores[i]<scores[i+1] for i in range(252)):raise DialogueTransitionError('scores de ranking inválidos')

def execute_answer(*,plan:Mapping[str,Any],parent_state:Mapping[str,Any],turn_package:Mapping[str,Any],response:Mapping[str,Any],spanish_source:Mapping[str,Any],store:TransitionStore)->dict[str,Any]:
    validate_plan(plan)
    completed=store.completed_result(plan,'answer')
    if completed is not None:return completed
    if plan['mode']!='answer' or parent_state.get('query_id')!=plan['query_id'] or turn_package.get('query_id')!=plan['query_id'] or response.get('query_id')!=plan['query_id']:raise DialogueTransitionError('answer mezcla consulta')
    if response.get('package_id')!=turn_package.get('package_id') or response.get('turn_index')!=turn_package.get('turn_index') or response.get('answer_sha256')!=hashlib.sha256(str(response.get('answer_literal','')).encode()).hexdigest():raise DialogueTransitionError('respuesta no corresponde a pregunta/hash')
    if plan['inputs']['parent_state_sha256']!=digest(parent_state) or plan['inputs']['turn_package_sha256']!=digest(turn_package) or plan['inputs']['response_sha256']!=digest(response) or plan['inputs']['spanish_source_sha256']!=digest(spanish_source):raise DialogueTransitionError('hash input answer divergente')
    terminal=bool(plan.get('terminal_without_inference'));decision={'schema_version':'1.0','contract_version':'dialogue-answer-decision-v1','transition_id':plan['transition_id'],'query_id':plan['query_id'],'round_index':plan['target_round'],'answer_literal':response['answer_literal'],'answer_sha256':response['answer_sha256'],'spanish_source':spanish_source,'requires_inference':not terminal,'terminal_reason':plan.get('terminal_reason') if terminal else None,'raw_response_preserved':True};ref=store.publish('artifacts/answer-decision.json',decision);store.checkpoint(plan,0,'answer_validated',{'parent':plan['inputs']['parent_state_sha256'],'response':plan['inputs']['response_sha256']},ref)
    result={'schema_version':'1.0','contract_version':'dialogue-transition-result-v1','transition_id':plan['transition_id'],'mode':'answer','status':'completed_without_inference' if terminal else 'prepared_for_authorized_inference','artifacts':{'answer_decision':ref},'executed_calls':0,'recovered_calls':0,'historical_parent_unchanged':True};store.publish('transition-result.json',result);return result

def _run_call(*,plan,call_spec,authorization,port,store,index,kind,payload):
    call=expected_call(plan,call_spec);validate_authorization(authorization,call);checkpoint=store.root/f'checkpoints/{index:04d}-{kind}.json'
    if checkpoint.exists():
        existing=json.loads(checkpoint.read_text());out=existing['output'];artifact=json.loads((store.root/out['logical_path']).read_text());return artifact,True
    artifact=port(call=call,**payload)
    if artifact.get('call_id')!=call.call_id:raise DialogueTransitionError('resultado pertenece a otra call')
    ref=store.publish(f'artifacts/{call.call_id}.json',artifact);store.checkpoint(plan,index,kind,{'input_sha256':call.input_sha256,'authorization_sha256':digest(authorization)},ref,call.call_id);return artifact,False

def execute_paired(*,plan:Mapping[str,Any],accumulation:Mapping[str,Any],authorizations:Mapping[str,Mapping[str,Any]],compiler:CompilerPort,literal_retriever:RetrieverPort,en_retriever:RetrieverPort,store:TransitionStore)->dict[str,Any]:
    validate_plan(plan)
    completed=store.completed_result(plan,'paired')
    if completed is not None:return completed
    if plan['mode']!='paired' or accumulation.get('query_id')!=plan['query_id'] or plan['inputs']['accumulation_sha256']!=digest(accumulation):raise DialogueTransitionError('paired accumulation divergente')
    rounds=[];executed=recovered=0;calls={row['call_key']:row for row in plan['calls']}
    for round_row in accumulation['rounds']:
        index=int(round_row['round']);source={'query_id':plan['query_id'],'round_index':index,'spanish_text':round_row['spanish_text'],'spanish_text_sha256':round_row['spanish_text_sha256'],'available_turns':round_row.get('available_turns',[])}
        literal_spec=calls[f'R{index}:retrieve_literal'];literal,hit=_run_call(plan=plan,call_spec=literal_spec,authorization=authorizations[literal_spec['call_key']],port=literal_retriever.retrieve,store=store,index=index*3,kind=f'R{index}-literal',payload={'query_id':f"{plan['query_id']}-R{index}",'text':source['spanish_text'],'language':'es'});recovered+=hit;executed+=not hit;validate_ranking(literal)
        compile_spec=calls[f'E{index}:compile_en'];compiled,hit=_run_call(plan=plan,call_spec=compile_spec,authorization=authorizations[compile_spec['call_key']],port=compiler.compile,store=store,index=index*3+1,kind=f'E{index}-compile',payload={'spanish_source':source});recovered+=hit;executed+=not hit
        en_spec=calls[f'E{index}:retrieve_en'];english,hit=_run_call(plan=plan,call_spec=en_spec,authorization=authorizations[en_spec['call_key']],port=en_retriever.retrieve,store=store,index=index*3+2,kind=f'E{index}-retrieve',payload={'query_id':f"{plan['query_id']}-E{index}",'text':compiled['text'],'language':'en'});recovered+=hit;executed+=not hit;validate_ranking(english)
        if {x['candidate_id'] for x in literal['results']}!={x['candidate_id'] for x in english['results']}:raise DialogueTransitionError('universo literal/EN divergente')
        rounds.append({'round':index,'spanish_text_sha256':source['spanish_text_sha256'],'literal_ranking_sha256':digest(literal),'compiled_text_sha256':compiled['text_sha256'],'english_ranking_sha256':digest(english)})
    bundle={'schema_version':'1.0','contract_version':'dq-dev1-paired-transition-output-v1','transition_id':plan['transition_id'],'query_id':plan['query_id'],'rounds':rounds,'same_spanish_source_between_arms':True,'rankings_used_for_question_selection':False,'ground_truth_used':False};bundle_ref=store.publish('artifacts/paired-bundle.json',bundle);result={'schema_version':'1.0','contract_version':'dialogue-transition-result-v1','transition_id':plan['transition_id'],'mode':'paired','status':'completed','artifacts':{'paired_bundle':bundle_ref},'executed_calls':executed,'recovered_calls':recovered,'historical_parent_unchanged':True};store.publish('transition-result.json',result);return result

def execute_retrieval(*,plan:Mapping[str,Any],authorization:Mapping[str,Any],retriever:RetrieverPort,store:TransitionStore)->dict[str,Any]:
    validate_plan(plan)
    completed=store.completed_result(plan,'retrieval')
    if completed is not None:return completed
    if plan['mode']!='retrieval' or len(plan.get('calls',[]))!=1:raise DialogueTransitionError('plan retrieval incompatible')
    spec=plan['calls'][0];payload=plan.get('retrieval_input',{});text=payload.get('text');language=payload.get('language')
    if not isinstance(text,str) or not text or language not in {'es','en'} or hashlib.sha256(text.encode()).hexdigest()!=spec['input_sha256']:raise DialogueTransitionError('input retrieval divergente')
    ranking,hit=_run_call(plan=plan,call_spec=spec,authorization=authorization,port=retriever.retrieve,store=store,index=0,kind='retrieve',payload={'query_id':f"{plan['query_id']}-{spec['arm']}{spec['round_index']}",'text':text,'language':language});validate_ranking(ranking)
    ranking_path=store.root/f"artifacts/{expected_call(plan,spec).call_id}.json";result={'schema_version':'1.0','contract_version':'dialogue-transition-result-v1','transition_id':plan['transition_id'],'mode':'retrieval','status':'completed','artifacts':{'ranking':{'logical_path':ranking_path.relative_to(store.root).as_posix(),'sha256':file_sha(ranking_path)}},'executed_calls':0 if hit else 1,'recovered_calls':1 if hit else 0,'historical_parent_unchanged':True};store.publish('transition-result.json',result);return result
