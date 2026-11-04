#!/usr/bin/env python3
"""Selecciona piloto Commons pequeño por metadata, sin GT ni descarga."""
from __future__ import annotations
import argparse,collections,hashlib,json
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--inventory",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();inventory=json.load(open(a.inventory));eligible=[r for r in inventory["records"] if r["use_gate"]["eligible_for_semantic_object_evidence"]];by_query=collections.defaultdict(list)
 for row in eligible:by_query[row["query_id"]].append(row)
 selected=[];seen_pages=set()
 for qid in sorted(by_query):
  candidates=sorted(by_query[qid],key=lambda r:(0 if r["target"].get("wikidata_id") else 1,-(r["record"]["media"].get("width_px") or 0)*(r["record"]["media"].get("height_px") or 0),r["record"]["page_id"]))
  for row in candidates:
   page=row["record"]["page_id"]
   if page in seen_pages:continue
   seen_pages.add(page);selected.append({"query_id":qid,"page_id":page,"file_title":row["record"]["file_title"],"canonical_url":row["record"]["canonical_url"],"description_url":row["record"]["description_url"],"author":row["record"]["author"],"license_identifier":row["record"]["license_identifier"],"license_url":row["record"]["license_url"],"attribution":row["record"]["attribution"],"target":row["target"],"location_kind":"object","role":"semantic_object_evidence_only","download_status":"not_authorized"})
   if sum(r["query_id"]==qid for r in selected)==2:break
 document={"schema_version":"1.0","contract_version":"h26-h37-commons-semantic-pilot-plan-v1","plan_id":"","status":"planned_not_authorized","inputs":{"inventory_sha256":digest(a.inventory)},"policy":{"maximum_images_per_query":2,"selection":"exact_wikidata_then_resolution","ground_truth_used":False,"coordinates_used_for_candidate_selection":False,"object_coordinates_used_as_camera":False,"candidate_scope":"ct2l_top20_targets","download_permitted":False},"assets":selected,"summary":{"queries":len({r["query_id"] for r in selected}),"assets":len(selected),"maximum_downloads":len(selected),"hard_maximum_bytes":len(selected)*8_000_000,"estimated_vlm_calls":len(selected)*2},"limitations":["semantic_object_views_not_street_views","tourism_bias","historical_or_interior_views_possible","requires_pixel_review_and_file_license_recheck"]};document["plan_id"]="h26-h37-commons-semantic-pilot-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="plan_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"plan_id":document["plan_id"],"summary":document["summary"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
