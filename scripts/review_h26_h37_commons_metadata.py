#!/usr/bin/env python3
"""Revisión determinista P180↔Wikidata OSM; nunca convierte objeto en cámara."""
from __future__ import annotations
import argparse,collections,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.commons_provider import validate_commons_use
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--inventory",type=Path,required=True);p.add_argument("--osm-objects",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();inventory=json.load(open(a.inventory));objects={r["osm_ref"]:r for r in map(json.loads,a.osm_objects.read_text().splitlines())};rows=[]
 for item in inventory["records"]:
  record=json.loads(json.dumps(item["record"]));target=item["target"];obj=objects.get(target["osm_ref"]);osm_wikidata=(obj or {}).get("tags",{}).get("wikidata");exact=bool(target.get("wikidata_id") and target["wikidata_id"]==osm_wikidata)
  # P180 identifica el objeto representado; cualquier coordenada sigue siendo semántica, no cámara.
  if exact:
   record["location"]={**record["location"],"kind":"object","camera_position_verified":False,"uncertainty":"unknown" if record["location"]["latitude"] is not None else "not_applicable"}
   for link in record["osm_links"]:
    if link["osm_ref"]==target["osm_ref"]:link.update({"link_method":"wikidata_exact","confidence":"high","review_status":"accepted"})
  gate=validate_commons_use(record);rows.append({**item,"record":record,"use_gate":gate,"metadata_review":{"kind":"deterministic_p180_osm_wikidata_exact_v1","osm_wikidata":osm_wikidata,"target_wikidata":target.get("wikidata_id"),"exact":exact,"human_visual_review":False}})
 unique={r["record"]["page_id"]:r for r in rows};coverage=collections.Counter(r["query_id"] for r in rows if r["use_gate"]["eligible_for_semantic_object_evidence"]);document={**inventory,"contract_version":"h26-h37-commons-metadata-reviewed-v1","source_inventory_sha256":digest(a.inventory),"records":rows,"summary":{**inventory["summary"],"eligible_object_semantic":sum(r["use_gate"]["eligible_for_semantic_object_evidence"] for r in rows),"eligible_unique_pages":len({r["record"]["page_id"] for r in rows if r["use_gate"]["eligible_for_semantic_object_evidence"]}),"queries_with_eligible_object_records":len(coverage),"eligible_by_query":dict(coverage),"eligible_camera":0},"protocol":{"object_coordinates_never_used_as_camera":True,"pixels_reviewed":False,"licenses_checked_from_metadata_only":True,"deterministic_not_human_review":True}};a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps(document["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
