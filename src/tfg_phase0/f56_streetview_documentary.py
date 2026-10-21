"""Dataset documental F5.6 de capturas locales y referencias Google Street View."""

from __future__ import annotations

from collections import Counter
import hashlib
from html import escape
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .f4_evaluation import assign_reference


PREFIX = "f56-streetview-documentary-sha256-"
PANORAMA_RE = re.compile(r"^[A-Za-z0-9_-]+$")
COORDINATE_RE = re.compile(r"(?<!\w)[+-]?\d{1,3}[.,]\d+")


class StreetViewDocumentaryError(ValueError):
    pass


def dataset_id(document: Mapping[str, Any]) -> str:
    identity={key:document[key] for key in ("contract_version","protocol","inputs","observations","excluded_observations","limitations")}
    return PREFIX+hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def build_dataset(spec: Mapping[str, Any], *, image_root: Path, catalogs: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("contract_version")!="f56-streetview-input-v1" or not isinstance(spec.get("observations"),list) or not isinstance(spec.get("excluded_observations"),list) or spec.get("review_policy")!={"visual_correspondence":"pending_human_review","egocentric_heading_check":"pending_human_review","text_frozen_before_model_outputs":True,"coordinates_and_panorama_ids_forbidden_in_text":True}: raise StreetViewDocumentaryError("especificación Street View incompatible")
    rows=[]; ids=set(); hashes=set()
    for source in spec["observations"]:
        observation_id=source.get("observation_id")
        if not isinstance(observation_id,str) or observation_id in ids: raise StreetViewDocumentaryError("observation_id duplicado o inválido")
        ids.add(observation_id); relative=PurePosixPath(source.get("image_path", ""))
        if relative.is_absolute() or any(part in {"",".",".."} for part in relative.parts): raise StreetViewDocumentaryError("ruta de imagen no válida")
        image=image_root/Path(*relative.parts)
        if not image.is_file(): raise StreetViewDocumentaryError(f"captura local ausente: {relative}")
        raw=image.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
        if digest in hashes: raise StreetViewDocumentaryError("capturas duplicadas por SHA-256")
        hashes.add(digest); width,height=png_dimensions(raw)
        latitude,longitude=source["link_coordinate"]["latitude"],source["link_coordinate"]["longitude"]
        if not _coordinate(latitude,longitude): raise StreetViewDocumentaryError("coordenada de enlace inválida")
        panorama=source.get("panorama_id"); heading=source.get("heading_degrees"); pitch=source.get("pitch_degrees")
        if not isinstance(panorama,str) or not PANORAMA_RE.fullmatch(panorama) or not _finite_range(heading,0,360,upper_exclusive=True) or not _finite_range(pitch,-90,90): raise StreetViewDocumentaryError("panorama, heading o pitch inválido")
        description=source.get("original_spanish_description")
        if not isinstance(description,str) or len(description)<80 or COORDINATE_RE.search(description) or panorama in description: raise StreetViewDocumentaryError("descripción insuficiente o con fuga")
        assignments={gallery:assign_reference(latitude,longitude,catalog) for gallery,catalog in sorted(catalogs.items())}
        inside=all(value["status"]!="outside_region" for value in assignments.values())
        visible=source.get("visible_evidence")
        if not isinstance(visible,list) or len(visible)<3 or any(not isinstance(value,str) or not value.strip() for value in visible): raise StreetViewDocumentaryError("evidencia visual declarada insuficiente")
        rows.append({"observation_id":observation_id,"source_type":"streetview_documentary","image":{"logical_path":relative.as_posix(),"sha256":digest,"size_bytes":len(raw),"media_type":"image/png","width":width,"height":height,"git_tracking_forbidden":True},"provenance":{"provider":"Google Street View","panorama_id":panorama,"external_url":source["external_url"],"capture_file_origin":"manual_screenshot_supplied_by_tfg_owner","terms_status":"not_open_license_do_not_redistribute"},"link_coordinate":{"latitude":latitude,"longitude":longitude,"crs":"EPSG:4326","meaning":"coordinate_embedded_in_supplied_google_maps_url","positional_uncertainty":"unknown","camera_position_independently_verified":False},"view":{"heading_degrees":heading,"heading_convention":"clockwise_from_north_as_declared_by_url","pitch_degrees":pitch,"body_orientation_inferred":False},"description":{"text":description,"language":"es","frozen_before_variants":True,"contains_coordinates":False,"contains_internal_ids":False,"formal_review_status":"pending"},"visible_evidence":list(visible),"description_review":{"status":"pending","reviewer":None,"reviewed_at_utc":None,"image_correspondence_verified":False,"egocentric_relations_verified_against_heading":False,"unobservable_claims_absent":False,"notes":source.get("review_notes")},"geography":{"inside_d004_by_link_coordinate":inside,"link_point_assignments":assignments,"exact_recall_eligible":False,"official_geographic_accuracy_eligible":False,"exploratory_haversine_eligible":inside,"exploratory_reference_label":"approximate_link_coordinate_unknown_uncertainty","exclusion_reason":"outside_d004" if not inside else "unknown_positional_uncertainty"},"status":"pending"})
    document={"schema_version":"1.0","contract_version":"f56-streetview-documentary-v1","dataset_id":PREFIX+"0"*64,"protocol":{"version":"f56-streetview-documentary-v2","real_ground_truth":False,"source_kind":"manual_google_streetview_screenshot","images_local_only":True,"coordinates_are_link_references":True,"unknown_accuracy_disables_exact_recall":True,"outside_region_not_forced_into_gallery":True,"no_automatic_description_approval":True,"no_model_execution":True},"inputs":{"image_root_logical":"data/streetview","catalogs":{gallery:{"manifest_id":catalog.manifest_id,"sha256":catalog.sha256,"cell_size_m":catalog.cell_size_m} for gallery,catalog in sorted(catalogs.items())}},"observations":rows,"excluded_observations":list(spec["excluded_observations"]),"limitations":["google_streetview_not_open_license","manual_screenshots_not_for_redistribution","link_coordinate_not_independently_verified_camera_position","positional_uncertainty_unknown","no_official_recall_or_accuracy","four_case_exploratory_documentary_sample"]}
    document["dataset_id"]=dataset_id(document); validate_dataset(document,catalogs=catalogs,image_root=image_root); return document


def validate_dataset(document:Mapping[str,Any],*,catalogs:Mapping[str,Any],image_root:Path|None=None)->dict[str,Any]:
    if document.get("dataset_id")!=dataset_id(document) or document.get("protocol",{}).get("real_ground_truth") is not False: raise StreetViewDocumentaryError("identidad o clasificación documental inválida")
    counts=Counter(); ids=set(); hashes=set()
    for row in document["observations"]:
        if row["observation_id"] in ids or row["image"]["sha256"] in hashes: raise StreetViewDocumentaryError("duplicado documental")
        ids.add(row["observation_id"]); hashes.add(row["image"]["sha256"]); counts[row["status"]]+=1
        if row["source_type"]!="streetview_documentary" or row["geography"]["exact_recall_eligible"] or row["geography"]["official_geographic_accuracy_eligible"]: raise StreetViewDocumentaryError("registro documental se presenta como GT oficial")
        latitude,longitude=row["link_coordinate"]["latitude"],row["link_coordinate"]["longitude"]
        for gallery,catalog in catalogs.items():
            if row["geography"]["link_point_assignments"][gallery]!=assign_reference(latitude,longitude,catalog): raise StreetViewDocumentaryError("asignación documental inconsistente")
        if image_root is not None:
            path=image_root/row["image"]["logical_path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row["image"]["sha256"]: raise StreetViewDocumentaryError("captura local ausente o modificada")
        if row["description_review"]["status"]=="pending" and (row["description_review"]["reviewer"] is not None or row["description"]["formal_review_status"]!="pending"): raise StreetViewDocumentaryError("revisión pendiente contiene aprobación")
    return {"observations":len(ids),"inside_d004":sum(row["geography"]["inside_d004_by_link_coordinate"] for row in document["observations"]),"outside_d004":sum(not row["geography"]["inside_d004_by_link_coordinate"] for row in document["observations"]),"exact_recall_eligible":0,"status_counts":dict(sorted(counts.items()))}


def exploratory_reference_adapter(document:Mapping[str,Any])->dict[str,Any]:
    return {"schema_version":"1.0","contract_version":"f56-exploratory-reference-v1","dataset_id":document["dataset_id"],"reference_kind":"approximate_link_coordinate","real_ground_truth":False,"official_metrics_allowed":False,"observations":[{"source_query_id":row["observation_id"],"latitude":row["link_coordinate"]["latitude"],"longitude":row["link_coordinate"]["longitude"],"uncertainty":"unknown","inside_d004":row["geography"]["inside_d004_by_link_coordinate"],"assignments":row["geography"]["link_point_assignments"],"exact_recall_eligible":False,"exploratory_haversine_eligible":row["geography"]["exploratory_haversine_eligible"]} for row in document["observations"]],"limitations":["do_not_report_as_official_accuracy","no_exact_recall","unknown_uncertainty"]}


def execution_gate(document:Mapping[str,Any])->dict[str,Any]:
    pending=sum(row["description"]["formal_review_status"]!="reviewed" for row in document["observations"])
    exact=sum(row["geography"]["exact_recall_eligible"] for row in document["observations"])
    inside=sum(row["geography"]["inside_d004_by_link_coordinate"] for row in document["observations"])
    blockers=[]
    if pending: blockers.append("descriptions_require_formal_human_review")
    if exact==0: blockers.append("no_validated_exact_cell_ground_truth")
    if inside<len(document["observations"]): blockers.append("observations_outside_d004")
    return {"schema_version":"1.0","contract_version":"f56-execution-gate-v1","dataset_id":document["dataset_id"],"ready_for_variant_generation":pending==0,"ready_for_exploratory_rankings":pending==0 and inside>0,"ready_for_official_geographic_evaluation":pending==0 and exact>0,"counts":{"observations":len(document["observations"]),"inside_d004":inside,"pending_description_review":pending,"exact_recall_eligible":exact,"variants_generated":0,"variants_approved":0,"rankings_generated":0},"blockers":blockers,"required_next_action":"formal_review_of_descriptions_and_egocentric_relations"}


def render_review_html(document:Mapping[str,Any],output:Path,*,image_prefix:str=".")->None:
    cards=[]
    for row in document["observations"]:
        image=escape((PurePosixPath(image_prefix)/row["image"]["logical_path"]).as_posix()); evidence="".join(f"<li>{escape(value)}</li>" for value in row["visible_evidence"]); assignments="".join(f"<li>{escape(gallery)}: <code>{escape(value['status'])}</code></li>" for gallery,value in sorted(row["geography"]["link_point_assignments"].items()))
        cards.append(f'<article><h2>{escape(row["observation_id"])}</h2><img src="{image}" alt="{escape(row["observation_id"])}"><blockquote>{escape(row["description"]["text"])}</blockquote><ul>{evidence}</ul><p>Heading: {row["view"]["heading_degrees"]}°; pitch: {row["view"]["pitch_degrees"]}°</p><ul>{assignments}</ul><p>D004: {row["geography"]["inside_d004_by_link_coordinate"]}; Recall exacto: no; revisión: pending.</p><p><a href="{escape(row["provenance"]["external_url"])}">Referencia externa</a></p></article>')
    html='<!doctype html><html lang="es"><head><meta charset="utf-8"><title>F5.6 Street View documental</title><style>body{font:16px system-ui;max-width:1100px;margin:auto;padding:2rem;background:#eef0f3}article{background:white;padding:1rem;margin:1rem 0;border-left:5px solid #345995}img{max-width:100%;height:auto}code{overflow-wrap:anywhere}</style></head><body><h1>Street View documental F5.6</h1><p>Capturas locales no redistribuibles. Coordenadas de enlace con incertidumbre desconocida; ninguna observación valida Recall exacto.</p>'+"".join(cards)+'</body></html>'; output.parent.mkdir(parents=True,exist_ok=True); output.write_text(html,encoding="utf-8")


def png_dimensions(raw:bytes)->tuple[int,int]:
    if len(raw)<24 or raw[:8]!=b"\x89PNG\r\n\x1a\n" or raw[12:16]!=b"IHDR": raise StreetViewDocumentaryError("archivo no es PNG válido")
    return int.from_bytes(raw[16:20],"big"),int.from_bytes(raw[20:24],"big")
def _coordinate(lat:Any,lon:Any)->bool: return isinstance(lat,(int,float)) and not isinstance(lat,bool) and isinstance(lon,(int,float)) and not isinstance(lon,bool) and math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180
def _finite_range(value:Any,lower:float,upper:float,upper_exclusive:bool=False)->bool: return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and lower<=value and (value<upper if upper_exclusive else value<=upper)
def _canonical_bytes(value:Any)->bytes: return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
