"""Outcome ortogonal V2 para separar generación, validación y publicación."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any,Mapping
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[2];SCHEMA=ROOT/'schemas/question_policy_outcome_v2.schema.json'
FINAL=('PUBLISHED_ASK','STOP','ABSTAIN','VALIDATION_REJECTED','TECHNICAL_FAILURE')
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest_text(v):return hashlib.sha256(v.encode()).hexdigest()
def _validate_invariants(d):
 f=d['final_outcome'];e=d['execution'];g=d['generation'];v=d['validation'];p=d['publication']
 if f=='PUBLISHED_ASK' and not (e['status']=='SUCCEEDED' and g['action']=='ASK' and v['status']=='PASSED' and p['action']=='ASK' and p['question']):raise ValueError('outcome ASK inconsistente')
 if f=='VALIDATION_REJECTED' and not (e['status']=='SUCCEEDED' and v['status']=='REJECTED' and p['action']=='NONE'):raise ValueError('outcome rechazo inconsistente')
 if f=='TECHNICAL_FAILURE' and e['status']!='FAILED':raise ValueError('outcome técnico inconsistente')
 if f in {'STOP','ABSTAIN'} and not (e['status']=='SUCCEEDED' and g['action']==f and p['action']==f and p['question'] is None):raise ValueError('outcome abstención inconsistente')
 if p['question'] is not None and p['question_sha256']!=digest_text(p['question']):raise ValueError('hash de pregunta divergente')
 return d
def build_outcome(*,execution,generation,validation,publication,final_outcome,lineage):
 if final_outcome not in FINAL:raise ValueError('final_outcome inválido')
 legacy={'PUBLISHED_ASK':('ASK',None),'STOP':('STOP',None),'ABSTAIN':('ABSTAIN',None),'VALIDATION_REJECTED':('ERROR','validation_rejection'),'TECHNICAL_FAILURE':('ERROR','technical_failure')}[final_outcome]
 d={'schema_version':'1.0','contract_version':'question-policy-outcome-v2','outcome_id':'','execution':dict(execution),'generation':dict(generation),'validation':dict(validation),'publication':dict(publication),'final_outcome':final_outcome,'legacy_projection':{'action':legacy[0],'error_kind':legacy[1]},'lineage':dict(lineage)};d['outcome_id']='question-policy-outcome-sha256-'+hashlib.sha256(canonical({k:v for k,v in d.items() if k!='outcome_id'})).hexdigest();Draft202012Validator(json.loads(SCHEMA.read_text())).validate(d);return _validate_invariants(d)
def from_v10_artifacts(*,raw_document=None,response=None,failure=None,telemetry=None,lineage=None):
 raw_payload=None
 if raw_document and raw_document.get('raw_output'):
  try:raw_payload=json.loads(raw_document['raw_output'])
  except json.JSONDecodeError:raw_payload=None
 action=raw_payload.get('action') if isinstance(raw_payload,dict) else None;question=raw_payload.get('question') if isinstance(raw_payload,dict) else None
 generation={'action':action,'raw_output_sha256':raw_document.get('raw_output_sha256') if raw_document else None,'raw_question':question,'raw_preserved':raw_document is not None}
 base_lineage={**dict(lineage or {}),'raw_document_sha256':hashlib.sha256(canonical(raw_document)).hexdigest() if raw_document else None}
 if response:
  decision=response['decision'];status=decision['status']
  if status=='ask':return build_outcome(execution={'status':'SUCCEEDED','completed_stage':'publication','error':None},generation=generation,validation={'status':'PASSED','stage':'grounding_v9a','reason_codes':[]},publication={'action':'ASK','question':decision['question'],'question_sha256':digest_text(decision['question']),'reason':None},final_outcome='PUBLISHED_ASK',lineage=base_lineage)
  kind=decision['abstention_kind'].upper();return build_outcome(execution={'status':'SUCCEEDED','completed_stage':'publication','error':None},generation=generation,validation={'status':'NOT_APPLICABLE','stage':None,'reason_codes':[]},publication={'action':kind,'question':None,'question_sha256':None,'reason':decision['abstention_reason']},final_outcome=kind,lineage=base_lineage)
 if failure:
  stage=failure.get('failure_stage');reasons=list(failure.get('reasons',[]));validation_rejection=stage=='post_raw_persistence_validation' and raw_document is not None and bool(reasons)
  if validation_rejection:return build_outcome(execution={'status':'SUCCEEDED','completed_stage':'generation','error':None},generation=generation,validation={'status':'REJECTED','stage':'grounding_or_contract','reason_codes':reasons},publication={'action':'NONE','question':None,'question_sha256':None,'reason':None},final_outcome='VALIDATION_REJECTED',lineage=base_lineage)
  return build_outcome(execution={'status':'FAILED','completed_stage':telemetry.get('completed_stage') if telemetry else None,'error':dict(failure)},generation=generation,validation={'status':'NOT_RUN','stage':stage,'reason_codes':reasons},publication={'action':'NONE','question':None,'question_sha256':None,'reason':None},final_outcome='TECHNICAL_FAILURE',lineage=base_lineage)
 raise ValueError('artefactos V10 insuficientes')
def legacy_projection(outcome):
 action=outcome['legacy_projection']['action']
 if action=='ASK':return {'action':'ASK','question':outcome['publication']['question'],'question_origin':'qwen3_vl_visual','error':None,'outcome_v2':outcome}
 if action in {'STOP','ABSTAIN'}:return {'action':action,'reason':outcome['publication']['reason'],'question_origin':'vlm_model_abstention','error':None,'outcome_v2':outcome}
 return {'action':'ERROR','question_origin':'technical_failure' if outcome['final_outcome']=='TECHNICAL_FAILURE' else 'validation_rejection','error':{'error_kind':outcome['legacy_projection']['error_kind'],'reason_codes':outcome['validation']['reason_codes']},'outcome_v2':outcome}
