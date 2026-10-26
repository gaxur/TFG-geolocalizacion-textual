#!/usr/bin/env python3
from __future__ import annotations
import argparse,collections,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import canonical_bytes
CLASSES=('supported','contradicted','unverifiable');COLUMNS=CLASSES+('invalid_output',)
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=json.loads(a.run.read_text());human=json.loads(a.annotations.read_text());pred={(r['candidate_id'],r['image_id'],r['claim_id']):r for r in run['records']};truth={(r['candidate_id'],r['image_id'],r['claim_id']):r for r in human['records']};assert set(pred)==set(truth) and len(pred)==60
 matrix={c:{p:0 for p in COLUMNS} for c in CLASSES};valid=correct=0;latencies=[];per=[]
 for key,h in truth.items():
  r=pred[key];v=r['parsed_verdict']['verdict'] if r['parsed_verdict'] else None
  matrix[h['human_verdict']][v or 'invalid_output']+=1
  if v:valid+=1;correct+=v==h['human_verdict']
  latencies.append(r['inference_seconds']);per.append({'candidate_id':key[0],'image_id':key[1],'claim_id':key[2],'human':h['human_verdict'],'predicted':v,'status':r['status'],'correct':v==h['human_verdict'] if v else False,'human_evidence':h['observed_evidence'],'vlm_evidence':r['parsed_verdict']['observed_evidence'] if r['parsed_verdict'] else None})
 metrics={}
 for c in CLASSES:
  tp=matrix[c][c];fp=sum(matrix[t][c] for t in CLASSES if t!=c);fn=sum(matrix[c][p] for p in COLUMNS if p!=c);precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None;f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else 0.0;metrics[c]={'support':sum(matrix[c].values()),'precision':precision,'recall':recall,'f1':f1}
 doc={'schema_version':'1.0','contract_version':'visual-atomic-validation-evaluation-v1','inputs':{'run_sha256':hashlib.sha256(a.run.read_bytes()).hexdigest(),'annotations_sha256':hashlib.sha256(a.annotations.read_bytes()).hexdigest()},'summary':{'pairs':60,'valid_predictions':valid,'valid_fraction':valid/60,'accuracy':correct/60,'accuracy_among_valid':correct/valid if valid else None,'macro_f1':sum(m['f1'] for m in metrics.values())/3,'false_contradictions':sum(matrix[t]['contradicted'] for t in CLASSES if t!='contradicted'),'false_supports':sum(matrix[t]['supported'] for t in CLASSES if t!='supported'),'correct_abstentions':matrix['unverifiable']['unverifiable'],'incorrect_abstentions':sum(matrix[t]['unverifiable'] for t in ('supported','contradicted')),'invalid_outputs':60-valid,'latency_total_seconds':sum(latencies),'latency_mean_seconds':sum(latencies)/60,'latency_mean_model_calls_seconds':sum(latencies)/(60-run['summary']['policy_unverifiable']),'latency_max_seconds':max(latencies)},'confusion_matrix':{'rows':list(CLASSES),'columns':list(COLUMNS),'counts':matrix},'per_class':metrics,'per_record':per,'resources':run['resources'],'limitations':['single_reviewer','development_fixture','small_imbalanced_sample','human_evidence_free_text','no_statistical_generalization']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps(doc['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
