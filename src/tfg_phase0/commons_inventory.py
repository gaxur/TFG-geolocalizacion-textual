"""Cliente inyectable y freeze de inventario Commons metadata-only."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from typing import Callable,Mapping,Sequence
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from .commons_provider import normalize_commons_record,validate_commons_use

API="https://commons.wikimedia.org/w/api.php"
class CommonsInventoryError(ValueError):pass
def canonical_bytes(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def build_query(*,wikidata_id:str|None,label:str|None,limit:int=10)->str:
 if not wikidata_id and not label:raise CommonsInventoryError("target vacío")
 if not 1<=limit<=10:raise CommonsInventoryError("limit inválido")
 search=f"haswbstatement:P180={wikidata_id}" if wikidata_id else f'intitle:"{label}"';params={"action":"query","generator":"search","gsrsearch":search,"gsrnamespace":6,"gsrlimit":limit,"prop":"imageinfo|coordinates","iiprop":"url|size|mime|extmetadata","maxlag":5,"format":"json","formatversion":2};return API+"?"+urlencode(params)
def fetch_metadata(url:str,*,opener:Callable=urlopen)->Mapping:
 if not url.startswith(API+"?"):raise CommonsInventoryError("endpoint no autorizado")
 request=Request(url,headers={"User-Agent":"TFG-geolocalizacion-textual/commons-metadata-v1","Accept":"application/json"})
 with opener(request,timeout=30) as response:document=json.loads(response.read().decode())
 if not isinstance(document,dict):raise CommonsInventoryError("respuesta no objeto")
 return document
def freeze_inventory(plan:Mapping,responses:Mapping[str,Mapping],*,consulted_at_utc:str|None=None)->dict:
 consulted=consulted_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00","Z");records=[];coverage=[];inventory_seed={"plan_id":plan["plan_id"],"consulted_at_utc":consulted};inventory_id="commons-h26-h37-metadata-sha256-"+hashlib.sha256(canonical_bytes(inventory_seed)).hexdigest()
 for item in plan["queries"]:
  key=f"{item['query_id']}|{item['target'].get('wikidata_id') or item['target'].get('label')}";response=responses.get(key,{"query":{"pages":[]}});normalized=[]
  for raw in response.get("query",{}).get("pages",[]):
   enriched={**raw,"location_kind":"unknown","location_source":"commons_geolocation" if raw.get("coordinates") else "absent","camera_position_verified":False,"depicted_objects":[{"label":item["target"].get("label") or item["target"].get("wikidata_id"),"wikidata_id":item["target"].get("wikidata_id"),"source":"manual"}],"osm_links":[{"osm_ref":item["target"]["osm_ref"],"link_method":"wikidata_exact" if item["target"].get("wikidata_id") else "name_and_geometry","confidence":"high" if item["target"].get("wikidata_id") else "medium","review_status":"pending"}]}
   record=normalize_commons_record(enriched,consulted_at_utc=consulted,inventory_id=inventory_id);normalized.append(record);records.append({"query_id":item["query_id"],"target":item["target"],"record":record,"use_gate":validate_commons_use(record)})
  coverage.append({"query_id":item["query_id"],"target":item["target"],"records":len(normalized),"camera_records":sum(r["location"]["kind"]=="camera" for r in normalized),"object_records":sum(r["location"]["kind"]=="object" for r in normalized),"unknown_records":sum(r["location"]["kind"]=="unknown" for r in normalized)})
 document={"schema_version":"1.0","contract_version":"h26-h37-commons-metadata-inventory-v1","inventory_id":inventory_id,"plan_id":plan["plan_id"],"consulted_at_utc":consulted,"network_scope":"metadata_only_no_image_download","records":records,"coverage":coverage,"summary":{"targets":len(plan["queries"]),"records":len(records),"queries_with_records":len({r["query_id"] for r in records}),"eligible_camera":sum(r["use_gate"]["eligible_for_geometric_camera_association"] for r in records),"eligible_object_semantic":sum(r["use_gate"]["eligible_for_semantic_object_evidence"] for r in records)},"limitations":["metadata_search_bias","location_kind_requires_review","file_specific_license_gate","object_coordinate_not_camera"]};return document
