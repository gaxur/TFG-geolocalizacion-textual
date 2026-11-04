#!/usr/bin/env python3
"""Plan candidate-neutral Top-50/100; no lee referencias ni métricas oracle."""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.camera_candidate_spatial import annotate_ambiguity,classify_camera_candidate
from src.tfg_phase0.mapillary_coverage import canonical_bytes

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def claim_contract(row, source_sha):
 value={"text_es":row["text_es"],"human_kind":row["kind"]};payload={"source_text_sha256":source_sha,"kind":row["kind"],"value":value,"evidence":{"text":row["text_es"],"span":None},"specificity":"distinctive" if row["kind"]!="scene" else "generic","requires_ocr":row["kind"]=="visible_text","requires_orientation":row["kind"]=="relation"};payload["claim_id"]="h26-h37-claim-sha256-"+hashlib.sha256(canonical_bytes({"query_id":row["query_id"],**payload})).hexdigest();return payload
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--rankings",type=Path,required=True);p.add_argument("--inventory",type=Path,required=True);p.add_argument("--catalog",type=Path,required=True);p.add_argument("--top-n",type=int,choices=(50,100),required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();campaign=json.loads(a.campaign.read_text());rankings=json.loads(a.rankings.read_text());inventory=json.loads(a.inventory.read_text());catalog=json.loads(a.catalog.read_text())
 # Extrae únicamente texto/claims: las posiciones de referencia no participan en ninguna selección.
 reference_ids={row["reference_asset"]["image_id"] for row in campaign["observations"]};reference_sequences={row["reference_asset"]["sequence_id"] for row in campaign["observations"]}
 queries=[]
 for row in campaign["observations"]:
  source_sha=hashlib.sha256(row["description"]["text_es"].encode()).hexdigest();claims=[]
  for raw in row["claims"]:
   claims.append(claim_contract({"query_id":row["query_id"],**raw},source_sha))
  queries.append({"query_id":row["query_id"],"text":row["description"]["text_es"],"text_sha256":source_sha,"claims":claims})
 candidates_by_id={row["candidate_id"]:row for row in catalog["candidates"]};ranking_by={q["query_id"]:r for q,r in zip(rankings["queries"],rankings["rankings"],strict=True)};images=[row for row in inventory["images"] if row["image_id"] not in reference_ids and row.get("sequence_id") not in reference_sequences]
 selected=[];all_candidate_ids={candidate["candidate_id"] for ranking in ranking_by.values() for candidate in ranking["results"][:a.top_n]};gallery=[candidates_by_id[value] for value in sorted(all_candidate_ids)]
 spatial=[]
 for image in images:
  for candidate in gallery:
   row=classify_camera_candidate(image,candidate,round_radius_m=100);spatial.append({"global_record_id":f"mapillary:{image['image_id']}","candidate_id":candidate["candidate_id"],**row})
 ambiguity={(r["global_record_id"],r["candidate_id"]):r for r in annotate_ambiguity(spatial)}
 for query in queries:
  for baseline in ranking_by[query["query_id"]]["results"][:a.top_n]:
   cid=baseline["candidate_id"];eligible=[]
   for image in images:
    geo=ambiguity[(f"mapillary:{image['image_id']}",cid)]
    if geo["center_distance_m"]>100:continue
    rank={"camera_inside_candidate":0,"camera_outside_view_compatible":1,"spatially_ambiguous":2,"orientation_incompatible":4,"insufficient_orientation_metadata":4,"not_eligible":5}.get(geo["classification"],5)
    priority=(rank,geo["competing_candidate_count"],geo["surface_distance_m"],geo["center_distance_m"],-(image.get("quality_score") or -1),-(image.get("width_px") or 0)*(image.get("height_px") or 0),image["image_id"]);eligible.append((priority,image,geo))
   if eligible:
    _,image,geo=min(eligible,key=lambda value:value[0]);selected.append({"query_id":query["query_id"],"baseline_rank":baseline["rank"],"candidate_id":cid,"image_id":image["image_id"],"sequence_id":image.get("sequence_id"),"classification":geo["classification"],"competing_candidate_count":geo["competing_candidate_count"],"center_distance_m":geo["center_distance_m"],"surface_distance_m":geo["surface_distance_m"],"orientation_comparable":geo["classification"] in {"camera_inside_candidate","camera_outside_view_compatible"}})
 claims_by={q["query_id"]:q["claims"] for q in queries};logical=sum(len(claims_by[row["query_id"]]) for row in selected);abstentions=sum(sum(claim["requires_orientation"] and not row["orientation_comparable"] for claim in claims_by[row["query_id"]]) for row in selected);assets={row["image_id"] for row in selected}
 document={"schema_version":"1.0","contract_version":"h26-h37-candidate-visual-plan-v1","plan_id":"","inputs":{"campaign_sha256":digest(a.campaign),"rankings_sha256":digest(a.rankings),"inventory_sha256":digest(a.inventory),"catalog_sha256":digest(a.catalog)},"scope":{"query_ids":[q["query_id"] for q in queries],"top_n":a.top_n,"views_per_slot":1,"maximum_radius_m":100},"protocol":{"ground_truth_used":False,"reference_coordinates_used":False,"reference_images_excluded":True,"reference_sequences_excluded":True,"reference_images_used":False,"vlm_outputs_used":False,"pixels_used":False,"selection":"one_best_geometric_metadata_view_per_candidate_slot"},"queries":queries,"associations":selected,"asset_ids":sorted(assets),"summary":{"queries":12,"candidate_slots":12*a.top_n,"covered_slots":len(selected),"zero_coverage_slots":12*a.top_n-len(selected),"logical_tasks_per_model":logical,"automatic_abstentions_per_model":abstentions,"generate_calls_per_model":logical-abstentions,"unique_assets":len(assets),"estimated_bytes":round(len(assets)*127767.625)}};document["plan_id"]="h26-h37-candidate-visual-plan-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in document.items() if k!="plan_id"})).hexdigest();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(document)+b"\n");print(json.dumps({"plan_id":document["plan_id"],"summary":document["summary"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
