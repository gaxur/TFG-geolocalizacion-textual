"""Validacion fail-closed de autorizaciones FreeText operacionales."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .dialogue_sessions import canonical, sha256_file
from .freetext_sessions import FreeTextUnavailable, atomic, digest


AUTH_CONTRACT = "atlas-dialogue-freetext-operational-authorization-v1"
RECEIPT_CONTRACT = "atlas-dialogue-freetext-operational-consumption-receipt-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXECUTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FreeTextUnavailable(f"autorizacion FreeText: {field} invalido")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FreeTextUnavailable(f"autorizacion FreeText: {field} invalido") from error
    if parsed.tzinfo is None:
        raise FreeTextUnavailable(f"autorizacion FreeText: {field} sin zona horaria")
    return parsed.astimezone(timezone.utc)


def executor_identity(executor: Any) -> tuple[dict[str, Any], str]:
    try:
        raw = getattr(executor, "identity", None)
    except Exception as error:
        raise FreeTextUnavailable("no se pudo verificar la identidad actual del ejecutor FreeText") from error
    if not isinstance(raw, Mapping) or not raw:
        raise FreeTextUnavailable("identidad del ejecutor FreeText ausente")
    identity = json.loads(json.dumps(raw))
    if not all(isinstance(key, str) and key and value not in (None, "") for key, value in identity.items()):
        raise FreeTextUnavailable("identidad del ejecutor FreeText incompleta")
    for key, value in identity.items():
        if key.endswith("_sha256") and (not isinstance(value, str) or not SHA256.fullmatch(value)):
            raise FreeTextUnavailable(f"hash de identidad del ejecutor invalido: {key}")
    return identity, hashlib.sha256(canonical(identity)).hexdigest()


class OperationalAuthorization:
    """Carga, vincula y vuelve a verificar una autorizacion inmutable."""

    def __init__(self, *, authorization_root: Path, session_root: Path, policy_identity: Mapping[str, str]):
        self.authorization_root = authorization_root.resolve()
        self.session_root = session_root
        self.policy_identity = dict(policy_identity)
        required = {
            "operational_policy_id",
            "operational_policy_version",
            "operational_policy_sha256",
            "core_policy_id",
            "core_policy_version",
            "core_policy_sha256",
        }
        if set(self.policy_identity) != required:
            raise ValueError("policy_identity operacional debe contener exactamente las seis identidades requeridas")
        for key in ("operational_policy_sha256", "core_policy_sha256"):
            if not SHA256.fullmatch(self.policy_identity[key]):
                raise ValueError(f"policy_identity contiene {key} invalido")

    def _authorization_path(self, execution_id: str) -> Path:
        if not EXECUTION_ID.fullmatch(execution_id):
            raise FreeTextUnavailable("execution_id operacional invalido")
        path = (self.authorization_root / f"{execution_id}.json").resolve()
        if path.parent != self.authorization_root:
            raise FreeTextUnavailable("ruta de autorizacion FreeText invalida")
        return path

    def validate(self, execution_id: str, executor: Any) -> dict[str, Any]:
        path = self._authorization_path(execution_id)
        if not path.is_file():
            raise FreeTextUnavailable("autorizacion FreeText operacional ausente")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FreeTextUnavailable("autorizacion FreeText operacional ilegible") from error
        identity, identity_sha256 = executor_identity(executor)
        required = {
            "schema_version": "1.0",
            "contract_version": AUTH_CONTRACT,
            "execution_id": execution_id,
            "status": "OPERATOR_AUTHORIZED",
            "approved": True,
            **self.policy_identity,
            "executor_identity": identity,
            "executor_identity_sha256": identity_sha256,
            "scope": {"session_count": 1, "stages": ["E0", "E1", "E2", "E3"]},
            "budgets": {"maximum_qwen_loads": 4, "maximum_qwen_calls": 4, "maximum_ct2l_loads": 4, "maximum_ct2l_calls": 4, "maximum_questions": 3, "automatic_retries": 0},
            "constraints": {
                "ground_truth_permitted": False,
                "vlm_permitted": False,
                "h38_h61_permitted": False,
                "references_permitted": False,
                "network_permitted": False,
            },
            "reusable_for_other_session": False,
        }
        expected_keys = set(required) | {"authorization_id", "approved_at", "valid_from", "expires_at", "description_sha256"}
        if set(document) != expected_keys or any(document.get(key) != value for key, value in required.items()):
            raise FreeTextUnavailable("autorizacion FreeText operacional incompatible")
        if not isinstance(document.get("description_sha256"), str) or not SHA256.fullmatch(document["description_sha256"]):
            raise FreeTextUnavailable("description_sha256 de autorización inválido")
        authorization_id = document.get("authorization_id")
        if not isinstance(authorization_id, str) or not authorization_id:
            raise FreeTextUnavailable("authorization_id FreeText ausente")
        approved_at = _instant(document.get("approved_at"), "approved_at")
        valid_from = _instant(document.get("valid_from"), "valid_from")
        expires_at = _instant(document.get("expires_at"), "expires_at")
        now = datetime.now(timezone.utc)
        if approved_at > now or valid_from > now or expires_at <= now or expires_at <= valid_from:
            raise FreeTextUnavailable("autorizacion FreeText fuera de su ventana temporal")
        return {
            "document": document,
            "path": path,
            "authorization_sha256": sha256_file(path),
            "executor_identity": identity,
            "executor_identity_sha256": identity_sha256,
        }

    def receipt_path(self, authorization_id: str) -> Path:
        name = hashlib.sha256(authorization_id.encode("utf-8")).hexdigest()
        return self.session_root / ".authorization-receipts" / f"{name}.json"

    def status(self, execution_id: str, executor: Any) -> tuple[str, dict[str, Any] | None]:
        try:
            validated = self.validate(execution_id, executor)
        except FreeTextUnavailable:
            return "invalid", None
        path = self.receipt_path(validated["document"]["authorization_id"])
        return ("consumed" if path.exists() else "authorized"), validated

    def create_receipt(
        self,
        validated: Mapping[str, Any],
        *,
        session_id: str,
        body_sha256: str,
        idempotency_key_sha256: str,
        created_at: str,
    ) -> tuple[dict[str, Any], bool]:
        authorization = validated["document"]
        path = self.receipt_path(authorization["authorization_id"])
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise FreeTextUnavailable("consumo previo FreeText incierto") from error
            same = {
                "authorization_id": authorization["authorization_id"],
                "authorization_sha256": validated["authorization_sha256"],
                "execution_id": authorization["execution_id"],
                "body_sha256": body_sha256,
                "idempotency_key_sha256": idempotency_key_sha256,
                "executor_identity_sha256": validated["executor_identity_sha256"],
            }
            if all(existing.get(key) == value for key, value in same.items()):
                payload = {key: value for key, value in existing.items() if key != "receipt_sha256"}
                if digest(payload) != existing.get("receipt_sha256"):
                    raise FreeTextUnavailable("consumo previo FreeText incierto")
                return existing, True
            raise FreeTextUnavailable("autorizacion FreeText operacional ya consumida")
        receipt = {
            "schema_version": "1.0",
            "contract_version": RECEIPT_CONTRACT,
            "authorization_id": authorization["authorization_id"],
            "authorization_sha256": validated["authorization_sha256"],
            "execution_id": authorization["execution_id"],
            "session_id": session_id,
            "body_sha256": body_sha256,
            "idempotency_key_sha256": idempotency_key_sha256,
            "executor_identity_sha256": validated["executor_identity_sha256"],
            "consumed_at": created_at,
            "reusable_for_other_session": False,
            "state": "reserved",
        }
        receipt["receipt_sha256"] = digest(receipt)
        atomic(path, receipt)
        return receipt, False

    def bind_receipt(self, receipt: Mapping[str, Any], bound_at: str) -> dict[str, Any]:
        path = self.receipt_path(receipt["authorization_id"])
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("receipt_sha256") != receipt.get("receipt_sha256") or current.get("state") not in {"reserved", "bound"}:
            raise FreeTextUnavailable("recibo de consumo FreeText no se puede vincular")
        if current["state"] == "bound":
            return current
        current["state"] = "bound"
        current["bound_at"] = bound_at
        current["receipt_sha256"] = digest({key: value for key, value in current.items() if key != "receipt_sha256"})
        atomic(path, current)
        return current

    def verify_receipt(self, validated: Mapping[str, Any], session: Mapping[str, Any]) -> dict[str, Any]:
        authorization = validated["document"]
        path = self.receipt_path(authorization["authorization_id"])
        if not path.is_file():
            raise FreeTextUnavailable("recibo de consumo FreeText ausente")
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FreeTextUnavailable("recibo de consumo FreeText ilegible") from error
        payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        expected = {
            "contract_version": RECEIPT_CONTRACT,
            "authorization_id": authorization["authorization_id"],
            "authorization_sha256": validated["authorization_sha256"],
            "execution_id": session.get("execution_id"),
            "session_id": session.get("session_id"),
            "executor_identity_sha256": validated["executor_identity_sha256"],
            "reusable_for_other_session": False,
        }
        if digest(payload) != receipt.get("receipt_sha256") or receipt.get("state") != "bound" or any(receipt.get(key) != value for key, value in expected.items()):
            raise FreeTextUnavailable("recibo de consumo FreeText divergente")
        if session.get("authorization_binding") != {
            "authorization_id": receipt["authorization_id"],
            "authorization_sha256": receipt["authorization_sha256"],
            "receipt_sha256": receipt["receipt_sha256"],
            "executor_identity_sha256": receipt["executor_identity_sha256"],
        }:
            raise FreeTextUnavailable("vinculo de autorizacion de sesion divergente")
        return receipt
