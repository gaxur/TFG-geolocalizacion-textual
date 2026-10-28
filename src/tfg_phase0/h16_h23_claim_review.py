"""Contrato canónico y validación de la revisión humana H16/H23 Top-50."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSIONS = {"h16-h23-reviewed-claim-set-v1", "h16-h23-reviewed-claim-set-v2"}
CANONICAL_FILENAME = "h16-h23-top50-claims-review.json"
DECISIONS = {"pending", "approved", "rejected"}


class ClaimReviewError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_claims(fixture: Mapping[str, Any]) -> dict[str, tuple[str, Mapping[str, Any]]]:
    expected = {}
    for query in fixture.get("queries", []):
        if not str(query.get("kind", "")).startswith("en_cartographic") or query.get("gallery_id") != "madrid-50m":
            raise ClaimReviewError("fixture no corresponde a la familia en_cartographic + madrid-50m")
        if query["claims"].get("source_text_sha256") != query.get("text_sha256"):
            raise ClaimReviewError("claims no corresponden al texto exacto")
        for claim in query["claims"].get("claims", []):
            claim_id = claim["claim_id"]
            if claim_id in expected:
                raise ClaimReviewError("claim_id duplicado en fixture")
            expected[claim_id] = (query["query_id"], claim)
    if not expected:
        raise ClaimReviewError("fixture sin claims")
    return expected


def pending_review(fixture: Mapping[str, Any], protocol: Mapping[str, Any], *, fixture_sha256: str, protocol_sha256: str) -> dict[str, Any]:
    expected = expected_claims(fixture)
    records = []
    for claim_id, (query_id, claim) in expected.items():
        records.append({"query_id": query_id, "claim": json.loads(json.dumps(claim, ensure_ascii=False)), "decision": "pending", "reason": None, "reviewer": None, "reviewed_at_utc": None})
    records.sort(key=lambda row: (row["query_id"], row["claim"]["evidence"]["span"]["start"], row["claim"]["claim_id"]))
    corrected = fixture.get("contract_version") == "h16-h23-multicandidate-fixture-v2"
    variant = protocol.get("scope", {}).get("variant", "en_cartographic")
    return {
        "schema_version": "1.0",
        "contract_version": "h16-h23-reviewed-claim-set-v2" if corrected else "h16-h23-reviewed-claim-set-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": fixture_sha256,
        "variant": variant,
        "gallery_id": "madrid-50m",
        "candidate_depth": 50,
        "review_status": "pending",
        "provenance": {"kind": "human_review", "imported_at_utc": None, "source_export_sha256": None, "previous_canonical_sha256": None},
        "semantic_warnings": ([{"query_id": "H16", "source_es": "retablo oscuro", "variant_en": "dark altarpiece", "status": "corrected_in_versioned_variant", "automatic_equivalence_accepted": False}] if corrected else [{"query_id": "H16", "source_es": "retablo oscuro", "variant_en": "dark choir", "status": "requires_human_decision", "automatic_equivalence_accepted": False}]),
        "records": records,
    }


def validate_review(document: Mapping[str, Any], fixture: Mapping[str, Any], protocol: Mapping[str, Any], *, require_complete: bool, fixture_sha256: str | None = None, protocol_sha256: str | None = None) -> dict[str, Any]:
    if document.get("contract_version") not in CONTRACT_VERSIONS:
        raise ClaimReviewError("contrato de revisión incompatible")
    if document.get("fixture_id") != fixture.get("fixture_id") or document.get("protocol_id") != protocol.get("protocol_id"):
        raise ClaimReviewError("revisión de otro fixture o protocolo")
    if fixture_sha256 and document.get("fixture_sha256") != fixture_sha256:
        raise ClaimReviewError("hash de fixture incompatible")
    if protocol_sha256 and document.get("protocol_sha256") != protocol_sha256:
        raise ClaimReviewError("hash de protocolo incompatible")
    if document.get("variant") != protocol.get("scope", {}).get("variant", "en_cartographic") or document.get("gallery_id") != "madrid-50m" or document.get("candidate_depth") != 50:
        raise ClaimReviewError("variante, galería o profundidad incompatibles")
    expected = expected_claims(fixture)
    records = document.get("records")
    if not isinstance(records, list) or len(records) != len(expected):
        raise ClaimReviewError("revisión incompleta")
    seen = set()
    pending = 0
    for row in records:
        claim = row.get("claim")
        if not isinstance(claim, Mapping) or claim.get("claim_id") not in expected:
            raise ClaimReviewError("claim desconocido")
        claim_id = claim["claim_id"]
        if claim_id in seen:
            raise ClaimReviewError("claim duplicado")
        seen.add(claim_id)
        query_id, expected_claim = expected[claim_id]
        if row.get("query_id") != query_id or claim != expected_claim:
            raise ClaimReviewError("claim, consulta, texto o hash manipulado")
        decision = row.get("decision")
        if decision not in DECISIONS:
            raise ClaimReviewError("decisión humana inválida")
        if decision == "pending":
            pending += 1
            if any(row.get(key) is not None for key in ("reviewer", "reviewed_at_utc")):
                raise ClaimReviewError("claim pendiente no debe figurar como revisado")
        elif not row.get("reviewer") or not row.get("reviewed_at_utc"):
            raise ClaimReviewError("decisión sin revisor o fecha")
    if seen != set(expected):
        raise ClaimReviewError("faltan claims")
    expected_status = "complete" if pending == 0 else "pending"
    if document.get("review_status") != expected_status:
        raise ClaimReviewError("review_status no coincide con las decisiones")
    if require_complete and pending:
        raise ClaimReviewError(f"revisión incompleta: {pending} claims pendientes")
    return {"valid": True, "claims": len(records), "pending": pending, "approved": sum(row["decision"] == "approved" for row in records), "rejected": sum(row["decision"] == "rejected" for row in records), "gate_passed": pending == 0}


def import_complete_review(exported: Mapping[str, Any], fixture: Mapping[str, Any], protocol: Mapping[str, Any], *, fixture_sha256: str, protocol_sha256: str, source_export_sha256: str, previous_canonical_sha256: str | None) -> dict[str, Any]:
    validate_review(exported, fixture, protocol, require_complete=True, fixture_sha256=fixture_sha256, protocol_sha256=protocol_sha256)
    result = json.loads(json.dumps(exported, ensure_ascii=False))
    result["provenance"] = {"kind": "human_review", "imported_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "source_export_sha256": source_export_sha256, "previous_canonical_sha256": previous_canonical_sha256}
    return result
