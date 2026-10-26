#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import atomic_annotation_template,canonical_bytes,compile_atomic_claims

DEFAULT_QUERIES=("H18","H22","H23","H25")
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description='Prepara nuevas anotaciones atómicas sin consultar predicciones VLM');p.add_argument('--spec',type=Path,default=ROOT/'config/madrid_h11_h25_independent.json');p.add_argument('--photos',type=Path,default=ROOT/'results/generated/mapillary/visual-pilot-v1/photo-manifest.json');p.add_argument('--output',type=Path,required=True);p.add_argument('--query-ids',nargs='*',default=list(DEFAULT_QUERIES));p.add_argument('--max-claims-per-query',type=int,default=6);a=p.parse_args();spec=json.loads(a.spec.read_text());photos=json.loads(a.photos.read_text());selected=set(a.query_ids);observations={r['query_id']:r for r in spec['observations']};claim_sets=[]
 for query_id in a.query_ids:
  observation=observations[query_id];compiled=compile_atomic_claims(observation['text'],observation['proper_toponyms']);claims=sorted(compiled['claims'],key=lambda r:(r['requires_ocr'] is False,r['specificity']!='distinctive',r['requires_orientation'],r['evidence']['span']['start']))[:a.max_claims_per_query];claim_sets.append({'query_id':query_id,'claims':claims,'source_text_sha256':compiled['source_text_sha256']})
 associations=[];seen=set()
 for photo in photos['photos']:
  if photo['status']!='downloaded' or photo['query_id'] not in selected:continue
  key=(photo['query_id'],photo['candidate_id'],photo['image_id'])
  if key in seen:continue
  seen.add(key);associations.append({'query_id':photo['query_id'],'candidate_id':photo['candidate_id'],'image_id':photo['image_id']})
 template=atomic_annotation_template(claim_sets,associations);doc={'schema_version':'1.0','contract_version':'visual-atomic-expanded-annotation-fixture-v1','fixture_role':'development_expansion_not_independent_test','inputs':{'spec_sha256':digest(a.spec),'photo_manifest_sha256':digest(a.photos)},'query_ids':a.query_ids,'claim_sets':claim_sets,'associations':associations,'annotation_template':template,'policy':{'predictions_used_for_selection':False,'ground_truth_used':False,'maximum_claims_per_query':a.max_claims_per_query,'existing_downloaded_images_only':True,'sequence_dependence_requires_grouped_analysis':True},'limitations':['queries_previously_seen_in_whole_description_development','human_labels_pending','not_final_test']};doc['fixture_id']='visual-expanded-fixture-sha256-'+hashlib.sha256(canonical_bytes(doc)).hexdigest();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b'\n');print(json.dumps({'fixture_id':doc['fixture_id'],'queries':len(claim_sets),'claims':sum(len(r['claims']) for r in claim_sets),'images':len(associations),'pairs':len(template['records'])},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
