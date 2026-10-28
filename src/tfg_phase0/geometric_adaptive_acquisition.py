"""Variante adaptativa con prioridad cámara-celda, sin cambiar elegibilidad histórica."""

from __future__ import annotations
import hashlib,json
from typing import Any,Mapping,Sequence
from .adaptive_visual_acquisition import canonical_bytes,validate_policy
from .camera_candidate_spatial import annotate_ambiguity,classify_camera_candidate
from .mapillary_visual_pilot import reject_ground_truth

def plan_geometric_adaptive(candidate_slots:Sequence[Mapping[str,Any]],gallery_candidates:Sequence[Mapping[str,Any]],images:Sequence[Mapping[str,Any]],policy:Mapping[str,Any],*,claims_per_slot=1):
 reject_ground_truth(candidate_slots,path="candidate_slots");reject_ground_truth(gallery_candidates,path="gallery_candidates");reject_ground_truth(images,path="images");validate_policy(policy)
 gallery_rows=[]
 for image in images:
  for candidate in gallery_candidates:
   spatial=classify_camera_candidate(image,candidate,round_radius_m=policy["limits"]["max_radius_m"])
   gallery_rows.append({"global_record_id":f"mapillary:{image['image_id']}","candidate_id":candidate["candidate_id"],**spatial})
 ambiguity={(row["global_record_id"],row["candidate_id"]):row for row in annotate_ambiguity(gallery_rows)};opportunities=[]
 for slot in candidate_slots:
  candidate=slot["candidate"]
  for image in images:
   spatial=ambiguity[(f"mapillary:{image['image_id']}",candidate["candidate_id"])]
   if spatial["center_distance_m"]>policy["limits"]["max_radius_m"]:continue
   group=image.get("sequence_id") or f"asset:{image['image_id']}";rank={"camera_inside_candidate":0,"camera_outside_view_compatible":4,"spatially_ambiguous":6,"orientation_incompatible":7,"insufficient_orientation_metadata":7,"not_eligible":9}.get(spatial["classification"],8)
   opportunities.append({"slot_id":slot["slot_id"],"query_id":slot["query_id"],"candidate_id":candidate["candidate_id"],"global_record_id":f"mapillary:{image['image_id']}","provider_record_id":image["image_id"],"opportunity_group_id":f"mapillary:{group}","distance_m":spatial["center_distance_m"],"surface_distance_m":spatial["surface_distance_m"],"geometric_rank":rank,"classification":spatial["classification"],"competing_candidate_count":spatial["competing_candidate_count"],"orientation_band":0 if image.get("camera_type") in {"equirectangular","spherical","cylindrical"} else 1,"quality_score":image.get("quality_score"),"width_px":image.get("width_px"),"height_px":image.get("height_px")})
 selected=[];keys=set();assets=set();events=[]
 for round_policy in policy["rounds"]:
  while True:
   counts={slot["slot_id"]:sum(row["slot_id"]==slot["slot_id"] for row in selected) for slot in candidate_slots};groups={slot["slot_id"]:{row["opportunity_group_id"] for row in selected if row["slot_id"]==slot["slot_id"]} for slot in candidate_slots};eligible=[]
   for row in opportunities:
    key=(row["slot_id"],row["global_record_id"])
    if key in keys or row["distance_m"]>round_policy["max_radius_m"] or counts[row["slot_id"]]>=round_policy["cumulative_images_per_candidate"]:continue
    new_group=row["opportunity_group_id"] not in groups[row["slot_id"]]
    if not new_group and len(groups[row["slot_id"]])<round_policy["cumulative_opportunity_groups_per_candidate"]:continue
    if len(assets|{row["provider_record_id"]})>policy["limits"]["max_unique_assets_total"] or (len(selected)+1)*claims_per_slot>policy["limits"]["max_jobs_per_model"]:continue
    priority=(len(groups[row["slot_id"]]),counts[row["slot_id"]],0 if new_group else 1,row["geometric_rank"],row["competing_candidate_count"],row["surface_distance_m"],row["distance_m"],-(row.get("quality_score") or -1),row["slot_id"],row["global_record_id"]);eligible.append((priority,row))
   if not eligible:break
   _,row=min(eligible,key=lambda item:item[0]);selected.append(row);keys.add((row["slot_id"],row["global_record_id"]));assets.add(row["provider_record_id"])
  events.append({"round":round_policy["round"],"selected_associations_cumulative":len(selected),"unique_assets_cumulative":len(assets)})
 coverage=[]
 for slot in candidate_slots:
  rows=[row for row in selected if row["slot_id"]==slot["slot_id"]];groups={row["opportunity_group_id"] for row in rows};coverage.append({"slot_id":slot["slot_id"],"query_id":slot["query_id"],"candidate_id":slot["candidate"]["candidate_id"],"images":len(rows),"opportunity_groups":len(groups),"coverage":min(1,len(groups)/policy["limits"]["max_opportunity_groups_per_candidate"])})
 doc={"schema_version":"1.0","contract_version":"geometric-adaptive-visual-acquisition-plan-v1","plan_id":"","policy_id":policy["policy_id"],"protocol":{"ground_truth_used":False,"pixels_used":False,"vlm_outputs_used":False,"fov_basis":"hypothetical_90_degrees","eligibility_compatibility_gate":"historical_center_distance","geometry_used_for_priority":True},"events":events,"associations":selected,"coverage":coverage,"summary":{"slots":len(candidate_slots),"associations":len(selected),"unique_assets":len(assets),"zero_coverage_slots":sum(not row["images"] for row in coverage),"coverage_macro":sum(row["coverage"] for row in coverage)/len(coverage),"coverage_min":min(row["coverage"] for row in coverage)},"limitations":["hypothetical_fov","geometric_compatibility_not_visibility","center_distance_gate_retained_for_inventory_completeness"]};doc["plan_id"]="geometric-adaptive-plan-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in doc.items() if k!="plan_id"})).hexdigest();return doc
