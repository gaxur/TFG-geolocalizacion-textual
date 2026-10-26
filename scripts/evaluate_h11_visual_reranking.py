#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
from src.tfg_phase0.visual_reranking import canonical_bytes,evaluate_topk_transition

H11_REFERENCE=(40.4184261,-3.7030098)
def main():
 p=argparse.ArgumentParser(description='Evalúa H11 después de congelar reranking; única capa con referencia');p.add_argument('--fixture',type=Path,required=True);p.add_argument('--reranking',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();fixture=json.loads(a.fixture.read_text());reranking=json.loads(a.reranking.read_text());reject_ground_truth(reranking,path='reranking')
 baseline=fixture['baseline']['results'];experimental=reranking['results'];transition=evaluate_topk_transition(baseline,experimental,reference_latitude=H11_REFERENCE[0],reference_longitude=H11_REFERENCE[1]);b=transition['baseline'];e=transition['experimental'];t=transition['transition']
 doc={'schema_version':'1.0','contract_version':'h11-visual-reranking-evaluation-v1','protocol':{'query_id':'H11','fixture_role':'development','reference_kind':'google_link_coordinate_unknown_uncertainty','official_f54_evaluation':False,'reference_loaded_only_by_evaluator':True,'top_k_set_invariant':True},'inputs':{'fixture_sha256':hashlib.sha256(a.fixture.read_bytes()).hexdigest(),'reranking_sha256':hashlib.sha256(a.reranking.read_bytes()).hexdigest()},'reference':{'latitude':H11_REFERENCE[0],'longitude':H11_REFERENCE[1],'crs':'EPSG:4326','positional_uncertainty':'unknown'},**transition,'evidence_responsibility':[{'candidate_id':r['candidate_id'],'baseline_rank':r['baseline_rank'],'experimental_rank':r['experimental_rank'],'visual_modifier':r['visual_modifier'],'positive_evidence':r['positive_evidence'],'negative_evidence':r['negative_evidence']} for r in experimental if r['baseline_rank']!=r['experimental_rank']],'limitations':['single_development_case','not_independent_evaluation','unknown_reference_uncertainty','no_statistical_generalization']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps({'transition':t['top1'],'baseline_top1_m':b['top1_distance_m'],'experimental_top1_m':e['top1_distance_m'],'delta_m':t['top1_distance_delta_m']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
