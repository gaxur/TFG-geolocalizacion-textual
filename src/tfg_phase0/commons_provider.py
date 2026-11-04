"""Normalización metadata-only de Commons; no realiza red ni descarga."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping

class CommonsMetadataError(ValueError):pass
def canonical_bytes(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def normalize_commons_record(raw:Mapping[str,Any],*,consulted_at_utc:str,inventory_id:str)->dict[str,Any]:
 title=raw.get("title");page_id=raw.get("pageid");info=raw.get("imageinfo",[{}])[0];ext=raw.get("extmetadata",info.get("extmetadata",{}));coordinates=raw.get("coordinates",[]);coordinate=coordinates[0] if coordinates else None;kind=raw.get("location_kind","unknown")
 if kind not in {"camera","object","unknown"}:raise CommonsMetadataError("location_kind inválido")
 if kind=="camera" and (coordinate is None or raw.get("camera_position_verified") is not True):raise CommonsMetadataError("coordenada de cámara no verificada")
 if not isinstance(title,str) or not title.startswith("File:") or not isinstance(page_id,int):raise CommonsMetadataError("identidad Commons inválida")
 value=lambda key:(ext.get(key) or {}).get("value") if isinstance(ext.get(key),dict) else ext.get(key)
 location={"kind":kind,"latitude":coordinate.get("lat") if coordinate else None,"longitude":coordinate.get("lon") if coordinate else None,"source":raw.get("location_source","commons_geolocation" if coordinate else "absent"),"uncertainty":"provider_reported" if coordinate else "not_applicable","camera_position_verified":raw.get("camera_position_verified") is True}
 record={"provider":"wikimedia_commons","file_title":title,"page_id":page_id,"canonical_url":info.get("url") or raw.get("canonical_url"),"description_url":info.get("descriptionurl") or raw.get("description_url"),"author":value("Artist"),"license_identifier":value("LicenseShortName"),"license_url":value("LicenseUrl"),"attribution":value("Attribution") or value("Credit"),"consulted_at_utc":consulted_at_utc,"location":location,"depicted_objects":raw.get("depicted_objects",[]),"osm_links":raw.get("osm_links",[]),"media":{"mime":info.get("mime"),"width_px":info.get("width"),"height_px":info.get("height"),"bytes":info.get("size"),"sha256":None,"local_path":None},"provenance":{"api_endpoint":"https://commons.wikimedia.org/w/api.php","api_revision":raw.get("api_revision"),"raw_record_sha256":hashlib.sha256(canonical_bytes(raw)).hexdigest(),"inventory_id":inventory_id}}
 if not record["canonical_url"] or not record["description_url"]:raise CommonsMetadataError("URLs Commons ausentes")
 return record
def validate_commons_use(record:Mapping[str,Any])->dict[str,Any]:
 blockers=[]
 if not record.get("license_identifier") or not record.get("license_url") or not record.get("author"):blockers.append("license_or_author_incomplete")
 if record["location"]["kind"]=="camera" and not record["location"]["camera_position_verified"]:blockers.append("camera_position_unverified")
 if record["location"]["kind"]=="object":blockers.append("object_coordinate_not_observer_position")
 if record["location"]["kind"]=="unknown":blockers.append("location_kind_unknown")
 if any(link["review_status"]!="accepted" or link["confidence"]!="high" for link in record.get("osm_links",[])):blockers.append("osm_link_not_high_confidence_accepted")
 return {"eligible_for_geometric_camera_association":not blockers and record["location"]["kind"]=="camera","eligible_for_semantic_object_evidence":not {"license_or_author_incomplete","location_kind_unknown","osm_link_not_high_confidence_accepted"}.intersection(blockers) and record["location"]["kind"]=="object","blockers":blockers}
