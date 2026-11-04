"""Contratos y validadores de preparación para la campaña independiente I01-I20."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPECTED_IDS = tuple(f"I{index:02d}" for index in range(1, 21))
LEDGER_STATES = {"CLEAR", "EXCLUDE", "REVIEW"}
FORBIDDEN_LEDGER_FIELDS = {
    "distance", "score", "reason", "match_id", "holdout_id", "coordinates",
    "latitude", "longitude", "nearest", "detector", "threshold", "count",
}


class I20PreparationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def content_id(prefix: str, document: Mapping[str, Any], field: str) -> str:
    return prefix + hashlib.sha256(canonical_bytes({key: value for key, value in document.items() if key != field})).hexdigest()


def validate_ledger_pair(submission: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, int]:
    candidates = submission.get("candidates", [])
    decisions = response.get("decisions", [])
    if submission.get("candidate_count") != len(candidates) or response.get("candidate_count") != len(decisions):
        raise I20PreparationError("cardinalidad ledger incompatible")
    candidate_refs = [row.get("candidate_ref") for row in candidates]
    decision_refs = [row.get("candidate_ref") for row in decisions]
    if len(set(candidate_refs)) != len(candidate_refs) or len(set(decision_refs)) != len(decision_refs):
        raise I20PreparationError("candidate_ref duplicado")
    if set(candidate_refs) != set(decision_refs):
        raise I20PreparationError("respuesta ledger incompleta o desconocida")
    if decision_refs != sorted(decision_refs):
        raise I20PreparationError("decisiones ledger no canónicas")
    if response.get("submission_id") != submission.get("submission_id") or response.get("manifest_commitment") != submission.get("manifest_commitment"):
        raise I20PreparationError("respuesta no vinculada al lote")
    if any(row.get("state") not in LEDGER_STATES or set(row) != {"candidate_ref", "state"} for row in decisions):
        raise I20PreparationError("decisión ledger contiene fuga o estado inválido")
    serialized = json.dumps(response, ensure_ascii=False).casefold()
    if any(f'"{field}"' in serialized for field in FORBIDDEN_LEDGER_FIELDS):
        raise I20PreparationError("respuesta ledger contiene campo prohibido")
    return {state: sum(row["state"] == state for row in decisions) for state in sorted(LEDGER_STATES)}


def validate_annotation_package(document: Mapping[str, Any], *, project_root: Path | None = None) -> dict[str, int]:
    if tuple(document.get("expected_observation_ids", ())) != EXPECTED_IDS:
        raise I20PreparationError("IDs esperados deben ser I01-I20 ordenados")
    observations = document.get("observations", [])
    if document.get("status") == "template_not_collected" and observations:
        raise I20PreparationError("plantilla no puede contener observaciones")
    ids = [row.get("observation_id") for row in observations]
    if len(ids) != len(set(ids)) or any(value not in EXPECTED_IDS for value in ids):
        raise I20PreparationError("observation_id inválido o duplicado")
    asset_ids, asset_hashes = set(), set()
    for row in observations:
        if row["description_sha256"] != sha256_text(row["description_es"]):
            raise I20PreparationError("description_sha256 inválido")
        if row["reference_asset_id"] in asset_ids or row["reference_asset_sha256"] in asset_hashes:
            raise I20PreparationError("referencia exacta reutilizada")
        asset_ids.add(row["reference_asset_id"]); asset_hashes.add(row["reference_asset_sha256"])
        if project_root is not None:
            path = project_root / row["reference_asset_path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["reference_asset_sha256"]:
                raise I20PreparationError("asset ausente o hash inválido")
        claim_ids = set()
        for claim in row["claims"]:
            start,end = claim["span"]["start"],claim["span"]["end"]
            if not 0 <= start < end <= len(row["description_es"]) or row["description_es"][start:end] != claim["text_es"]:
                raise I20PreparationError("span de claim no literal")
            payload = {key: value for key, value in claim.items() if key != "claim_id"}
            expected = "i20-claim-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()
            if claim["claim_id"] != expected or expected in claim_ids:
                raise I20PreparationError("claim_id inválido o duplicado")
            claim_ids.add(expected)
            if claim["kind"] in {"camera_frame_relation", "egocentric_relation"} and not claim["requires_orientation"]:
                raise I20PreparationError("relación sin requirement de orientación")
        orientation=row["orientation"]
        if orientation["status"] == "unknown" and (orientation["bearing_degrees"] is not None or orientation["uncertainty_degrees"] is not None or orientation["meaning"] != "unknown" or orientation["cardinal_conversion_allowed"]):
            raise I20PreparationError("orientación desconocida reinterpretada")
        if orientation["cardinal_conversion_allowed"] and orientation["status"] not in {"camera_heading_verified", "observer_heading_verified"}:
            raise I20PreparationError("conversión cardinal sin orientación verificada")
    if document.get("status") == "frozen":
        if len(observations) < 12 or any(row.get("description_status") != "frozen" for row in observations):
            raise I20PreparationError("anotación congelada incompleta o con drafts")
        expected_id=content_id("i20-annotation-package-sha256-",document,"package_id")
        if document.get("package_id")!=expected_id:
            raise I20PreparationError("package_id de anotación inválido")
    return {"expected": 20, "observed": len(observations), "missing": 20-len(observations)}


def validate_review_package(document: Mapping[str, Any], annotation: Mapping[str, Any]) -> None:
    observations={row["observation_id"]:row for row in annotation.get("observations", [])}
    by_observation: dict[str,list[Mapping[str,Any]]] = {}
    for review in document.get("reviews", []):
        if review["observation_id"] not in observations:
            raise I20PreparationError("review de observación desconocida")
        by_observation.setdefault(review["observation_id"],[]).append(review)
    if document.get("status") == "frozen":
        if set(by_observation)!={row["observation_id"] for row in annotation.get("observations",[])}:
            raise I20PreparationError("review freeze no cubre anotación completa")
        for observation_id,reviews in by_observation.items():
            if len(reviews)!=2 or len({row["reviewer_pseudonym"] for row in reviews})!=2:
                raise I20PreparationError(f"{observation_id} no tiene dos revisores independientes")
            expected={claim["claim_id"] for claim in next(row for row in annotation["observations"] if row["observation_id"]==observation_id)["claims"]}
            for review in reviews:
                ids=[row["claim_id"] for row in review["claim_reviews"]]
                if len(ids)!=len(set(ids)) or set(ids)!=expected:raise I20PreparationError("claim reviews incompletas")
        from .i20_annotation_workflow import detailed_disagreements
        disagreements={observation_id for observation_id,reviews in by_observation.items() if detailed_disagreements(reviews[0],reviews[1]) or any(row["decision"]!="accept" for row in reviews)}
        adjudicated={row["observation_id"] for row in document.get("adjudication", [])}
        if disagreements!=adjudicated:raise I20PreparationError("adjudicación no coincide con discrepancias")
        if document.get("package_id")!=content_id("i20-review-package-sha256-",document,"package_id"):raise I20PreparationError("package_id review inválido")


def validate_gt_package(document: Mapping[str, Any], annotation: Mapping[str, Any]) -> dict[str,int]:
    annotation_ids={row["observation_id"] for row in annotation.get("observations", [])}
    refs=document.get("references",[]);ids=[row["observation_id"] for row in refs]
    if len(ids)!=len(set(ids)) or any(value not in annotation_ids for value in ids):
        raise I20PreparationError("GT duplicado o sin anotación")
    for row in refs:
        if row["status"]=="validated":
            required=(row["latitude"],row["longitude"],row["crs"],row["capture_method"],row["validation_method"],row["source_record_sha256"],row["reviewer_pseudonym"],row["validated_at_utc"])
            if any(value is None for value in required):raise I20PreparationError("GT validado incompleto")
            if row["uncertainty_status"]!="unknown" and row["reported_accuracy_m"] is None:raise I20PreparationError("GT sin precisión documentada")
    if document.get("status")=="frozen":
        if set(ids)!={row["observation_id"] for row in annotation.get("observations",[])} or any(row["status"]!="validated" for row in refs):raise I20PreparationError("GT congelado parcial o no validado")
        if document.get("package_id")!=content_id("i20-ground-truth-package-sha256-",document,"package_id"):raise I20PreparationError("package_id GT inválido")
    return {"validated":sum(row["status"]=="validated" for row in refs),"pending":sum(row["status"]=="pending" for row in refs),"rejected":sum(row["status"]=="rejected" for row in refs)}


def validate_policy_freeze(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "i20-policy-freeze-v1" or document.get("status") != "frozen_before_collection":
        raise I20PreparationError("freeze de políticas incompatible")
    roles={row["id"]:row for row in document.get("policies",[])}
    if set(roles)!={"ct2l","atlas_v3","structured_osm_v4","reliable_v5"}:
        raise I20PreparationError("inventario de políticas incompleto")
    if roles["ct2l"]["transferability"]!="executable":raise I20PreparationError("CT2L debe ser ejecutable")
    if roles["atlas_v3"]["transferability"]!="requires_i_specific_visual_evidence":raise I20PreparationError("Atlas no puede reutilizar bundle H26-H37")
    if roles["atlas_v3"]["fallback_counts_as_atlas_result"] is not False:raise I20PreparationError("fallback Atlas duplicaría CT2L")
    if any(row["recalibration_allowed"] for row in roles.values()):raise I20PreparationError("I01-I20 no permite recalibración")


def build_empty_annotation_package(instructions_sha256: str) -> dict[str,Any]:
    document={"schema_version":"1.0","contract_version":"i20-annotation-package-v1","package_id":"","status":"template_not_collected","expected_observation_ids":list(EXPECTED_IDS),"reference_policy":"single_designated_reference_visual_only","language_policy":"original_spanish","blinding":{"rankings_present":False,"predictions_present":False,"ground_truth_present":False,"candidate_information_present":False},"source_ledger":None,"instructions_sha256":instructions_sha256,"observations":[]}
    document["package_id"]=content_id("i20-annotation-package-sha256-",document,"package_id");return document


def build_empty_review_package() -> dict[str,Any]:
    document={"schema_version":"1.0","contract_version":"i20-review-package-v1","package_id":"","status":"template_not_collected","annotation_package_id":None,"reviewer_count":2,"reviews":[],"adjudication":[]}
    document["package_id"]=content_id("i20-review-package-sha256-",document,"package_id");return document


def build_empty_gt_package() -> dict[str,Any]:
    document={"schema_version":"1.0","contract_version":"i20-ground-truth-package-v1","package_id":"","status":"template_not_collected","annotation_content_seen":False,"predictions_seen":False,"references":[]}
    document["package_id"]=content_id("i20-ground-truth-package-sha256-",document,"package_id");return document
