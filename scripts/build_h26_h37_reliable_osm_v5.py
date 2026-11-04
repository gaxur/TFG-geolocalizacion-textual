#!/usr/bin/env python3
"""Congela diagnóstico, confianza, políticas y ablaciones v5 sin ground truth."""
from __future__ import annotations
import argparse,copy,hashlib,json,re
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.reliable_osm_promotion import build_reliable_variants,catalog_statistics,classify_description_claims,promotion_confidence,visual_support_index

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load_jsonl(path):return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def classify_free_text(text):
 patterns={"visual_attributes":r"\b(?:fachada|roj[oa]|amarill[oa]|clar[oa]|gris|verde|piedra|ladrillo|curv[oa]|balcones?|barandillas?|ornamental|adoquinad[oa]|asfaltad[oa])\b","mixed_attributes":r"\b(?:cartel|letrero|logotipo|cruz luminosa|r[oó]tulo)\b","unverifiable":r"\b(?:personas?|veh[ií]culos?|autob[uú]s|tr[aá]fico)\b"}
 return {key:sorted({m.group(0) for m in re.finditer(pattern,text,re.I)},key=str.casefold) for key,pattern in patterns.items()}
def variant_from_confidence(atlas,rows,policy):
 variants,audit=build_reliable_variants(atlas,rows);return variants[policy],audit
def main():
 p=argparse.ArgumentParser();p.add_argument("--v4-rankings",type=Path,required=True);p.add_argument("--objects",type=Path,required=True);p.add_argument("--associations",type=Path,required=True);p.add_argument("--visual-rankings",type=Path,required=True);p.add_argument("--visual-plan",type=Path,required=True);p.add_argument("--diagnostic-output",type=Path,required=True);p.add_argument("--confidence-output",type=Path,required=True);p.add_argument("--rankings-output",type=Path,required=True);a=p.parse_args()
 v4=json.loads(a.v4_rankings.read_text());objects={row["osm_ref"]:row for row in load_jsonl(a.objects)};associations=load_jsonl(a.associations);catalog=catalog_statistics(objects,associations);visual=json.loads(a.visual_rankings.read_text());plan=json.loads(a.visual_plan.read_text());claims={row["query_id"]:row["claims"] for row in plan["queries"]};aggregates={qid:row["original_aggregate"] for qid,row in visual["queries"].items()};visual_index=visual_support_index(claims,aggregates)
 diagnostics=[];confidence_queries={};ranking_queries={}
 for qid,query in sorted(v4["queries"].items()):
  textual=query["structured_evidence"]["textual_evidence"];classifications=classify_description_claims(textual);classifications.update(classify_free_text(next(row["text"] for row in plan["queries"] if row["query_id"]==qid)))
  candidates=[]
  for candidate in query["structured_evidence"]["candidate_evidence"]:
   row=promotion_confidence(query_id=qid,candidate=candidate,textual_evidence=textual,catalog=catalog,visual=visual_index.get((qid,candidate["candidate_id"])))
   candidates.append(row)
  atlas=query["variants"]["atlas_v3"]
  main_variants,audit=build_reliable_variants(atlas,candidates)
  ablations={}
  settings={
   "ablation_no_global_ambiguity":{"require_global_ambiguity":False},
   "ablation_no_nominal_consistency":{"require_nominal_consistency":False},
   "ablation_no_object_grouping":{"group_objects":False},
   "ablation_no_visual_support":{"use_visual":False},
  }
  for name,kwargs in settings.items():
   rows=[promotion_confidence(query_id=qid,candidate=candidate,textual_evidence=textual,catalog=catalog,visual=visual_index.get((qid,candidate["candidate_id"])),**kwargs) for candidate in query["structured_evidence"]["candidate_evidence"]]
   ablations[name],_=variant_from_confidence(atlas,rows,"confidence_abstention")
  names_only=[];categories_only=[]
  for candidate in query["structured_evidence"]["candidate_evidence"]:
   names=copy.deepcopy(candidate);names["matches"]=[row for row in names["matches"] if row.get("kind")!="category"]
   categories=copy.deepcopy(candidate);categories["matches"]=[row for row in categories["matches"] if row.get("kind")=="category"]
   names_only.append(promotion_confidence(query_id=qid,candidate=names,textual_evidence=textual,catalog=catalog,visual=visual_index.get((qid,candidate["candidate_id"]))))
   categories_only.append(promotion_confidence(query_id=qid,candidate=categories,textual_evidence=textual,catalog=catalog,visual=visual_index.get((qid,candidate["candidate_id"]))))
  ablations["ablation_names_only"],_=variant_from_confidence(atlas,names_only,"confidence_abstention")
  ablations["ablation_categories_only"],_=variant_from_confidence(atlas,categories_only,"confidence_abstention")
  variants={"baseline":query["variants"]["baseline"],"atlas_v3":atlas,"structured_osm_v4":query["variants"]["structured_osm"],**main_variants,**ablations}
  ranking_queries[qid]={"baseline_results":query["baseline_results"],"variants":variants,"promotion_audit":audit,"confidence_candidates":candidates}
  confidence_queries[qid]={"summary":{"high":sum(row["confidence"]=="high" for row in candidates),"medium":sum(row["confidence"]=="medium" for row in candidates),"low":sum(row["confidence"]=="low" for row in candidates),"none":sum(row["confidence"]=="none" for row in candidates)},"selected":audit,"candidates":candidates}
  if qid in {"H28","H30","H31","H32","H36"}:
   promoted=query["promotion_audit"]["promoted_candidate_id"];v4_candidate=next((row for row in query["structured_evidence"]["candidate_evidence"] if row["candidate_id"]==promoted),None);v5_candidate=next((row for row in candidates if row["candidate_id"]==promoted),None);diagnostics.append({"query_id":qid,"v4_promoted_candidate":promoted,"v4_evidence":v4_candidate,"v5_confidence":v5_candidate,"claim_classification":classifications,"atlas_rank":atlas.index(promoted)+1 if promoted in atlas else None,"visual":visual_index.get((qid,promoted))})
 inputs={"v4_rankings_sha256":digest(a.v4_rankings),"objects_sha256":digest(a.objects),"associations_sha256":digest(a.associations),"visual_rankings_sha256":digest(a.visual_rankings),"visual_plan_sha256":digest(a.visual_plan)}
 diagnostic={"schema_version":"1.0","contract_version":"h26-h37-v5-mechanism-diagnostic","protocol":{"ground_truth_used":False,"queries":"H26-H37","focus_queries":["H28","H30","H31","H32","H36"],"visual_inference_reused_only":True},"inputs":inputs,"catalog":{"candidate_count":catalog["candidate_count"],"name_count":len(catalog["name_cells"]),"object_with_cells":len(catalog["object_cells"])},"rows":diagnostics,"complementarity":{"ct2l_raster":{"class":"A","evidence":"north_up_z18_osm_carto_pixels_without_f3_tags_or_ids","native_crop_px":256,"published_px":512,"model_input_px":336,"approximate_projected_width_m":152.87,"represented":["road_and_building_geometry","selected_osm_carto_icons","selected_collision_limited_names","landuse_and_water_styling"],"not_explicit":["osm_ids","raw_tag_dictionary","candidate_cell_boundary","exact_f3_predicates","center_to_geometry_distance"],"causal_attention_inferred":False},"structured_f3":{"class":"B","evidence":"full_tags_identity_intersection_predicates_center_distance_and_partial_relation_context","source_aligned_with_ct2l_raster":False,"visibility_inferred":False},"street_visual":{"class":"C","evidence":"appearance_signage_material_viewpoint_and_occlusion","camera_position_inferred_from_object":False},"unavailable":{"class":"D","evidence":"model_attention_exact_visibility_and_missing_source_facts"}}}
 confidence_doc={"schema_version":"1.0","contract_version":"h26-h37-v5-promotion-confidence","protocol":{"ground_truth_used":False,"heuristic_not_probability":True,"global_catalog_ambiguity":True,"same_object_tags_not_independent":True,"same_category_objects_grouped":True,"visual_support_requires_specific_supported_claim":True,"unverifiable_is_neutral":True},"inputs":inputs,"queries":confidence_queries}
 rankings={"schema_version":"1.0","contract_version":"h26-h37-reliable-osm-rankings-v5","ranking_set_id":"","status":"exploratory_development_frozen_before_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"candidate_scope":"same_ct2l_top100","fallback":"atlas_v3","maximum_promotions_per_query":1,"top1_protected":"never_changes_atlas_rank1","top1_conditioned":"high_confidence_only","confidence_abstention":"high_to_rank1_medium_to_rank5_else_atlas","thresholds_predefined_from_observable_semantics_not_gt":True,"ablations":["names_only","categories_only","no_global_ambiguity","no_nominal_consistency","no_object_grouping","no_visual_support"]},"inputs":inputs,"queries":ranking_queries};rankings["ranking_set_id"]="h26-h37-reliable-osm-v5-sha256-"+hashlib.sha256(canonical({k:v for k,v in rankings.items() if k!="ranking_set_id"})).hexdigest()
 for path,doc in ((a.diagnostic_output,diagnostic),(a.confidence_output,confidence_doc),(a.rankings_output,rankings)):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"ranking_set_id":rankings["ranking_set_id"],"selected":{qid:row["selected"] for qid,row in confidence_queries.items()}},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
