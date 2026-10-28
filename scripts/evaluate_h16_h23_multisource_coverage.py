#!/usr/bin/env python3
"""Cobertura metadata-only Mapillary/Panoramax; KartaView/Commons no medibles."""

from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830
from src.tfg_phase0.image_providers import MapillaryMetadataProvider,PanoramaxMetadataProvider

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,required=True);p.add_argument("--mapillary",type=Path,required=True);p.add_argument("--panoramax",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();fixture=json.loads(a.fixture.read_text());inventories={"mapillary":MapillaryMetadataProvider().normalize_inventory(json.loads(a.mapillary.read_text())),"panoramax":PanoramaxMetadataProvider().normalize_inventory(json.loads(a.panoramax.read_text()))};slots=[]
 for query in fixture["queries"]:
  for candidate in query["baseline_results"]:
   cx,cy=wgs84_to_epsg25830(candidate["latitude"],candidate["longitude"]);providers={}
   for provider,images in inventories.items():
    nearby=[]
    for image in images:
     ix,iy=wgs84_to_epsg25830(image.latitude,image.longitude);distance=math.hypot(cx-ix,cy-iy)
     if distance<=100:nearby.append({"global_record_id":image.global_record_id,"distance_m":distance,"sequence_or_collection":image.collection_or_sequence_id,"heading_available":image.heading_degrees is not None,"captured_at":image.captured_at_utc,"license":image.license_identifier,"location_kind":image.location_kind})
    nearby.sort(key=lambda row:(row["distance_m"],row["global_record_id"]));providers[provider]={"count_100m":len(nearby),"minimum_distance_m":nearby[0]["distance_m"] if nearby else None,"independent_sequences_or_collections":len({row["sequence_or_collection"] or row["global_record_id"] for row in nearby}),"heading_available":sum(row["heading_available"] for row in nearby),"records":nearby}
   slots.append({"query_id":query["query_id"],"rank":candidate["rank"],"candidate_id":candidate["candidate_id"],"providers":providers})
 summary={}
 for provider in inventories:
  summary[provider]={"inventory_records":len(inventories[provider]),"covered_slots_100m":sum(row["providers"][provider]["count_100m"]>0 for row in slots),"covered_unique_candidates_100m":len({row["candidate_id"] for row in slots if row["providers"][provider]["count_100m"]>0})}
 union={row["candidate_id"] for row in slots if any(row["providers"][provider]["count_100m"]>0 for provider in inventories)}
 doc={"schema_version":"1.0","contract_version":"h16-h23-multisource-metadata-coverage-v1","inputs":{"fixture_sha256":sha(a.fixture),"mapillary_inventory_sha256":sha(a.mapillary),"panoramax_inventory_sha256":sha(a.panoramax)},"protocol":{"ground_truth_used":False,"distance_crs":"EPSG:25830","radius_m":100,"candidate_source":"CT2L frozen ranking","metadata_only":True,"visibility_inferred":False},"provider_status":{"mapillary":"inventory_frozen_buffer100m","panoramax":"historical_inventory_d004_strict","kartaview":"unavailable_not_frozen","wikimedia_commons":"unavailable_not_frozen"},"summary":summary,"union_covered_unique_candidates_100m":len(union),"slots":slots,"limitations":["panoramax_bbox_d004_strict_not_buffer100m","kartaview_not_measurable_from_repository","commons_not_measurable_from_repository","metadata_proximity_not_visibility","cross_provider_pixel_duplicates_unknown"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({"summary":summary,"union":len(union)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
