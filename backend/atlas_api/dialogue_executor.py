"""Ejecutor HXX secuencial: Qwen y CT2L viven en procesos hijos no simultáneos."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping
import urllib.request

from src.tfg_phase0.f5_text_transform import GenerationConfig, validate_transformation
from src.tfg_phase0.interactive_dialogue import DialoguePolicyConfig, F3EvidenceIndex, QuestionIntent, cluster_ranked_candidates, select_question_intent
from src.tfg_phase0.interactive_dialogue_multiturn import interpret_answer

from .dialogue_sessions import atomic_write, canonical, sha256_file


def _meminfo() -> dict[str,int]:
    values={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key,raw=line.split(':',1);values[key]=int(raw.strip().split()[0])*1024
    return values


def _vmstat() -> dict[str,int]:
    wanted={'pswpin','pswpout','pgmajfault','pgscan_direct','pgsteal_direct','oom_kill'}
    return {key:int(value) for key,value in (line.split() for line in Path('/proc/vmstat').read_text().splitlines()) if key in wanted}


def _psi() -> dict[str,float]:
    rows={}
    for line in Path('/proc/pressure/memory').read_text().splitlines():
        parts=line.split();rows[parts[0]]=float(dict(item.split('=',1) for item in parts[1:])['avg10'])
    return rows


def _gpu_processes() -> list[str]:
    result=subprocess.run(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader,nounits'],capture_output=True,text=True)
    if result.returncode: return ['NOT_VERIFIED']
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


class SequentialDialogueExecutor:
    def __init__(self, *, qwen_model:Path, runtime_config:Path, region_config:Path, f3_bundle:Path, clip_weights:Path, cvg_utils_sha256:str, ollama_ps_url:str, python_executable:str=sys.executable):
        self.qwen_model=qwen_model;self.runtime_config=runtime_config;self.region_config=region_config;self.f3_bundle=f3_bundle;self.clip_weights=clip_weights;self.cvg_utils_sha256=cvg_utils_sha256;self.ollama_ps_url=ollama_ps_url;self.python=python_executable
        raw=json.loads((Path(__file__).resolve().parents[2]/'config/interactive_dialogue_multiturn.json').read_text());self.policy=DialoguePolicyConfig(reserve_size=raw['reserve_size'],cluster_radius_m=raw['cluster_radius_m'],minimum_hypotheses=raw['minimum_hypotheses'],minimum_supported_hypotheses=raw['minimum_supported_hypotheses'],maximum_supported_fraction=raw['maximum_supported_fraction'],allow_qwen_question=False,enable_controlled_rewrite=False);self.max_questions=raw['max_questions'];self.evidence=F3EvidenceIndex.load_bundle(f3_bundle)

    @property
    def identity(self) -> dict[str,str]:
        root=Path(__file__).resolve().parents[2]
        return {'executor_sha256':sha256_file(Path(__file__)),'worker_sha256':sha256_file(root/'scripts/run_mvp_dialogue_worker.py'),'answer_parser_sha256':sha256_file(root/'src/tfg_phase0/interactive_dialogue_multiturn.py'),'text_transform_sha256':sha256_file(root/'src/tfg_phase0/f5_text_transform.py')}

    def _gate(self, root:Path, label:str) -> None:
        samples=[]
        for index in range(5):
            memory=_meminfo();samples.append({'index':index+1,'memory':{'available':memory['MemAvailable'],'swap_total':memory['SwapTotal'],'swap_free':memory['SwapFree']},'vmstat':_vmstat(),'psi':_psi(),'gpu':_gpu_processes()})
            if index<4:time.sleep(2)
        first,last=samples[0],samples[-1];deltas={key:last['vmstat'][key]-first['vmstat'][key] for key in first['vmstat']};blocking={key:value for key,value in deltas.items() if key!='pgmajfault' and value}
        try:
            ollama=json.loads(urllib.request.urlopen(self.ollama_ps_url,timeout=3).read()).get('models',[])
        except Exception as error:
            ollama=[{'status':'NOT_VERIFIED','error':type(error).__name__}]
        ram=[row['memory']['available'] for row in samples];psi=max(max(row['psi'].values()) for row in samples);gpu=any(row['gpu'] for row in samples);passed=not blocking and not ollama and not gpu and min(ram)>=40*1024**3 and max(ram)-min(ram)<=1024**3 and psi<.10
        document={'schema_version':'1.0','contract_version':'atlas-dialogue-stable-swap-v2','label':label,'samples':samples,'deltas':deltas,'blocking_deltas':blocking,'ollama_models':ollama,'passed':passed};atomic_write(root/f'{label}-resource-gate.json',document)
        if not passed:raise RuntimeError('stable-swap-v2 bloquea la sesión')

    def _run(self, command:list[str], root:Path, name:str, timeout:int) -> None:
        result=subprocess.run(command,capture_output=True,text=True,timeout=timeout);atomic_write(root/f'{name}-supervisor.json',{'returncode':result.returncode,'stdout':result.stdout[-4000:],'stderr':result.stderr[-4000:]})
        if result.returncode:raise RuntimeError(f'{name} falló')

    def _qwen(self, *, query_id:str, round_index:int, spanish_text:str, root:Path) -> dict[str,Any]:
        request={'query_id':query_id,'round':round_index,'spanish_text':spanish_text};request_path=root/f'qwen-request-{round_index}.json';atomic_write(request_path,request);output=root/f'en-{round_index}.json';self._gate(root,f'qwen-{round_index}')
        self._run([self.python,str(Path(__file__).resolve().parents[2]/'scripts/run_mvp_dialogue_worker.py'),'qwen','--request',str(request_path),'--model',str(self.qwen_model),'--output',str(output)],root,f'qwen-{round_index}',360)
        document=json.loads(output.read_text());validation=validate_transformation(spanish_text,document['text'],'translate_en_cartographic',[],GenerationConfig())
        if not validation['structurally_valid']:raise RuntimeError('EN rechazado por validación')
        document['validation']=validation;atomic_write(output,document);return document

    def _ct2l(self, *, query_id:str, round_index:int, english:Mapping[str,Any], root:Path) -> dict[str,Any]:
        request={'query_id':query_id,'round':round_index,'text':english['text'],'text_sha256':english['text_sha256']};request_path=root/f'ct2l-request-{round_index}.json';atomic_write(request_path,request);output=root/f'ranking-{round_index}.json';self._gate(root,f'ct2l-{round_index}')
        self._run([self.python,str(Path(__file__).resolve().parents[2]/'scripts/run_mvp_dialogue_worker.py'),'ct2l','--request',str(request_path),'--runtime-config',str(self.runtime_config),'--region-config',str(self.region_config),'--clip',str(self.clip_weights),'--cvg-utils-sha256',self.cvg_utils_sha256,'--output',str(output)],root,f'ct2l-{round_index}',300)
        return json.loads(output.read_text())

    def _question(self, state:dict[str,Any]) -> None:
        ranking=state['rounds'][-1]['ranking'];hypotheses=cluster_ranked_candidates(ranking,self.evidence,reserve_size=self.policy.reserve_size,radius_m=self.policy.cluster_radius_m);used={turn['question']['feature'] for turn in state['turns']};description=state['description_es']+' '+' '.join(('Puedo ver ' if claim['polarity']=='positive' else 'No puedo ver ')+claim['label'] for claim in state['claims']);intent=select_question_intent(description,hypotheses,self.policy)
        if intent is None or intent.feature in used:state['status']='completed';state['stop_reason']='no_discriminative_question';return
        text=intent.deterministic_question;state['turns'].append({'index':len(state['turns'])+1,'question':{'feature':intent.feature,'label':intent.label,'question':text,'question_sha256':hashlib.sha256(text.encode()).hexdigest()},'answer':None})

    def _es(self,state:Mapping[str,Any]) -> str:
        parts=[state['description_es']]
        for claim in state['claims']:parts.append((f"Puedo ver {claim['label']}." if claim['polarity']=='positive' else f"No puedo ver {claim['label']} desde mi posición."))
        return ' '.join(parts)

    def start(self, *, query_id:str, description:str, session_root:Path) -> Mapping[str,Any]:
        en=self._qwen(query_id=query_id,round_index=0,spanish_text=description,root=session_root);ranking=self._ct2l(query_id=query_id,round_index=0,english=en,root=session_root);state={'contract_version':'atlas-dialogue-scientific-state-v1','status':'awaiting_answer','stop_reason':None,'query_id':query_id,'description_es':description,'claims':[],'answers':[],'turns':[],'rounds':[{'round':0,'es':description,'es_sha256':hashlib.sha256(description.encode()).hexdigest(),'en':en,'ranking':ranking,'ranking_sha256':hashlib.sha256(canonical(ranking)).hexdigest()}]};self._question(state);return state

    def answer(self, *, state:Mapping[str,Any], answer:str, answer_kind:str, session_root:Path) -> Mapping[str,Any]:
        value=json.loads(json.dumps(state));turn=value['turns'][-1];intent=QuestionIntent('web',turn['question']['feature'],turn['question']['label'],(),(),(),turn['question']['question'],());interpreted=interpret_answer(answer,intent,value['claims']);turn['answer']={'literal':answer,'sha256':hashlib.sha256(answer.encode()).hexdigest(),'answer_kind':answer_kind,'interpretation':interpreted};value['answers'].append(turn['answer'])
        if interpreted['kind']=='stop' or interpreted.get('conflict'):value['status']='completed';value['stop_reason']='human_requested_stop' if interpreted['kind']=='stop' else 'unresolvable_contradiction';return value
        if interpreted['informative']:value['claims'].append({'claim_id':f"claim-{turn['index']:03d}",'feature':intent.feature,'label':intent.label,'polarity':interpreted['polarity'],'active':True})
        if len(value['turns'])>=self.max_questions:value['terminal_es']=self._es(value);value['terminal_es_sha256']=hashlib.sha256(value['terminal_es'].encode()).hexdigest();value['status']='completed';value['stop_reason']='max_questions_reached';return value
        if interpreted['informative']:
            es=self._es(value);round_index=len(value['rounds']);en=self._qwen(query_id=value['query_id'],round_index=round_index,spanish_text=es,root=session_root);ranking=self._ct2l(query_id=value['query_id'],round_index=round_index,english=en,root=session_root);value['rounds'].append({'round':round_index,'es':es,'es_sha256':hashlib.sha256(es.encode()).hexdigest(),'en':en,'ranking':ranking,'ranking_sha256':hashlib.sha256(canonical(ranking)).hexdigest()})
        self._question(value);return value
