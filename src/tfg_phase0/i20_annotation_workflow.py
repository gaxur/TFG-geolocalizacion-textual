"""Paquetes humanos y gates de congelación I01-I20, sin acceso a GT en UI."""

from __future__ import annotations

import hashlib
import json
import base64
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .i20_preparation import EXPECTED_IDS, I20PreparationError, canonical_bytes, content_id, sha256_text


class I20WorkflowError(I20PreparationError):
    pass


def safe_relative_path(value: str) -> Path:
    path=Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise I20WorkflowError("ruta humana insegura")
    return path


def build_annotation_fixture(assignments: Mapping[str, Any], package_root: Path, *, instructions_sha256: str) -> dict[str, Any]:
    rows=[]
    for row in assignments.get("assignments",[]):
        path=safe_relative_path(row["reference_asset_path"])
        absolute=package_root/path
        if not absolute.is_file() or hashlib.sha256(absolute.read_bytes()).hexdigest()!=row["reference_asset_sha256"]:
            raise I20WorkflowError("referencia humana ausente o corrupta")
        rows.append({"observation_id":row["observation_id"],"reference_asset_id":row["reference_asset_id"],"reference_asset_sha256":row["reference_asset_sha256"],"reference_asset_path":path.as_posix()})
    if [row["observation_id"] for row in rows]!=list(EXPECTED_IDS):raise I20WorkflowError("fixture de anotación incompleta")
    fixture={"schema_version":"1.0","contract_version":"i20-annotation-ui-fixture-v1","fixture_id":"","instructions_sha256":instructions_sha256,"expected_observation_ids":list(EXPECTED_IDS),"privacy":{"geography_present":False,"provider_ids_present":False,"rankings_present":False,"predictions_present":False,"external_links_present":False},"observations":rows};fixture["fixture_id"]="i20-annotation-ui-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in fixture.items() if k!="fixture_id"})).hexdigest();return fixture


def build_scene_fixture(annotation_fixture: Mapping[str, Any], geographic: Mapping[str, Any], spatial: Mapping[str, Any]) -> dict[str, Any]:
    by_id={row["observation_id"]:row for row in annotation_fixture["observations"]};geo={row["observation_id"]:row for row in geographic["references"]};pairs=set()
    for row in spatial.get("pairs_below_target",[]):pairs.add(tuple(sorted((row["left"],row["right"]))))
    sequence_groups={}
    for row in geographic["references"]:sequence_groups.setdefault(row["sequence_id"],[]).append(row["observation_id"])
    for ids in sequence_groups.values():
        for index,left in enumerate(ids):
            for right in ids[index+1:]:pairs.add(tuple(sorted((left,right))))
    records=[]
    for left,right in sorted(pairs):
        payload={"left_observation_id":left,"right_observation_id":right,"left_reference_path":by_id[left]["reference_asset_path"],"right_reference_path":by_id[right]["reference_asset_path"]}
        records.append({"pair_id":"scene-pair-sha256-"+hashlib.sha256(canonical_bytes(payload)).hexdigest(),**payload})
    fixture={"schema_version":"1.0","contract_version":"i20-scene-review-fixture-v1","fixture_sha256":"","privacy":{"coordinates_present":False,"provider_ids_present":False,"distances_present":False,"holdout_present":False},"records":records};fixture["fixture_sha256"]=hashlib.sha256(canonical_bytes({k:v for k,v in fixture.items() if k!="fixture_sha256"})).hexdigest();return fixture


def validate_scene_review(document: Mapping[str, Any], fixture: Mapping[str, Any]) -> dict[str,int]:
    expected={row["pair_id"]:(row["left_observation_id"],row["right_observation_id"]) for row in fixture["records"]};rows=document.get("records",[])
    if document.get("fixture_sha256")!=fixture.get("fixture_sha256"):raise I20WorkflowError("scene review no corresponde a fixture")
    if len(rows)!=len(expected) or {row.get("pair_id") for row in rows}!=set(expected):raise I20WorkflowError("scene review incompleta")
    for row in rows:
        if (row["left_observation_id"],row["right_observation_id"])!=expected[row["pair_id"]]:raise I20WorkflowError("par de escena alterado")
        if row["decision"]=="CLEAR" and "uncertain" in {row["same_scene"],row["field_of_view_overlap"],row["same_place_different_frame"]}:raise I20WorkflowError("CLEAR con incertidumbre de escena")
        if row["decision"]=="CLEAR" and (row["same_scene"]=="yes" or row["field_of_view_overlap"]=="yes"):raise I20WorkflowError("CLEAR con solapamiento")
    if document.get("status")=="frozen" and not document.get("reviewer_pseudonym"):raise I20WorkflowError("scene review congelada sin humano")
    return {state:sum(row["decision"]==state for row in rows) for state in ("CLEAR","EXCLUDE","REVIEW")}


def annotation_active_ids(scene_review: Mapping[str, Any]) -> set[str]:
    excluded=set();blocked=set()
    for row in scene_review.get("records",[]):
        if row["decision"]=="EXCLUDE":excluded.update((row["left_observation_id"],row["right_observation_id"]))
        elif row["decision"]=="REVIEW":blocked.update((row["left_observation_id"],row["right_observation_id"]))
    return set(EXPECTED_IDS)-excluded-blocked


def detailed_disagreements(left: Mapping[str,Any], right: Mapping[str,Any]) -> list[str]:
    differences=[]
    for field in ("decision","description_faithfulness","observable_only","orientation_handling","uncertainty_handling"):
        if left.get(field)!=right.get(field):differences.append(field)
    left_claims={row["claim_id"]:row for row in left.get("claim_reviews",[])};right_claims={row["claim_id"]:row for row in right.get("claim_reviews",[])}
    if set(left_claims)!=set(right_claims):differences.append("claim_set")
    for claim_id in sorted(set(left_claims)&set(right_claims)):
        for field in ("verdict","atomicity","evidence_span_valid","orientation_frame_valid"):
            if left_claims[claim_id].get(field)!=right_claims[claim_id].get(field):differences.append(f"claim:{claim_id}:{field}")
    return differences


def validate_complete_reviews(review: Mapping[str,Any], annotation: Mapping[str,Any], active_ids: set[str]) -> dict[str,list[str]]:
    observations={row["observation_id"]:row for row in annotation.get("observations",[]) if row["observation_id"] in active_ids};by_id={}
    for row in review.get("reviews",[]):by_id.setdefault(row["observation_id"],[]).append(row)
    if set(observations)!=set(by_id):raise I20WorkflowError("revisiones no cubren exactamente el cohort activo")
    disagreements={}
    for observation_id,observation in observations.items():
        rows=by_id[observation_id]
        if len(rows)!=2 or len({row["reviewer_pseudonym"] for row in rows})!=2:raise I20WorkflowError("se requieren dos revisores distintos")
        expected_claims={row["claim_id"] for row in observation["claims"]}
        for row in rows:
            claim_ids=[item["claim_id"] for item in row["claim_reviews"]]
            if len(claim_ids)!=len(set(claim_ids)) or set(claim_ids)!=expected_claims:raise I20WorkflowError("revisión de claims incompleta")
        differences=detailed_disagreements(rows[0],rows[1])
        if differences or any(row["decision"]!="accept" for row in rows):disagreements[observation_id]=differences or ["non_accept_decision"]
    adjudications={row["observation_id"]:row for row in review.get("adjudication",[])}
    if set(adjudications)!=set(disagreements):raise I20WorkflowError("adjudicación no corresponde a discrepancias")
    for observation_id,row in adjudications.items():
        if set(row["disagreement_ids"])!=set(disagreements[observation_id]):raise I20WorkflowError("disagreement_ids incompletos")
        original_claims={claim["claim_id"] for claim in observations[observation_id]["claims"]}
        if not set(row["final_claim_ids"]).issubset(original_claims):raise I20WorkflowError("adjudicación introduce claims")
        if row["final_status"]=="include" and row["final_description_es"] not in {None,observations[observation_id]["description_es"]}:raise I20WorkflowError("adjudicación reescribe descripción")
    return disagreements


def validate_freeze_readiness(*, annotation: Mapping[str,Any], scene_review: Mapping[str,Any], scene_fixture: Mapping[str,Any], review: Mapping[str,Any], ledger_receipt: Mapping[str,Any] | None, geographic: Mapping[str,Any]) -> dict[str,Any]:
    blockers=[]
    if scene_review.get("status")!="frozen":blockers.append("scene_review_not_frozen")
    else:
        try:
            scene_counts=validate_scene_review(scene_review,scene_fixture)
            if scene_counts["REVIEW"]:blockers.append("scene_review_pending")
        except I20WorkflowError as error:blockers.append(f"scene_review_invalid:{error}")
    active=annotation_active_ids(scene_review) if not blockers else set()
    observations={row["observation_id"]:row for row in annotation.get("observations",[])}
    if annotation.get("status")!="frozen" or set(observations)!=active or any(row.get("description_status")!="frozen" for row in observations.values()):blockers.append("annotation_not_complete_and_frozen")
    try:
        if active:validate_complete_reviews(review,annotation,active)
    except I20WorkflowError as error:blockers.append(f"reviews_invalid:{error}")
    if review.get("status")!="frozen":blockers.append("reviews_not_frozen")
    if not ledger_receipt or ledger_receipt.get("verification_status")!="valid" or ledger_receipt.get("all_active_candidates_clear") is not True:blockers.append("authentic_blind_ledger_receipt_missing")
    geo_ids={row["observation_id"] for row in geographic.get("references",[])}
    if geographic.get("status")!="frozen" or not active.issubset(geo_ids):blockers.append("geographic_provenance_not_frozen")
    return {"ready":not blockers and len(active)>=12,"active_observations":len(active),"minimum_required":12,"blockers":blockers}


def verify_custodian_response(submission: Mapping[str,Any], response: Mapping[str,Any], public_key_raw: bytes) -> dict[str,Any]:
    """Verifica una respuesta real; nunca genera firmas ni decisiones sintéticas."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        signature_text=str(response["custodian_signature"])
        if not signature_text.startswith("ed25519:"):
            raise I20WorkflowError("firma custodio sin prefijo Ed25519")
        signature=base64.b64decode(signature_text.split(":",1)[1],validate=True)
        if len(signature)!=64 or len(public_key_raw)!=32:
            raise I20WorkflowError("longitud criptográfica inválida")
        unsigned={key:value for key,value in response.items() if key!="custodian_signature"}
        Ed25519PublicKey.from_public_bytes(public_key_raw).verify(signature,canonical_bytes(unsigned))
    except I20WorkflowError:
        raise
    except Exception as error:
        raise I20WorkflowError("firma custodio inválida") from error
    if response.get("protocol")!="blind-exclusion-ledger/v1" or response.get("policy_id")!="i20-exclusion-policy-v1":
        raise I20WorkflowError("protocolo o política ledger incompatible")
    if response.get("submission_id")!=submission.get("submission_id") or response.get("manifest_commitment")!=submission.get("manifest_commitment"):
        raise I20WorkflowError("respuesta ledger no corresponde al submission")
    decisions=response.get("decisions",[]);candidate_refs=sorted(row["candidate_ref"] for row in submission.get("candidates",[]))
    if [row.get("candidate_ref") for row in decisions]!=candidate_refs or len(decisions)!=submission.get("candidate_count"):
        raise I20WorkflowError("decisiones ledger incompletas o no canónicas")
    if any(set(row)!={"candidate_ref","state"} or row["state"] not in {"CLEAR","EXCLUDE","REVIEW"} for row in decisions):
        raise I20WorkflowError("respuesta ledger filtra campos o estado inválido")
    commitment_payload={key:value for key,value in response.items() if key not in {"response_commitment","custodian_signature"}}
    expected="sha256:"+hashlib.sha256(canonical_bytes(commitment_payload)).hexdigest()
    if response.get("response_commitment")!=expected:
        raise I20WorkflowError("response_commitment inválido")
    counts={state:sum(row["state"]==state for row in decisions) for state in ("CLEAR","EXCLUDE","REVIEW")}
    return {"verification_status":"valid","submission_id":response["submission_id"],"manifest_commitment":response["manifest_commitment"],"response_commitment":response["response_commitment"],"custodian_key_id":response["custodian_key_id"],"decision_counts":counts,"all_active_candidates_clear":counts["EXCLUDE"]==0 and counts["REVIEW"]==0}
