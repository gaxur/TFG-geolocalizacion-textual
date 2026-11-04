#!/usr/bin/env python3
"""Congela smoke H11 de calidad: 5 candidatos, 15 assets, sin claims/ranking/GT."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_quality_gate import canonical_bytes,freeze_quality_reserves
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,doc):path.write_bytes(canonical_bytes(doc)+b'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--base-policy',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();fixture=json.loads(a.fixture.read_text());assets_doc=json.loads(a.assets.read_text());inventory=json.loads(a.inventory.read_text());root=a.output_root;root.mkdir(parents=True,exist_ok=True)
 if fixture.get('contract_version')!='h11-visual-execution-fixture-v1' or fixture.get('fixture_role')!='development' or fixture.get('policy',{}).get('ground_truth_used') is not False or fixture.get('policy',{}).get('query_reference_used') is not False or any(token in json.dumps(fixture.get('policy',{})) for token in ('H26','H38','I01')):raise ValueError('fixture no es desarrollo H11 seguro')
 assets={str(row['image_id']):row for row in assets_doc['assets'] if row.get('status')=='downloaded'};inventory_by={str(row['image_id']):row for row in inventory['images']};by_candidate={}
 for association in fixture['associations']:
  image_id=str(association['image_id']);asset=assets.get(image_id)
  if asset is None or image_id not in inventory_by:continue
  path=(a.assets.parent/asset['logical_path']).resolve()
  if not path.is_file() or path.stat().st_size!=asset['size_bytes'] or digest(path)!=asset['sha256']:raise ValueError('asset histórico sin integridad')
  by_candidate.setdefault(association['candidate_id'],set()).add(image_id)
 selected=sorted(candidate_id for candidate_id,ids in by_candidate.items() if len(ids)>=3)[:5]
 if len(selected)!=5:raise ValueError('no hay cinco candidatos con tres assets')
 candidate_by={row['candidate_id']:row for row in fixture['baseline']['results']};candidates=[{key:candidate_by[cid][key] for key in ('candidate_id','latitude','longitude')} for cid in selected]
 allowed_ids={image_id for cid in selected for image_id in by_candidate[cid]};images=[row for image_id,row in inventory_by.items() if image_id in allowed_ids];plan=freeze_quality_reserves(candidates,images,maximum_radius_m=100,reserve_depth=3)
 if len(plan['reserves'])!=15:raise ValueError('smoke no produjo 15 reservas')
 selected_asset_ids={row['image_id'] for row in plan['reserves']};smoke_assets=[]
 for image_id in sorted(selected_asset_ids):
  row=assets[image_id];smoke_assets.append({key:row[key] for key in ('image_id','logical_path','sha256','size_bytes','media_type','license','license_url','attribution','acquired_at_utc')})
 candidates_doc={'schema_version':'1.0','contract_version':'visual-quality-smoke-candidates-v1','partition':'development_historical_h11','candidate_ids':selected,'selection':'lexicographically_first_five_candidates_with_at_least_three_hash_valid_local_assets','protocol':{'pixels_used_for_selection':False,'ground_truth_used':False,'claims_used':False,'rankings_used_for_selection':False,'h26_h37_used':False,'h38_h61_used':False,'i01_i20_used':False},'inputs':{'fixture_sha256':digest(a.fixture),'asset_manifest_sha256':digest(a.assets),'inventory_sha256':digest(a.inventory)}}
 asset_document={'schema_version':'1.0','contract_version':'visual-quality-smoke-assets-v1','asset_count':len(smoke_assets),'network_required':False,'asset_root':str(a.assets.parent),'source_asset_manifest_sha256':digest(a.assets),'assets':smoke_assets}
 policy=json.loads(a.base_policy.read_text());policy['enabled']=True;policy['status']='pending_explicit_gpu_authorization';policy['limits'].update({'target_accepted_images_per_candidate':1,'maximum_images_inspected_per_candidate':3,'maximum_images_downloaded_per_query':1,'maximum_quality_vlm_calls':15,'maximum_claim_vlm_calls':1,'maximum_replacements_per_candidate':2,'maximum_sequences_per_candidate':3,'maximum_wall_seconds':300,'maximum_downloaded_bytes':1})
 write(root/'candidates.json',candidates_doc);write(root/'reserve-plan.json',plan);write(root/'asset-manifest.json',asset_document);write(root/'policy.json',policy)
 authorization={'schema_version':'1.0','contract_version':'visual-quality-smoke-authorization-v1','authorization_id':'visual-quality-h11-five-candidate-smoke-v1','approved':False,'approved_by':None,'approved_at_utc':None,'expires_at_utc':None,'gpu_authorized':False,'purpose':'technical_visual_quality_smoke_only','partition':'development_historical_h11','candidate_count':5,'maximum_images_per_candidate':3,'maximum_quality_vlm_calls':15,'network_permitted':False,'downloads_permitted':False,'claims_permitted':False,'reranking_permitted':False,'ground_truth_permitted':False,'geographic_evaluation_permitted':False,'training_permitted':False,'fine_tuning_permitted':False,'h26_h37_permitted':False,'h38_h61_permitted':False,'i01_i20_permitted':False,'policy_sha256':digest(root/'policy.json'),'reserves_sha256':digest(root/'reserve-plan.json'),'assets_sha256':digest(root/'asset-manifest.json'),'source_fixture_sha256':digest(a.fixture),'source_asset_manifest_sha256':digest(a.assets),'source_inventory_sha256':digest(a.inventory),'candidate_ids':selected};write(root/'authorization.request.json',authorization)
 print(json.dumps({'candidates':selected,'plan_id':plan['plan_id'],'reserves':len(plan['reserves']),'assets':len(smoke_assets),'asset_bytes':sum(row['size_bytes'] for row in smoke_assets),'authorization_approved':False},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
