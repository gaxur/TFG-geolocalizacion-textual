"""Evaluación posterior con referencias de artefactos Top-N congelados."""
from __future__ import annotations
from typing import Mapping,Sequence
from .f4_evaluation import haversine_m
from .topn_promotion import TopNPromotionError
def evaluate_promotion(document:Mapping,*,reference_latitude:float,reference_longitude:float,reference_candidate_id:str|None=None,threshold_m:float=50)->dict:
 if document.get('protocol',{}).get('ground_truth_used') is not False or not document.get('audit',{}).get('candidate_set_invariant_topn'):raise TopNPromotionError('artefacto no evaluable')
 baseline=document['baseline_results'];by={r['candidate_id']:r for r in baseline};base_ids=[r['candidate_id'] for r in baseline[:10]];final_ids=document['final_top10_candidate_ids']
 if len(final_ids)!=10 or not set(final_ids)<={r['candidate_id'] for r in baseline}:raise TopNPromotionError('Top-10 final inválido')
 def metrics(ids):
  distances=[haversine_m(reference_latitude,reference_longitude,by[x]['latitude'],by[x]['longitude']) for x in ids];return {'top1_distance_m':distances[0],'minimum_distance':{str(k):min(distances[:k]) for k in (1,5,10)},'geo_recall':{str(k):min(distances[:k])<=threshold_m for k in (1,5,10)},'exact_recall':{str(k):(reference_candidate_id in ids[:k]) if reference_candidate_id else None for k in (1,5,10)}}
 base,final=metrics(base_ids),metrics(final_ids);promoted=set(final_ids)-set(base_ids);displaced=set(base_ids)-set(final_ids);return {'baseline':base,'experimental':final,'transition':{'top1_distance_delta_m':final['top1_distance_m']-base['top1_distance_m'],'improved':final['top1_distance_m']<base['top1_distance_m'],'regressed':final['top1_distance_m']>base['top1_distance_m'],'promoted_candidate_ids':sorted(promoted),'displaced_candidate_ids':sorted(displaced),'relevant_promoted':reference_candidate_id in promoted if reference_candidate_id else None,'relevant_displaced':reference_candidate_id in displaced if reference_candidate_id else None},'limitations':['evaluation_only','parameters_not_selected_here']}
