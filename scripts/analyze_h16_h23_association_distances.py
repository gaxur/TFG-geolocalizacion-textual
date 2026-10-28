#!/usr/bin/env python3
"""Analiza post hoc distancias de asociaciones históricas, sin cambiar selección."""

from __future__ import annotations
import argparse,collections,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crs import wgs84_to_epsg25830

BANDS=((0,25,"0-25"),(25,50,"25-50"),(50,100,"50-100"),(100,150,"100-150"),(150,float("inf"),">150"))
def band(distance):
 for low,high,name in BANDS:
  if low<=distance<high or name=="50-100" and distance==100:return name
 raise ValueError(distance)
def main():
 p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,required=True);p.add_argument("--assets",type=Path,required=True);p.add_argument("--inventory",type=Path,required=True);p.add_argument("--catalog",type=Path,required=True);p.add_argument("--f3-associations",type=Path,required=True);p.add_argument("--run-2b",type=Path,required=True);p.add_argument("--run-8b",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();fixture=json.loads(a.fixture.read_text());assets=json.loads(a.assets.read_text());inventory=json.loads(a.inventory.read_text());catalog=json.loads(a.catalog.read_text());runs={"2b":json.loads(a.run_2b.read_text()),"8b":json.loads(a.run_8b.read_text())};images={r["image_id"]:r for r in inventory["images"]};candidates={r["candidate_id"]:r for r in catalog["candidates"]};f3=collections.defaultdict(list)
 for line in a.f3_associations.read_text().splitlines():
  row=json.loads(line);f3[row["candidate_id"]].append(row["center_distance_m"])
 claim_specificity={c["claim_id"]:c["specificity"] for q in fixture["queries"] for c in q["claims"]["claims"]};associations=[]
 for row in assets["associations"]:
  image=images[row["image_id"]];candidate=candidates[row["candidate_id"]];ix,iy=wgs84_to_epsg25830(image["latitude"],image["longitude"]);cx,cy=candidate["generation"]["center_easting_m"],candidate["generation"]["center_northing_m"];center=math.hypot(ix-cx,iy-cy);dx=max(abs(ix-cx)-25,0);dy=max(abs(iy-cy)-25,0);edge=math.hypot(dx,dy);associations.append({**row,"camera_center_distance_epsg25830_m":center,"camera_cell_surface_distance_epsg25830_m":edge,"camera_inside_cell":edge==0,"band":band(center),"camera_heading_available":image.get("orientation_degrees") is not None,"sequence_id":image.get("sequence_id"),"minimum_candidate_center_to_intersecting_osm_geometry_m":min(f3[row["candidate_id"]]) if f3[row["candidate_id"]] else None,"osm_distance_semantics":"candidate_center_to_F3_intersecting_geometry_not_camera_to_visible_object"})
 association_key={(r["query_id"],r["candidate_id"],r["image_id"]):r for r in associations};bands={name:{"physical_image_ids":set(),"associations":0,"candidate_ids":set(),"sequence_ids":set(),"inside_cell_associations":0,"jobs":{m:collections.Counter() for m in runs},"supported_generic":{m:0 for m in runs},"supported_distinctive":{m:0 for m in runs}} for *_,name in BANDS}
 for row in associations:
  value=bands[row["band"]];value["physical_image_ids"].add(row["image_id"]);value["associations"]+=1;value["candidate_ids"].add(row["candidate_id"]);value["sequence_ids"].add(row.get("sequence_id") or f"image:{row['image_id']}");value["inside_cell_associations"]+=row["camera_inside_cell"]
 for model,run in runs.items():
  for record in run["records"]:
   row=association_key[(record["query_id"],record["candidate_id"],record["image_id"])];value=bands[row["band"]];value["jobs"][model]["total"]+=1;value["jobs"][model][record["verdict"]]+=1;value["jobs"][model][record["status"]]+=1
   if record["verdict"]=="supported":value["supported_generic" if claim_specificity[record["claim_id"]]=="generic" else "supported_distinctive"][model]+=1
 output={}
 for name,value in bands.items():output[name]={"physical_images":len(value["physical_image_ids"]),"associations":value["associations"],"candidates":len(value["candidate_ids"]),"sequences":len(value["sequence_ids"]),"inside_cell_associations":value["inside_cell_associations"],"jobs":{m:dict(c) for m,c in value["jobs"].items()},"supported_generic":value["supported_generic"],"supported_distinctive":value["supported_distinctive"]}
 doc={"schema_version":"1.0","contract_version":"h16-h23-v2-association-distance-analysis-v1","inputs":{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (a.fixture,a.assets,a.inventory,a.catalog,a.f3_associations,a.run_2b,a.run_8b)},"protocol":{"analysis_only":True,"selection_unchanged":True,"distance_crs":"EPSG:25830","cell_size_m":50,"cell_half_extent_m":25,"bands_m":[name for *_,name in BANDS]},"summary":{"physical_images":len({r['image_id'] for r in associations}),"associations":len(associations),"center_distance_min_m":min(r['camera_center_distance_epsg25830_m'] for r in associations),"center_distance_max_m":max(r['camera_center_distance_epsg25830_m'] for r in associations),"inside_cell_associations":sum(r['camera_inside_cell'] for r in associations)},"bands":output,"associations_detail":associations,"limitations":["distance_band_not_causal","F3_distance_is_not_camera_object_distance","FOV_not_available","visible_object_may_belong_to_neighbor_cell"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"summary":doc["summary"],"bands":output},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
