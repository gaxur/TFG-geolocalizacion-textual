#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import aggregate_candidate_evidence,canonical_bytes,rerank_experimental

def main():
 p=argparse.ArgumentParser(description='Agrega veredictos H11 y genera ranking separado');p.add_argument('--fixture',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--enable',action='store_true');p.add_argument('--lambda-pos',type=float,default=0);p.add_argument('--lambda-neg',type=float,default=0);a=p.parse_args();f=json.loads(a.fixture.read_text());run=json.loads(a.run.read_text());claims=run['approved_claims'];verdicts=[]
 for row in run['records']:
  if row['status'] in {'valid','policy_unverifiable'}:
   verdict=row.get('verdict') or (row.get('parsed_verdict') or {}).get('verdict')
   if verdict:verdicts.append({'status':'valid','candidate_id':row['candidate_id'],'image_id':row['image_id'],'claim_id':row['claim_id'],'verdict':verdict})
 baseline_ids=[r['candidate_id'] for r in f['baseline']['results']];aggregate=aggregate_candidate_evidence(claims,f['associations'],verdicts,candidate_ids=baseline_ids);ranking=rerank_experimental({'results':f['baseline']['results']},aggregate,enabled=a.enable,lambda_pos=a.lambda_pos,lambda_neg=a.lambda_neg);doc={'schema_version':'1.0','contract_version':'h11-visual-reranking-artifact-v1','fixture_id':f['fixture_id'],'inputs':{'fixture_sha256':hashlib.sha256(a.fixture.read_bytes()).hexdigest(),'run_sha256':hashlib.sha256(a.run.read_bytes()).hexdigest()},'aggregate':aggregate,**ranking};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps({'enabled':a.enable,'candidates':len(ranking['results'])},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
