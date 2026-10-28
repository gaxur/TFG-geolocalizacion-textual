"""Planificación adaptativa por cobertura metadata-only, sin GT ni outputs VLM."""

from __future__ import annotations
import hashlib,json,math
from typing import Any,Mapping,Sequence
from .crs import wgs84_to_epsg25830
from .mapillary_visual_pilot import reject_ground_truth

class AdaptiveAcquisitionError(ValueError):pass
def canonical_bytes(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def freeze_policy(*,provider_id="mapillary",rounds=((25,2,2),(50,4,4),(100,8,8)),max_unique_assets_total=432,max_new_assets=391,max_jobs_per_model=11080,max_storage_bytes=3_128_000_000,max_asset_bytes=8_000_000):
 policy={"schema_version":"1.0","contract_version":"adaptive-visual-acquisition-policy-v1","policy_id":"","status":"frozen","mode":"coverage_adaptive","provider_id":provider_id,"candidate_scope":{"candidate_depth":50,"complete_symmetric_block":[1,50]},"rounds":[{"round":i+1,"max_radius_m":r,"cumulative_images_per_candidate":images,"cumulative_opportunity_groups_per_candidate":groups} for i,(r,images,groups) in enumerate(rounds)],"limits":{"max_rounds":len(rounds),"max_radius_m":rounds[-1][0],"max_images_per_candidate":rounds[-1][1],"max_opportunity_groups_per_candidate":rounds[-1][2],"max_unique_assets_total":max_unique_assets_total,"max_new_assets":max_new_assets,"max_jobs_per_model":max_jobs_per_model,"max_storage_bytes":max_storage_bytes,"max_asset_bytes":max_asset_bytes},"selection":{"allocation":"lexicographic_max_min_v1","sequence_diversity_first":True,"pixels_allowed":False,"vlm_outputs_allowed":False,"ground_truth_allowed":False},"stop":{"no_eligible_opportunities":True,"limits_are_hard":True,"supported_verdict_allowed":False}}
 policy["policy_id"]="adaptive-policy-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in policy.items() if k!="policy_id"})).hexdigest();validate_policy(policy);return policy
def validate_policy(policy):
 reject_ground_truth(policy,path="adaptive_policy");rounds=policy.get("rounds",[]);limits=policy.get("limits",{})
 if policy.get("contract_version")!="adaptive-visual-acquisition-policy-v1" or policy.get("status")!="frozen":raise AdaptiveAcquisitionError("política incompatible")
 expected="adaptive-policy-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in policy.items() if k!="policy_id"})).hexdigest()
 if policy.get("policy_id")!=expected or not rounds or any(rounds[i]["max_radius_m"]>=rounds[i+1]["max_radius_m"] for i in range(len(rounds)-1)):raise AdaptiveAcquisitionError("identidad o radios inválidos")
 if any(rounds[i]["cumulative_images_per_candidate"]>rounds[i+1]["cumulative_images_per_candidate"] for i in range(len(rounds)-1)) or limits.get("max_radius_m")>150 or limits.get("max_images_per_candidate")>16:raise AdaptiveAcquisitionError("cuotas o límites inválidos")
 if policy["selection"]!={"allocation":"lexicographic_max_min_v1","sequence_diversity_first":True,"pixels_allowed":False,"vlm_outputs_allowed":False,"ground_truth_allowed":False}:raise AdaptiveAcquisitionError("selección puede introducir fuga")
def _opportunities(candidates,images,max_radius):
 result=[]
 for candidate in candidates:
  cx,cy=wgs84_to_epsg25830(candidate["latitude"],candidate["longitude"])
  for image in images:
   ix,iy=wgs84_to_epsg25830(image["latitude"],image["longitude"]);distance=math.hypot(cx-ix,cy-iy)
   if distance>max_radius:continue
   group=image.get("sequence_id") or f"asset:{image['image_id']}";heading=image.get("orientation_degrees");bearing=math.degrees(math.atan2(cx-ix,cy-iy))%360;difference=abs((heading-bearing+180)%360-180) if heading is not None else None;panoramic=image.get("camera_type") in {"equirectangular","spherical","cylindrical"};band=0 if panoramic else 1 if difference is not None and difference<=45 else 2 if difference is not None and difference<=90 else 3
   result.append({"candidate_id":candidate["candidate_id"],"global_record_id":f"mapillary:{image['image_id']}","provider_record_id":image["image_id"],"opportunity_group_id":f"mapillary:{group}","distance_m":distance,"orientation_band":band,"quality_score":image.get("quality_score"),"width_px":image.get("width_px"),"height_px":image.get("height_px")})
 return result
def plan_adaptive(candidates:Sequence[Mapping[str,Any]],images:Sequence[Mapping[str,Any]],policy:Mapping[str,Any],*,existing_asset_ids=(),claims_per_candidate=1):
 reject_ground_truth(candidates,path="candidates");reject_ground_truth(images,path="images");validate_policy(policy)
 if len({c["candidate_id"] for c in candidates})!=len(candidates):raise AdaptiveAcquisitionError("candidatos duplicados")
 opportunities=_opportunities(candidates,images,policy["limits"]["max_radius_m"]);selected=[];selected_keys=set();assets=set(existing_asset_ids);new_assets=set();events=[]
 for round_policy in policy["rounds"]:
  while True:
   counts={c["candidate_id"]:sum(x["candidate_id"]==c["candidate_id"] for x in selected) for c in candidates};groups={c["candidate_id"]:{x["opportunity_group_id"] for x in selected if x["candidate_id"]==c["candidate_id"]} for c in candidates};eligible=[]
   for row in opportunities:
    key=(row["candidate_id"],row["global_record_id"])
    if key in selected_keys or row["distance_m"]>round_policy["max_radius_m"] or counts[row["candidate_id"]]>=round_policy["cumulative_images_per_candidate"]:continue
    new_group=row["opportunity_group_id"] not in groups[row["candidate_id"]]
    if not new_group and len(groups[row["candidate_id"]])<round_policy["cumulative_opportunity_groups_per_candidate"]:continue
    physical_new=row["provider_record_id"] not in assets
    if physical_new and len(new_assets)>=policy["limits"]["max_new_assets"]:continue
    projected_assets=len(assets|{row["provider_record_id"]})
    if projected_assets>policy["limits"]["max_unique_assets_total"] or (len(new_assets)+(1 if physical_new else 0))*policy["limits"]["max_asset_bytes"]>policy["limits"]["max_storage_bytes"]:continue
    projected_jobs=(len(selected)+1)*claims_per_candidate
    if projected_jobs>policy["limits"]["max_jobs_per_model"]:continue
    priority=(len(groups[row["candidate_id"]]),counts[row["candidate_id"]],0 if new_group else 1,row["orientation_band"],row["distance_m"],-(row.get("quality_score") or -1),-(row.get("width_px") or 0)*(row.get("height_px") or 0),row["candidate_id"],row["global_record_id"]);eligible.append((priority,row,physical_new))
   if not eligible:break
   _,row,physical_new=min(eligible,key=lambda item:item[0]);selected.append(row);selected_keys.add((row["candidate_id"],row["global_record_id"]));assets.add(row["provider_record_id"])
   if physical_new:new_assets.add(row["provider_record_id"])
  events.append({"round":round_policy["round"],"radius_m":round_policy["max_radius_m"],"selected_associations_cumulative":len(selected),"unique_assets_cumulative":len(assets),"new_assets_cumulative":len(new_assets)})
 coverage=[]
 for candidate in candidates:
  rows=[x for x in selected if x["candidate_id"]==candidate["candidate_id"]];groups={x["opportunity_group_id"] for x in rows};target=policy["limits"]["max_opportunity_groups_per_candidate"];coverage.append({"candidate_id":candidate["candidate_id"],"images":len(rows),"opportunity_groups":len(groups),"coverage":min(1,len(groups)/target)})
 doc={"schema_version":"1.0","contract_version":"adaptive-visual-acquisition-plan-v1","plan_id":"","policy_id":policy["policy_id"],"protocol":{"ground_truth_used":False,"vlm_outputs_used":False,"pixels_used":False,"chase_supported":False},"events":events,"associations":selected,"coverage":coverage,"summary":{"candidates":len(candidates),"associations":len(selected),"unique_assets":len(assets),"new_assets":len(new_assets),"zero_coverage_candidates":sum(not row["images"] for row in coverage),"coverage_macro":sum(row["coverage"] for row in coverage)/len(coverage) if coverage else 0,"coverage_min":min((row["coverage"] for row in coverage),default=0)},"stop_reason":"rounds_complete_or_no_eligible_opportunities"};doc["plan_id"]="adaptive-plan-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in doc.items() if k!="plan_id"})).hexdigest();return doc
