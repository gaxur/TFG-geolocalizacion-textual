#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.topn_reserve import canonical_bytes
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description='Planifica reserva visual progresiva sin GT ni descargas');p.add_argument('--rankings',type=Path,required=True);p.add_argument('--coverage',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rankings=json.loads(a.rankings.read_text());coverage=json.loads(a.coverage.read_text());selected={(r['query_id'],r['kind'],r['gallery_id']):r for r in rankings['rows'] if r['kind']=='en_cartographic' and r['gallery_id']=='madrid-50m'};cov={(r['query_id']):r for r in coverage['per_query']};queries=[]
 for query_id in sorted(cov):
  row=selected[(query_id,'en_cartographic','madrid-50m')];slot_cov={s['rank']:s for s in cov[query_id]['slots']};blocks=[]
  for start,end in ((1,10),(11,20),(21,50),(51,100)):
   candidates=[]
   for c in row['results'][start-1:end]:
    v=slot_cov[c['rank']];candidates.append({'rank':c['rank'],'candidate_id':c['candidate_id'],'has_camera_100m':v['covered']['100'],'nearest_image_distance_m':v['nearest_image_distance_m']})
   blocks.append({'start_rank':start,'end_rank':end,'candidate_count':len(candidates),'covered_100m':sum(c['has_camera_100m'] for c in candidates),'candidates':candidates})
  queries.append({'query_id':query_id,'blocks':blocks})
 doc={'schema_version':'1.0','contract_version':'topn-visual-reserve-plan-v1','inputs':{'rankings_sha256':sha(a.rankings),'coverage_sha256':sha(a.coverage)},'protocol':{'gallery_id':'madrid-50m','kind':'en_cartographic','ground_truth_used':False,'selection_order':'rank_blocks','blocks':[[1,10],[11,20],[21,50],[51,100]],'advance_rule':'complete fixed block before opening next block','no_coverage_is_neutral':True,'downloads_authorized':False},'queries':queries,'summary':{'query_count':len(queries),'candidate_slots':sum(b['candidate_count'] for q in queries for b in q['blocks']),'covered_100m':sum(b['covered_100m'] for q in queries for b in q['blocks'])},'limitations':['metadata_coverage_only','no_photos_selected_or_downloaded','no_claim_review_for_reserve','no_substitution_policy_calibrated']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps(doc['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
