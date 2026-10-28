#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
from src.tfg_phase0.visual_reranking import canonical_bytes,compile_atomic_claims,plan_multiview_associations

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description='Prepara H11 visual sin abrir referencia/GT');p.add_argument('--rankings',type=Path,default=ROOT/'results/generated/f5/h11-h25-independent/rankings.json');p.add_argument('--plan',type=Path,default=ROOT/'results/generated/f5/h11-h25-independent/plan.json');p.add_argument('--inventory',type=Path,default=ROOT/'results/generated/mapillary/d004-buffer100m/inventory.json');p.add_argument('--existing-photos',type=Path,default=ROOT/'results/generated/mapillary/visual-pilot-v1/photo-manifest.json');p.add_argument('--output-root',type=Path,required=True);p.add_argument('--max-images-per-candidate',type=int,default=int(__import__('os').environ.get('MAPILLARY_IMAGES_PER_CANDIDATE','8')));a=p.parse_args()
 rankings=json.loads(a.rankings.read_text());texts=json.loads(a.plan.read_text());inventory=json.loads(a.inventory.read_text());existing=json.loads(a.existing_photos.read_text());reject_ground_truth(rankings,path='rankings');reject_ground_truth(texts,path='plan');reject_ground_truth(inventory,path='inventory')
 rows=[r for r in rankings['rows'] if r['query_id']=='H11' and r['gallery_id']=='madrid-50m' and r['kind']=='es_original'];controls=[r for r in texts['controls'] if r['query_id']=='H11' and r['kind']=='es_original']
 if len(rows)!=1 or len(controls)!=1 or len(rows[0]['results'])!=10:raise ValueError('H11 baseline no disponible de forma única')
 baseline=rows[0];candidates=[{k:r[k] for k in ('candidate_id','latitude','longitude')} for r in baseline['results']];multiview=plan_multiview_associations(candidates,inventory['images'],max_images_per_candidate=a.max_images_per_candidate)
 rank_by={r['candidate_id']:r for r in baseline['results']};image_by={r['image_id']:r for r in inventory['images']}
 associations=[]
 for row in multiview['associations']:
  source=image_by[row['image_id']];associations.append({**row,'baseline_rank':rank_by[row['candidate_id']]['rank'],'candidate_latitude':rank_by[row['candidate_id']]['latitude'],'candidate_longitude':rank_by[row['candidate_id']]['longitude'],'camera_latitude':source['latitude'],'camera_longitude':source['longitude'],'camera_orientation_degrees':source.get('orientation_degrees'),'captured_at_epoch_ms':source.get('captured_at_epoch_ms'),'orientation_comparable':False,'orientation_comparability_method':'not_established'})
 associations.sort(key=lambda r:(r['baseline_rank'],r['orientation_band'],r['distance_to_candidate_m'],r['image_id']))
 assets=sorted({r['image_id'] for r in associations});old={r['image_id']:r for r in existing['photos'] if r['status']=='downloaded'};reuse=sorted(set(assets)&set(old));new=sorted(set(assets)-set(old));sizes=[r['size_bytes'] for r in old.values()]
 claims=compile_atomic_claims(controls[0]['text'],[])
 baseline_public={'query_key':'visual-query-'+hashlib.sha256(controls[0]['text_sha256'].encode()).hexdigest(),'text':controls[0]['text'],'text_sha256':controls[0]['text_sha256'],'gallery_id':'madrid-50m','kind':'es_original','results':baseline['results']}
 doc={'schema_version':'1.0','contract_version':'h11-visual-execution-fixture-v1','fixture_role':'development','inputs':{'rankings_sha256':digest(a.rankings),'plan_sha256':digest(a.plan),'inventory_sha256':digest(a.inventory),'photo_manifest_sha256':digest(a.existing_photos)},'baseline':baseline_public,'claims':claims,'assets':assets,'associations':associations,'policy':{**multiview['policy'],'query_reference_used':False,'original_query_image_excluded':'pending_manual_confirmation','orientation_comparable':False},'coverage':{'candidate_count':10,'covered_candidates':multiview['covered_candidate_count'],'association_count':len(associations),'unique_assets':len(assets),'existing_assets_reused':reuse,'new_assets_required':new,'estimated_new_bytes':round(len(new)*sum(sizes)/len(sizes)),'maximum_new_bytes':len(new)*8_000_000},'limitations':['development_case','no_ground_truth_loaded','camera_proximity_does_not_prove_visibility','claims_require_human_review']}
 doc['fixture_id']='h11-visual-fixture-sha256-'+hashlib.sha256(canonical_bytes(doc)).hexdigest();a.output_root.mkdir(parents=True,exist_ok=True);(a.output_root/'fixture.json').write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps({'fixture_id':doc['fixture_id'],'claims':len(claims['claims']),'associations':len(associations),'assets':len(assets),'reused':len(reuse),'new':len(new),'estimated_new_bytes':doc['coverage']['estimated_new_bytes']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
