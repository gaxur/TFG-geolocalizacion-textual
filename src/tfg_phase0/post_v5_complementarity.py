"""Contratos offline para la auditoría CT2L-OSM/F3 posterior a exploratory-v5."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


class PostV5AuditError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def content_id(prefix: str, document: Mapping[str, Any], excluded: tuple[str, ...]) -> str:
    payload = {key: value for key, value in document.items() if key not in excluded}
    return prefix + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_complementarity_audit(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "ct2l-f3-complementarity-audit-v1":
        raise PostV5AuditError("contrato de complementariedad incompatible")
    if document.get("audit_id") != content_id("ct2l-f3-audit-sha256-", document, ("audit_id",)):
        raise PostV5AuditError("audit_id no corresponde al contenido")
    alignment = document.get("snapshot_alignment", {})
    if alignment.get("same_source_bytes") is not False or alignment.get("causal_comparison_valid_now") is not False:
        raise PostV5AuditError("la auditoría debe conservar el mismatch F3/F4")
    classes = {row.get("class") for row in document.get("information_classes", [])}
    if classes != {"A", "B", "C", "D", "E"}:
        raise PostV5AuditError("clasificación A-E incompleta")
    if document.get("ground_truth_used") is not False or document.get("network_used") is not False or document.get("gpu_used") is not False:
        raise PostV5AuditError("auditoría offline contaminada")


def validate_ablation_plan(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "aligned-cartographic-ablation-plan-v1":
        raise PostV5AuditError("contrato de ablación incompatible")
    if document.get("plan_id") != content_id("aligned-ablation-plan-sha256-", document, ("plan_id",)):
        raise PostV5AuditError("plan_id no corresponde al contenido")
    variants = [row.get("id") for row in document.get("variants", [])]
    if variants != ["G", "GS", "GSN", "FULL"]:
        raise PostV5AuditError("variantes cartográficas no están fijadas")
    if document.get("status") != "blocked_pending_authorization":
        raise PostV5AuditError("la campaña no debe quedar habilitada")
    if document.get("execution", {}).get("performed") is not False:
        raise PostV5AuditError("el plan no puede declarar ejecución")
    if not all(document.get("controls", {}).get(key) is True for key in ("same_source_bytes", "same_candidates", "same_footprint", "same_renderer", "same_checkpoint")):
        raise PostV5AuditError("controles pareados incompletos")


def validate_independent_protocol(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "independent-transfer-validation-protocol-v1":
        raise PostV5AuditError("contrato independiente incompatible")
    if document.get("protocol_id") != content_id("independent-transfer-protocol-sha256-", document, ("protocol_id",)):
        raise PostV5AuditError("protocol_id no corresponde al contenido")
    if document.get("status") != "blocked_no_eligible_local_observations":
        raise PostV5AuditError("el protocolo no debe declararse ejecutable")
    if document.get("current_inventory", {}).get("confirmed_eligible_observations") != 0:
        raise PostV5AuditError("se inventaron observaciones independientes")
    if document.get("selection", {}).get("uses_rankings") is not False or document.get("selection", {}).get("uses_ground_truth_distance_to_candidates") is not False:
        raise PostV5AuditError("selección independiente contaminada")
    if document.get("evaluation", {}).get("references_loaded_after_rankings_frozen") is not True:
        raise PostV5AuditError("falta separación de GT")
    if document.get("final_test", {}).get("opened") is not False:
        raise PostV5AuditError("el test sellado no puede abrirse")


def validate_alternative_matrix(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "post-v5-alternative-matrix-v1":
        raise PostV5AuditError("matriz de alternativas incompatible")
    ids = [row.get("id") for row in document.get("alternatives", [])]
    if ids != ["A", "B", "C", "D", "E"]:
        raise PostV5AuditError("alternativas A-E incompletas")
    selected = [row["id"] for row in document["alternatives"] if row.get("selected")]
    if selected != ["B"]:
        raise PostV5AuditError("debe existir una única prioridad B")
