#!/usr/bin/env python3
"""Audita F3 y congela rankings structured-OSM H26-H37 sin aceptar GT."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.structured_osm_reranking import build_structured_evidence,build_variants,index_f3

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load_jsonl(path):return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def main():
 p=argparse.ArgumentParser();p.add_argument("--ct2l",type=Path,required=True);p.add_argument("--atlas-rankings",type=Path,required=True);p.add_argument("--historical-osm-rankings",type=Path,required=True);p.add_argument("--associations",type=Path,required=True);p.add_argument("--objects",type=Path,required=True);p.add_argument("--audit-output",type=Path,required=True);p.add_argument("--matrix-output",type=Path,required=True);p.add_argument("--rankings-output",type=Path,required=True);a=p.parse_args()
 ct2l=json.loads(a.ct2l.read_text());atlas=json.loads(a.atlas_rankings.read_text());historical=json.loads(a.historical_osm_rankings.read_text());objects={row["osm_ref"]:row for row in load_jsonl(a.objects)};associations=load_jsonl(a.associations);by_candidate=index_f3(associations)
 if ct2l["inputs"]["ground_truth_used"] or ct2l["inputs"]["coordinates_used_for_retrieval"]:raise ValueError("CT2L incompatible: usa GT")
 if len(ct2l["queries"])!=len(ct2l["rankings"]):raise ValueError("consultas y rankings CT2L no están alineados")
 query_text={row["query_id"]:row["text"] for row in ct2l["queries"]};ranking_by={query["query_id"]:ranking for query,ranking in zip(ct2l["queries"],ct2l["rankings"],strict=True)};queries={};matrix=[]
 for qid in sorted(query_text):
  baseline=ranking_by[qid]["results"][:100];ids=[row["candidate_id"] for row in baseline];evidence=build_structured_evidence(text=query_text[qid],candidate_ids=ids,associations_by_candidate=by_candidate,objects=objects);variants,audit=build_variants(ids,evidence)
  variants={"baseline":ids,"atlas_v3":atlas["queries"][qid]["variants"]["top100_original_beta_0.1"],"historical_osm_gamma_0.35":historical["queries"][qid]["variants"]["osm_gamma_0.35"],**variants}
  queries[qid]={"baseline_results":baseline,"variants":variants,"promotion_audit":audit,"structured_evidence":evidence}
  matrix.append({"query_id":qid,"textual_evidence":evidence["textual_evidence"],"summary":evidence["summary"],"top_structured_candidates":[{key:row[key] for key in ("candidate_id","original_rank","score","evidence_level","matched_specific_categories","matches")} for row in evidence["candidate_evidence"][:10]],"promotion":audit})
 audit_doc={"schema_version":"1.0","contract_version":"h26-h37-osm-f3-signal-audit-v4","protocol":{"ground_truth_used":False,"candidate_scope":"ct2l_top100","f3_association_semantics":"osm_geometry_intersects_50m_candidate_cell","absence_is_not_contradiction":True,"cartographic_proximity_is_not_visibility":True},"inputs":{"ct2l_sha256":digest(a.ct2l),"associations_sha256":digest(a.associations),"objects_sha256":digest(a.objects)},"inventory":{"objects":len(objects),"associations":len(associations),"candidates_with_associations":len(by_candidate),"named_objects":sum(bool(row.get("tags",{}).get("name")) for row in objects.values()),"wikidata_objects":sum(bool(row.get("tags",{}).get("wikidata")) for row in objects.values()),"geometry_roles":dict(sorted(__import__("collections").Counter(row.get("geometry_role") for row in objects.values()).items()))},"generation":{"association_predicate":"intersects","distance":"candidate_cell_center_to_full_osm_geometry_epsg25830","relation_geometry_available":False,"serialized_object_geometry_available":False}}
 matrix_doc={"schema_version":"1.0","contract_version":"h26-h37-structured-osm-evidence-matrix-v4","protocol":{"ground_truth_used":False,"deterministic_rules":True,"orientation_relations_scored":False,"generic_categories_strong":False},"rows":matrix}
 ranking_doc={"schema_version":"1.0","contract_version":"h26-h37-structured-osm-rankings-v4","ranking_set_id":"","status":"exploratory_development_frozen_before_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"candidate_scope":"same_ct2l_top100","rrf_k":60,"maximum_promotions_per_query":1,"absence_is_not_contradiction":True,"orientation_relations_scored":False,"fallback":"exact_ct2l_order_on_insufficient_evidence","variants":["baseline","atlas_v3","historical_osm_gamma_0.35","structured_osm","rrf_k60","conditional_top5","conditional_strong_top1"]},"inputs":{"ct2l_sha256":digest(a.ct2l),"atlas_rankings_sha256":digest(a.atlas_rankings),"historical_osm_rankings_sha256":digest(a.historical_osm_rankings),"associations_sha256":digest(a.associations),"objects_sha256":digest(a.objects)},"queries":queries};ranking_doc["ranking_set_id"]="h26-h37-structured-osm-v4-sha256-"+hashlib.sha256(canonical({k:v for k,v in ranking_doc.items() if k!="ranking_set_id"})).hexdigest()
 for path,document in ((a.audit_output,audit_doc),(a.matrix_output,matrix_doc),(a.rankings_output,ranking_doc)):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"ranking_set_id":ranking_doc["ranking_set_id"],"queries":len(queries),"abstentions":sum(row["summary"]["abstain"] for row in matrix)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
