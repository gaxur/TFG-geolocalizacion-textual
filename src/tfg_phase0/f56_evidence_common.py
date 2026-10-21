"""Evidencia genérica y observaciones propias, independiente del proveedor visual."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .f4_evaluation import assign_reference, query_dataset_id
from .f5_ground_truth_evaluation import ground_truth_dataset_id


class EvidenceValidationError(ValueError): pass


def validate_field_record(record:Mapping[str,Any])->None:
    if record.get("contract_version")!="f55-field-observation-v1" or record.get("review",{}).get("status") not in {"pending","approved","rejected"}: raise EvidenceValidationError("registro de campo incompatible")
    evidence=record.get("evidence")
    if not isinstance(evidence,list): raise EvidenceValidationError("evidence debe ser lista")
    for row in evidence:
        path=PurePosixPath(row.get("logical_path",""))
        if path.is_absolute() or any(part in {"",".",".."} for part in path.parts) or not _sha(row.get("sha256")): raise EvidenceValidationError("evidencia no verificable")
    if record["review"]["status"]!="approved": return
    required=(record.get("observer_position"),record.get("captured_at_utc"),record.get("device"),record.get("original_spanish_description"),record["review"].get("reviewer"),record["review"].get("reviewed_at_utc"),record["review"].get("validation_method"))
    if any(value is None or value=="" for value in required) or not record.get("gnss_readings") or not evidence: raise EvidenceValidationError("registro aprobado incompleto")
    position=record["observer_position"]
    if position.get("source")!="measured_observer_position" or position.get("horizontal_accuracy_m") is None or not _coordinate(position.get("latitude"),position.get("longitude")) or position.get("crs")!="EPSG:4326": raise EvidenceValidationError("posición no medida")
    if not str(record["captured_at_utc"]).endswith("Z") or not record.get("consent_or_data_policy"): raise EvidenceValidationError("fecha UTC o política ausente")
    evidence_ids={row.get("evidence_id") for row in evidence}
    if None in evidence_ids or len(evidence_ids)!=len(evidence): raise EvidenceValidationError("evidence_id inválido")
    for reading in record["gnss_readings"]:
        if not isinstance(reading,Mapping) or not _coordinate(reading.get("latitude"),reading.get("longitude")) or not isinstance(reading.get("horizontal_accuracy_m"),(int,float)) or reading["horizontal_accuracy_m"]<0 or not str(reading.get("captured_at_utc","")).endswith("Z"): raise EvidenceValidationError("lectura GNSS inválida")
    if not set(record.get("orientation",{}).get("evidence_ids",[]))<=evidence_ids: raise EvidenceValidationError("orientación sin evidencia")


def import_approved_field_records(records:Sequence[Mapping[str,Any]],*,evidence_root:Path,catalogs:Mapping[str,Any],dataset_version:str="madrid-field-observations-v1"):
    approved=[]; counts=Counter(); seen=set()
    for record in records:
        validate_field_record(record); status=record["review"]["status"]; counts[status]+=1
        if status!="approved": continue
        if record["record_id"] in seen: raise EvidenceValidationError("record_id duplicado")
        seen.add(record["record_id"]); _verify(record["evidence"],evidence_root); approved.append(record)
    queries=[]; observations=[]
    for record in approved:
        p=record["observer_position"]; assignments={gallery:assign_reference(p["latitude"],p["longitude"],catalog,reported_accuracy_m=p["horizontal_accuracy_m"]) for gallery,catalog in catalogs.items()}; qid=record["record_id"]
        query={"query_id":qid,"location_id":record["location_id"],"derivation_group_id":record["derivation_group_id"],"partition":record["partition"],"description":{"text":record["original_spanish_description"],"language":"es","contains_coordinates":False},"provenance":{"source_type":"human_in_situ","description":"Observación redactada in situ antes de rankings.","independent_environment_observation":True,"instructions_version":"field-observation-v1","collected_at_utc":record["captured_at_utc"]},"reference":{"status":"validated","latitude":p["latitude"],"longitude":p["longitude"],"crs":"EPSG:4326","capture_method":f"multi_reading_gnss:{record['device']}","reported_accuracy_m":p["horizontal_accuracy_m"],"validation_method":record["review"]["validation_method"],"catalog_assignment":assignments["madrid-50m"]},"ambiguity":{"status":"not_ambiguous","notes":record["review"].get("notes")},"validation_status":"validated"}
        queries.append(query); observations.append(_observation(query,record,assignments))
    source=_query_dataset(queries,catalogs["madrid-50m"],dataset_version); gt=_gt_dataset(observations,source,catalogs,dataset_version)
    return source,gt,{key:counts[key] for key in ("pending","approved","rejected")}


def _query_dataset(queries,catalog,version):
    d={"schema_version":"1.0","contract_version":"f4-query-dataset-v1","dataset_id":"","dataset_version":version,"region":{"region_id":catalog.region_id,"bbox_wgs84":dict(catalog.region_bbox_wgs84)},"catalog":{"manifest_id":catalog.manifest_id,"manifest_sha256":catalog.sha256,"candidate_count":len(catalog.candidates),"assignment_policy":"projected_cell_interior_boundary_ambiguous_v1"},"partition_policy":{"version":"location-and-derivation-group-v1","group_by":["location_id","derivation_group_id"],"evaluation_frozen":False,"evaluation_use_restriction":"no_parameter_prompt_checkpoint_or_pipeline_selection","near_duplicate_token_jaccard_threshold":.8},"queries":queries}; d["dataset_id"]=query_dataset_id(d); return d
def _gt_dataset(observations,source,catalogs,version):
    raw=_canonical(source)+b"\n"; d={"schema_version":"1.0","contract_version":"f5-ground-truth-dataset-v1","dataset_id":"","dataset_version":version,"source_query_dataset":{"dataset_id":source["dataset_id"],"sha256":hashlib.sha256(raw).hexdigest()},"catalogs":{g:{"manifest_id":c.manifest_id,"manifest_sha256":c.sha256,"candidate_count":len(c.candidates),"cell_size_m":c.cell_size_m} for g,c in sorted(catalogs.items())},"collection_protocol":{"version":"f54-madrid-observer-collection-v1","target_observations":{"minimum":20,"maximum":30},"observer_position_policy":"observer_wgs84_not_mentioned_object","description_policy":"original_spanish_independent_observation","ground_truth_capture_before_ranking":True,"evidence_required":True,"orientation_policy":"explicit_evidence_no_egocentric_to_cardinal_inference","synthetic_excluded_from_accuracy":True},"observations":observations}; d["dataset_id"]=ground_truth_dataset_id(d); return d
def _observation(query,record,assignments):
    evidence=[{"evidence_id":r["evidence_id"],"kind":r.get("kind","other"),"logical_reference":r["logical_path"],"sha256":r["sha256"],"description":r.get("description","Evidencia revisada"),"captured_at_utc":r.get("captured_at_utc") or query["provenance"]["collected_at_utc"],"review_status":"reviewed"} for r in record["evidence"]]
    return {"source_query_id":query["query_id"],"location_id":query["location_id"],"derivation_group_id":query["derivation_group_id"],"partition":query["partition"],"description_profile":"complete_observation","comparison_parent_query_id":None,"observer_reference":{"status":"validated","latitude":query["reference"]["latitude"],"longitude":query["reference"]["longitude"],"crs":"EPSG:4326","capture_method":query["reference"]["capture_method"],"reported_accuracy_m":query["reference"]["reported_accuracy_m"],"validation_method":query["reference"]["validation_method"],"evidence":evidence,"review_notes":query["ambiguity"]["notes"] or "Revisión completada."},"orientation":dict(record["orientation"]),"catalog_assignments":dict(assignments),"description_review_status":"reviewed","limitations":list(record["limitations"])}
def _verify(rows,root):
    for row in rows:
        path=root/row["logical_path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row["sha256"]: raise EvidenceValidationError("evidencia ausente o modificada")
def _sha(v): return isinstance(v,str) and len(v)==64 and all(c in "0123456789abcdef" for c in v)
def _coordinate(lat,lon): return isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180
def _canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
