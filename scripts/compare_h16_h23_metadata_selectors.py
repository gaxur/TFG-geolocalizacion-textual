#!/usr/bin/env python3
"""Compara selector histórico, adaptativo y geométrico sobre inventario congelado."""

from __future__ import annotations
import argparse,collections,hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.adaptive_visual_acquisition import freeze_policy,plan_adaptive
from src.tfg_phase0.geometric_adaptive_acquisition import plan_geometric_adaptive

def summarize(name,rows,slots):
 by=collections.defaultdict(list)
 for row in rows:by[row.get("slot_id") or f"{row['query_id']}:{row['candidate_id']}"] .append(row)
 # The historical rows have no slot_id; use explicit query:candidate identity.
 counts=[];groups=[];angles=[];distances=[];ambiguous=0
 for slot in slots:
  key=slot["slot_id"];selected=by.get(key,[]);counts.append(len(selected));groups.append(len({row.get("opportunity_group_id") or row.get("sequence_id") or f"image:{row['image_id']}" for row in selected}));angles.append(len({row.get("orientation_band") for row in selected}));distances.extend(row.get("distance_m",row.get("distance_to_candidate_m")) for row in selected);ambiguous+=sum(row.get("classification")=="spatially_ambiguous" for row in selected)
 return {"selector":name,"slots":len(slots),"covered_slots":sum(value>0 for value in counts),"zero_coverage_slots":sum(value==0 for value in counts),"coverage_macro_images":statistics.fmean(value/8 for value in counts),"coverage_min_images":min(counts),"mean_independent_groups":statistics.fmean(groups),"minimum_independent_groups":min(groups),"mean_orientation_bins":statistics.fmean(angles),"unique_physical_images":len({row.get("provider_record_id") or row.get("image_id") for row in rows}),"associations":len(rows),"ambiguous_associations":ambiguous,"distance_distribution":{"min":min(distances) if distances else None,"median":statistics.median(distances) if distances else None,"max":max(distances) if distances else None}}
def main():
 p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,required=True);p.add_argument("--inventory",type=Path,required=True);p.add_argument("--catalog",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();fixture=json.loads(a.fixture.read_text());inventory=json.loads(a.inventory.read_text());catalog=json.loads(a.catalog.read_text());slots=[]
 for query in fixture["queries"]:
  for candidate in query["baseline_results"]:slots.append({"slot_id":f"{query['query_id']}:{candidate['candidate_id']}","query_id":query["query_id"],"candidate":candidate})
 policy=freeze_policy(max_unique_assets_total=1000,max_new_assets=1000,max_jobs_per_model=100000,max_storage_bytes=8_000_000_000);flat_candidates=[{"candidate_id":slot["slot_id"],"latitude":slot["candidate"]["latitude"],"longitude":slot["candidate"]["longitude"]} for slot in slots];adaptive=plan_adaptive(flat_candidates,inventory["images"],policy,claims_per_candidate=1);adaptive_rows=[{**row,"slot_id":row["candidate_id"]} for row in adaptive["associations"]];geometric=plan_geometric_adaptive(slots,catalog["candidates"],inventory["images"],policy,claims_per_slot=1);historical=[{**row,"slot_id":f"{row['query_id']}:{row['candidate_id']}"} for row in fixture["associations"]]
 summaries=[summarize("historical_fixed",historical,slots),summarize("coverage_adaptive",adaptive_rows,slots),summarize("geometric_adaptive",geometric["associations"],slots)];sets={"historical":{(r["slot_id"],r.get("image_id")) for r in historical},"adaptive":{(r["slot_id"],r["provider_record_id"]) for r in adaptive_rows},"geometric":{(r["slot_id"],r["provider_record_id"]) for r in geometric["associations"]}}
 doc={"schema_version":"1.0","contract_version":"h16-h23-metadata-selector-comparison-v1","inputs":{"fixture_sha256":hashlib.sha256(a.fixture.read_bytes()).hexdigest(),"inventory_sha256":hashlib.sha256(a.inventory.read_bytes()).hexdigest(),"catalog_sha256":hashlib.sha256(a.catalog.read_bytes()).hexdigest()},"protocol":{"same_candidate_slots":True,"same_inventory":True,"ground_truth_used":False,"no_pixels":True,"no_vlm_outputs":True},"summaries":summaries,"pairwise_changes":{"historical_vs_adaptive":len(sets["historical"]^sets["adaptive"]),"adaptive_vs_geometric":len(sets["adaptive"]^sets["geometric"]),"historical_vs_geometric":len(sets["historical"]^sets["geometric"])},"adaptive_plan":adaptive,"geometric_plan":geometric,"limitations":["metadata_only_not_visual_quality","hypothetical_fov","historical_uses_haversine_center_while_new_uses_projected_center_for_rounds"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"summaries":summaries,"changes":doc["pairwise_changes"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
