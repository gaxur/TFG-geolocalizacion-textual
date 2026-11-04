#!/usr/bin/env python3
"""E2E sintético: sustitución y claims sin red, GPU ni modelo real."""
from __future__ import annotations
import argparse,hashlib,json,tempfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_quality_gate import ManifestAssetResolver,ScriptedQualityVerifier,run_quality_replacement,canonical_bytes
class Claims:
 def __init__(self):self.calls=[]
 def verify(self,*,candidate_id,asset,claims):self.calls.append((candidate_id,asset.image_id,len(claims)));return [{'claim_id':row['claim_id'],'verdict':'unverifiable'} for row in claims]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with tempfile.TemporaryDirectory(prefix='quality-fixture-') as name:
  root=Path(name);assets={};decisions={};reserves=[]
  specs=[('C1',['REJECT','ACCEPT']),('C2',['REVIEW','ACCEPT']),('C3',['REJECT','REJECT'])]
  for candidate,values in specs:
   for index,decision in enumerate(values):
    raw=f'{candidate}-{index}'.encode();path=root/f'{candidate}-{index}.bin';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();assets[f'{candidate}-{index}']={'logical_path':path.name,'sha256':sha,'size_bytes':len(raw)};reserves.append({'candidate_id':candidate,'reserve_index':index,'image_id':f'{candidate}-{index}','sequence_id':f'S{index}'})
    reasons={'ACCEPT':['USABLE_SCENE'],'REJECT':['BLUR'],'REVIEW':['AMBIGUOUS_QUALITY']}[decision];decisions[sha]={'decision':decision,'reason_codes':reasons}
  policy=json.loads((ROOT/'config/visual_quality_gate_v1.json').read_text());policy['enabled']=True;policy['status']='fixture_authorized';policy['limits']['target_accepted_images_per_candidate']=1;policy['limits']['maximum_images_inspected_per_candidate']=2;policy['limits']['maximum_replacements_per_candidate']=1;claims=Claims();verifier=ScriptedQualityVerifier(decisions);result=run_quality_replacement(reserves=reserves,claims_by_candidate={cid:[{'claim_id':f'{cid}-claim'}] for cid,_ in specs},policy=policy,resolver=ManifestAssetResolver(assets,root=root),quality_verifier=verifier,claim_verifier=claims,mode='fixture');report={'schema_version':'1.0','contract_version':'visual-quality-fixture-report-v1','synthetic_fixture':True,'scientific_result':False,'network_opened':False,'model_loaded':False,'gpu_opened':False,'result':result,'claim_calls':claims.calls};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(report)+b'\n');print(json.dumps(result['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
