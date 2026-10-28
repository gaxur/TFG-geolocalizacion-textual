#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f4_evaluation import haversine_m
from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
from src.tfg_phase0.topn_reserve import canonical_bytes
RADII=(25,50,100)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--rankings',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--kind',default='en_cartographic');p.add_argument('--gallery',default='madrid-50m');a=p.parse_args();rankings=json.loads(a.rankings.read_text());inventory=json.loads(a.inventory.read_text());reject_ground_truth(rankings,path='rankings');reject_ground_truth(inventory,path='inventory');selected=[r for r in rankings['rows'] if r['kind']==a.kind and r['gallery_id']==a.gallery];assert len(selected)==15;images=inventory['images'];per=[];unique={}
 for row in selected:
  slots=[]
  for candidate in row['results']:
   distances=[haversine_m(candidate['latitude'],candidate['longitude'],image['latitude'],image['longitude']) for image in images];nearest=min(distances) if distances else None;entry={'rank':candidate['rank'],'candidate_id':candidate['candidate_id'],'nearest_image_distance_m':nearest,'covered':{str(r):nearest is not None and nearest<=r for r in RADII}};slots.append(entry);unique[candidate['candidate_id']]={**candidate,'nearest_image_distance_m':nearest,'covered':entry['covered']}
  per.append({'query_id':row['query_id'],'slots':slots,'covered_counts':{str(r):sum(s['covered'][str(r)] for s in slots) for r in RADII}})
 doc={'schema_version':'1.0','contract_version':'h11-h25-topn-mapillary-coverage-v1','inputs':{'rankings_sha256':sha(a.rankings),'inventory_sha256':sha(a.inventory)},'protocol':{'kind':a.kind,'gallery_id':a.gallery,'top_k':rankings['top_k'],'ground_truth_used':False,'coverage_does_not_imply_visibility':True},'summary':{'query_count':len(per),'slot_count':sum(len(r['slots']) for r in per),'unique_candidate_count':len(unique),'slot_coverage':{str(radius):{'covered':sum(r['covered_counts'][str(radius)] for r in per),'total':sum(len(r['slots']) for r in per)} for radius in RADII},'unique_coverage':{str(radius):{'covered':sum(c['covered'][str(radius)] for c in unique.values()),'total':len(unique)} for radius in RADII}},'per_query':per,'unique_candidates':sorted(unique.values(),key=lambda x:x['candidate_id']),'limitations':['metadata_proximity_only','no_images_downloaded','shared_assets_not_independent']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps(doc['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
