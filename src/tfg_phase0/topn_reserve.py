"""Congelación Top-N CT2L desde un plan textual saneado, sin referencias."""
from __future__ import annotations
import hashlib,json,math,time
from typing import Any,Mapping
from .mapillary_visual_pilot import reject_ground_truth

class TopNReserveError(ValueError): pass
ALLOWED_TOP_K=(10,20,50,100,200,500)
def canonical_bytes(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def content_id(doc):return 'h11-h25-topn-sha256-'+hashlib.sha256(canonical_bytes({k:v for k,v in doc.items() if k!='reserve_id'})).hexdigest()
def resolve_top_k(value:int|str,*,gallery_count:int)->int:
 if value=='full':return gallery_count
 if not isinstance(value,int) or isinstance(value,bool) or value not in ALLOWED_TOP_K:raise TopNReserveError('Top-K debe ser 10/20/50/100/200/500/full')
 if value>gallery_count:raise TopNReserveError(f'Top-K {value} supera la galería de {gallery_count} candidatos')
 return value
def freeze_topn(plan:Mapping[str,Any],retriever,*,top_k:int,plan_sha256:str)->dict[str,Any]:
 reject_ground_truth(plan,path='plan')
 if plan.get('contract_version')!='h11-h25-two-control-plan-v1' or len(plan.get('controls',[]))!=30 or top_k not in ALLOWED_TOP_K:raise TopNReserveError('plan o top_k incompatible')
 rows=[];checkpoint=None;gallery_meta={}
 for control in plan['controls']:
  started=time.perf_counter();response=retriever.retrieve_many(gallery_ids=('madrid-25m','madrid-50m'),query_id=control['control_id'],text=control['text'],language=control['language'],k=top_k);elapsed=(time.perf_counter()-started)*1000;current=response['model']['checkpoint_sha256'];checkpoint=current if checkpoint is None else checkpoint
  if current!=checkpoint:raise TopNReserveError('checkpoint cambió')
  for retrieval in response['retrievals']:
   if top_k>retrieval['gallery_count']:raise TopNReserveError(f"Top-K {top_k} supera {retrieval['gallery_id']}")
   results=retrieval['results'];ranks=[r.get('rank') for r in results]
   if len(results)!=top_k or ranks!=list(range(1,top_k+1)) or len({r['candidate_id'] for r in results})!=top_k or any(not math.isfinite(r['cosine_similarity']) for r in results):raise TopNReserveError('ranking Top-N inválido')
   gallery_meta[retrieval['gallery_id']]={'gallery_count':retrieval['gallery_count'],'visual_dataset_id':retrieval['visual_dataset_id'],'embedding_dataset_id':retrieval['embedding_dataset_id'],'ranking_method':retrieval['ranking_method'],'tie_break':retrieval['tie_break']}
   rows.append({**{k:control[k] for k in ('query_id','category','scene_type','kind','control_id','text_sha256','transformation_run_id')},'gallery_id':retrieval['gallery_id'],'results':results,'retrieval_ms':response['timings_ms']['total'],'pipeline_elapsed_ms':elapsed})
 doc={'schema_version':'1.0','contract_version':'h11-h25-frozen-topn-rankings-v1','reserve_id':'','top_k':top_k,'plan_sha256':plan_sha256,'checkpoint_sha256':checkpoint,'galleries':gallery_meta,'protocol':{'ranking_method':'exhaustive_cosine','ground_truth_used':False,'coordinates_used_for_retrieval':False,'fine_tuning':False},'rows':rows,'limitations':['text_embeddings_recomputed_not_persisted','same_frozen_visual_embeddings','no_candidate_filtering']};doc['reserve_id']=content_id(doc);return doc
def validate_top10_prefix(reserve:Mapping[str,Any],old:Mapping[str,Any])->dict[str,Any]:
 index={(r['query_id'],r['kind'],r['gallery_id']):r for r in old['rows']};mismatches=[];max_delta=0.0
 if len(index)!=len(old['rows']):mismatches.append({'reason':'duplicate_old_row_key'})
 for row in reserve['rows']:
  key=(row['query_id'],row['kind'],row['gallery_id']);prior=index.get(key)
  if prior is None:mismatches.append({'key':key,'reason':'missing_old'});continue
  if len(prior.get('results',[]))!=10:mismatches.append({'key':key,'reason':'old_prefix_not_exactly_10'});continue
  for left,right in zip(prior['results'],row['results'][:10]):
   if left['rank']!=right['rank'] or left['candidate_id']!=right['candidate_id'] or left['latitude']!=right['latitude'] or left['longitude']!=right['longitude']:mismatches.append({'key':key,'rank':left['rank'],'reason':'identity_or_coordinate'});break
   max_delta=max(max_delta,abs(left['cosine_similarity']-right['cosine_similarity']))
 reserve_keys={(r['query_id'],r['kind'],r['gallery_id']) for r in reserve['rows']}
 for key in set(index)-reserve_keys:mismatches.append({'key':key,'reason':'missing_new'})
 return {'rows_checked':len(reserve['rows']),'prefix_length':10,'identity_coordinate_mismatches':mismatches,'max_absolute_cosine_delta':max_delta,'exact_prefix_match':not mismatches and max_delta==0.0}

def validate_frozen_topn(document:Mapping[str,Any])->None:
 reject_ground_truth(document,path='reserve')
 if document.get('contract_version')!='h11-h25-frozen-topn-rankings-v1' or document.get('reserve_id')!=content_id(document):raise TopNReserveError('identidad de reserva inválida')
 top_k=document.get('top_k')
 if top_k not in ALLOWED_TOP_K:raise TopNReserveError('Top-K congelado no permitido')
 rows=document.get('rows',[]);keys=[]
 for row in rows:
  keys.append((row.get('query_id'),row.get('kind'),row.get('gallery_id')));results=row.get('results',[])
  if len(results)!=top_k or [r.get('rank') for r in results]!=list(range(1,top_k+1)) or len({r.get('candidate_id') for r in results})!=top_k:raise TopNReserveError('ranking congelado inválido')
 if len(rows)!=60 or len(keys)!=len(set(keys)):raise TopNReserveError('la reserva H11-H25 debe contener 60 rankings únicos')
