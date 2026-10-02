"""Utilidades de hash y metadatos para reproducibilidad."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_provenance(*, artifact_id: str, source: str, source_version: str | None, input_hashes: dict[str, str], parameters: Any, code_version: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_id": artifact_id,
        "source": source,
        "source_version": source_version,
        "input_hashes": dict(sorted(input_hashes.items())),
        "parameters_hash": sha256_json(parameters),
        "code_version": code_version,
    }
