#!/usr/bin/env python3
"""Matriz causal y plan Commons/OSM sin red ni nuevas inferencias."""
from __future__ import annotations
import argparse,collections,hashlib,json,re,unicodedata
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def norm(text):return " ".join("".join(c for c in unicodedata.normalize("NFKD",text.casefold()) if not unicodedata.combining(c)).split())
DISTINCTIVE=re.compile(r"\b(?:cartel|letrero|placa|museo|farmacia|starbucks|sportium|alonzo|escarpin|la concha|torre|reloj|arco|monumental|pasaje|mural|cruz)\b",re.I)
OSM_DISTINCTIVE={"tourism":{"museum","attraction","artwork"},"historic":{"monument","memorial","building","archaeological_site"},"amenity":{"pharmacy","place_of_worship","theatre"},"man_made":{"tower"},"building":{"church","cathedral","civic","historic"}}
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--recoverability",type=Path,required=True);p.add_argument("--rankings",type=Path,required=True);p.add_argument("--evaluation",type=Path,required=True);p.add_argument("--visual-plan",type=Path,required=True);p.add_argument("--osm-associations",type=Path,required=True);p.add_argument("--osm-objects",type=Path,required=True);p.add_argument("--output-matrix",type=Path,required=True);p.add_argument("--output-commons",type=Path,required=True);p.add_argument("--output-osm-guide",type=Path,required=True);a=p.parse_args();campaign=json.load(open(a.campaign));recover=json.load(open(a.recoverability));rankings=json.load(open(a.rankings));evaluation=json.load(open(a.evaluation));plan=json.load(open(a.visual_plan));observations={r["query_id"]:r for r in campaign["observations"]};recover_by={r["query_id"]:r for r in recover["rows"]};queries=rankings["queries"];objects={r["osm_ref"]:r for r in map(json.loads,a.osm_objects.read_text().splitlines())};by_candidate=collections.defaultdict(list)
 for row in map(json.loads,a.osm_associations.read_text().splitlines()):
  if row["osm_ref"] in objects:by_candidate[row["candidate_id"]].append(objects[row["osm_ref"]])
 matrix=[];commons_queries=[];osm_needs=[]
 for qid,query in sorted(queries.items()):
  observation=observations[qid];claims=observation["claims"];distinctive=[r for r in claims if DISTINCTIVE.search(norm(r["text_es"]))];aggregate={r["candidate_id"]:r for r in query["original_aggregate"]["candidates"]};candidate_rows=query["baseline_results"][:100];shared_images=collections.Counter(r["image_id"] for r in plan["associations"] if r["query_id"]==qid);nearest=recover_by[qid];nearest_row=next((r for r in candidate_rows if r["rank"]==nearest["nearest_rank_top100"]),None);nearest_aggregate=aggregate.get(nearest_row["candidate_id"]) if nearest_row else None
  # Causal flags are multi-label and descriptive, not a single asserted cause.
  flags=[]
  if not nearest["oracle"]["top100"]["100"]:flags.append("F_candidate_not_recoverable_top100_100m")
  if nearest["nearest_rank_top100"]>10:flags.append("E_candidate_available_but_below_top10")
  if distinctive:flags.append("A_or_B_distinctive_evidence_requires_better_visibility_or_recognition")
  if nearest_aggregate and nearest_aggregate["positive_evidence"]>0 and nearest["nearest_rank_top100"]>10:flags.append("C_or_E_supported_evidence_not_sufficiently_discriminative")
  nearest_associations=[r for r in plan["associations"] if r["query_id"]==qid and nearest_row and r["candidate_id"]==nearest_row["candidate_id"]]
  if any(r["classification"]=="spatially_ambiguous" for r in nearest_associations):flags.append("D_spatial_association_ambiguous")
  matrix.append({"query_id":qid,"claims":len(claims),"distinctive_claim_texts":[r["text_es"] for r in distinctive],"nearest_top100_rank":nearest["nearest_rank_top100"],"nearest_top100_distance_m":nearest["nearest_distance_top100_m"],"nearest_positive_evidence":nearest_aggregate["positive_evidence"] if nearest_aggregate else None,"nearest_negative_evidence":nearest_aggregate["negative_evidence"] if nearest_aggregate else None,"nearest_image_associations":len(nearest_associations),"nearest_spatial_classes":sorted({r["classification"] for r in nearest_associations}),"shared_image_max_frequency":max(shared_images.values(),default=0),"causal_flags":flags})
  # Commons targets derive only from Top-20 OSM named/Wikidata objects and distinctive query text.
  candidate_ids=[r["candidate_id"] for r in candidate_rows[:20]];targets={}
  for cid in candidate_ids:
   for obj in by_candidate.get(cid,[]):
    tags=obj.get("tags",{});name=tags.get("name") or tags.get("name:es") or tags.get("official_name");wikidata=tags.get("wikidata")
    if not name and not wikidata:continue
    name_match=bool(name and len(norm(name))>=4 and norm(name) in norm(observation["description"]["text_es"]))
    category_match=any(norm(str(tags.get(key,""))) in values for key,values in OSM_DISTINCTIVE.items()) and bool(distinctive)
    semantic_match=name_match or category_match
    if semantic_match:targets[(name,wikidata,obj["osm_ref"]) ]={"label":name,"wikidata_id":wikidata,"osm_ref":obj["osm_ref"],"candidate_ids":sorted({cid}|set(targets.get((name,wikidata,obj["osm_ref"]),{}).get("candidate_ids",[])))}
  prioritized=sorted(targets.values(),key=lambda target:(0 if target["label"] and norm(target["label"]) in norm(observation["description"]["text_es"]) else 1,0 if target["wikidata_id"] else 1,target["label"] or "",target["osm_ref"]))[:3]
  for target in prioritized:commons_queries.append({"query_id":qid,"target":target,"query_mode":"exact_name_or_distinctive_osm_category_metadata_only","location_kind_required":"object_or_camera_explicit","download_permitted":False})
  osm_needs.append({"query_id":qid,"distinctive_claims":[r["text_es"] for r in distinctive],"named_or_wikidata_targets":prioritized,"guidance_only":True,"visibility_inferred":False})
 matrix_doc={"schema_version":"1.0","contract_version":"h26-h37-evidence-diagnostic-matrix-v3","inputs":{"campaign_sha256":digest(a.campaign),"recoverability_sha256":digest(a.recoverability),"rankings_sha256":digest(a.rankings),"evaluation_sha256":digest(a.evaluation),"visual_plan_sha256":digest(a.visual_plan)},"protocol":{"development_only":True,"ground_truth_used_for_posthoc_diagnosis":True,"ground_truth_used_for_selection":False,"multi_label_causes_not_human_ground_truth":True},"rows":matrix}
 commons={"schema_version":"1.0","contract_version":"h26-h37-commons-metadata-query-plan-v1","status":"planned_no_network_not_authorized","inputs":{"diagnostic_matrix_sha256":hashlib.sha256(json.dumps(matrix_doc,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"osm_associations_sha256":digest(a.osm_associations),"osm_objects_sha256":digest(a.osm_objects)},"policy":{"candidate_scope":"ct2l_top20","selection_uses_gt":False,"wikidata_or_exact_name_required":True,"metadata_only":True,"maximum_api_queries":len(commons_queries),"maximum_records_per_target":10,"download_images":False,"separate_location_kind":True},"queries":commons_queries,"risks":["tourism_bias","object_not_camera_coordinates","historical_images","file_specific_licenses","semantic_selection_bias"]};commons["plan_id"]="h26-h37-commons-plan-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in commons.items() if k!="plan_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 osm_doc={"schema_version":"1.0","contract_version":"h26-h37-osm-acquisition-guide-v1","status":"guidance_only_not_ranking_score","inputs":{"osm_associations_sha256":digest(a.osm_associations),"osm_objects_sha256":digest(a.osm_objects)},"protocol":{"existence_not_visibility":True,"ground_truth_used":False,"candidate_scope":"ct2l_top20","purpose":"decide_which_distinctive_evidence_to_seek"},"queries":osm_needs}
 for path,doc in ((a.output_matrix,matrix_doc),(a.output_commons,commons),(a.output_osm_guide,osm_doc)):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
 print(json.dumps({"matrix_rows":len(matrix),"commons_targets":len(commons_queries),"commons_plan_id":commons["plan_id"],"osm_guides":len(osm_needs)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
