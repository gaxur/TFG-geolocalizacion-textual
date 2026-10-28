"""Validación de campañas H26+ sin ejecutar retrieval ni abrir outputs de modelos."""
from __future__ import annotations
from datetime import datetime
import hashlib,json,math
from pathlib import Path
from typing import Any,Mapping,Sequence
from jsonschema import Draft202012Validator
from .f4_evaluation import haversine_m

class IndependentCampaignError(ValueError):pass
def canonical_bytes(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def _time(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
def validate_campaign(document:Mapping[str,Any],*,schema:Mapping[str,Any],evidence_root:Path,historical:Sequence[Mapping[str,Any]]=(),development_target:int=12,test_target:int=24,minimum_prior_distance_m:float=50)->dict[str,Any]:
 if not isinstance(document,Mapping) or not isinstance(document.get('observations'),list):raise IndependentCampaignError('contenedor de campaña inválido')
 validator=Draft202012Validator(schema,format_checker=Draft202012Validator.FORMAT_CHECKER);rows=document['observations']
 for row in rows:validator.validate(row)
 ids=[r['query_id'] for r in rows];locations=[r['location_id'] for r in rows]
 if len(ids)!=len(set(ids)) or len(locations)!=len(set(locations)):raise IndependentCampaignError('IDs de consulta/localización duplicados')
 blocks={}
 for row in rows:
  blocks.setdefault(row['spatial_block_id'],set()).add(row['partition'])
  frozen=_time(row['freeze']['observation_frozen_at_utc']);ranked=row['freeze']['rankings_executed_at_utc']
  if ranked is not None and frozen>=_time(ranked):raise IndependentCampaignError('ranking anterior o simultáneo al freeze')
  if any(repr(token) in row['description_es'] for token in (row['observer_position']['latitude'],row['observer_position']['longitude'])):raise IndependentCampaignError('coordenada filtrada en descripción')
  for evidence in row['evidence']:
   path=(evidence_root/evidence['logical_path']).resolve()
   try:path.relative_to(evidence_root.resolve())
   except ValueError as error:raise IndependentCampaignError('ruta de evidencia fuera de raíz') from error
   if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=evidence['sha256']:raise IndependentCampaignError('evidencia ausente o hash inválido')
  for prior in historical:
   distance=haversine_m(row['observer_position']['latitude'],row['observer_position']['longitude'],prior['latitude'],prior['longitude'])
   if distance<minimum_prior_distance_m:raise IndependentCampaignError(f"{row['query_id']} solapa observación histórica {prior.get('id')}")
 if any(len(parts)>1 for parts in blocks.values()):raise IndependentCampaignError('bloque espacial mezclado entre development/test')
 counts={p:sum(r['partition']==p for r in rows) for p in ('development','test_sealed')}
 complete=counts=={'development':development_target,'test_sealed':test_target}
 return {'schema_version':'1.0','contract_version':'independent-campaign-validation-v1','observation_count':len(rows),'partition_counts':counts,'spatial_blocks':len(blocks),'target_complete':complete,'minimum_prior_distance_m':minimum_prior_distance_m,'campaign_sha256':hashlib.sha256(canonical_bytes(document)).hexdigest()}
