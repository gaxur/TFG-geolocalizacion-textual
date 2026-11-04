"""Postprocesador VLM del MVP con artefactos precalculados y fallback CT2L."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol


class VisualPostprocessorError(ValueError):
    pass


class VisualPostprocessor(Protocol):
    @property
    def metadata(self) -> Mapping[str, Any]: ...
    def apply(self, *, query_text: str, processing_variant: str, retrieval: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def close(self) -> None: ...
    @property
    def reserve_k(self) -> int: ...


def query_identity(query_text: str, processing_variant: str, retrieval: Mapping[str, Any]) -> str:
    payload = {"query_text_sha256": hashlib.sha256(query_text.encode()).hexdigest(), "processing_variant": processing_variant, "gallery_id": retrieval["gallery_id"], "visual_dataset_id": retrieval["visual_dataset_id"], "embedding_dataset_id": retrieval["embedding_dataset_id"], "baseline": [{"candidate_id": row["candidate_id"], "cosine_similarity": row["cosine_similarity"]} for row in retrieval["results"]]}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "visual-request-sha256-" + hashlib.sha256(raw).hexdigest()


class PrecomputedVisualPostprocessor:
    def __init__(self, bundle_path: Path, *, fallback: str = "baseline"):
        if fallback not in {"baseline", "error"}:
            raise VisualPostprocessorError("fallback visual inválido")
        document = json.loads(bundle_path.read_text(encoding="utf-8"))
        if document.get("contract_version") not in {"atlas-precomputed-visual-bundle-v1", "atlas-precomputed-visual-bundle-v2"}:
            raise VisualPostprocessorError("bundle visual incompatible")
        entries = document.get("entries", [])
        self._entries = {row["request_id"]: row for row in entries}
        if len(self._entries) != len(entries):
            raise VisualPostprocessorError("request_id visual duplicado")
        self._fallback = fallback
        self._reserve_k = int(document.get("reserve_k", 10))
        if self._reserve_k < 10:
            raise VisualPostprocessorError("reserva visual menor que Top-10")
        self._metadata = {"provider": "precomputed_qwen3_vl", "bundle_id": document["bundle_id"], "models": document.get("models", []), "reserve_k": self._reserve_k}

    @property
    def metadata(self) -> Mapping[str, Any]:
        return self._metadata

    @property
    def reserve_k(self) -> int:
        return self._reserve_k

    def apply(self, *, query_text: str, processing_variant: str, retrieval: Mapping[str, Any]) -> Mapping[str, Any]:
        request_id = query_identity(query_text, processing_variant, retrieval)
        entry = self._entries.get(request_id)
        reserve = list(retrieval["results"])
        baseline = reserve[:10]
        if entry is None:
            if self._fallback == "error":
                raise VisualPostprocessorError("no existe resultado VLM compatible")
            return {"status": "fallback_baseline", "source": "precomputed", "request_id": request_id, "reason": "no_compatible_precomputed_result", "model": None, "policy_id": None, "baseline_results": baseline, "final_results": baseline, "evidence": []}
        reserve_ids = [row["candidate_id"] for row in reserve]
        baseline_ids = reserve_ids[:10]
        expected_reserve = entry.get("reserve_candidate_ids", entry.get("baseline_candidate_ids"))
        final_ids = entry.get("final_candidate_ids", [])
        if expected_reserve != reserve_ids or len(final_ids) != 10 or len(set(final_ids)) != 10 or not set(final_ids) <= set(reserve_ids):
            raise VisualPostprocessorError("resultado visual no corresponde al baseline")
        by_id = {row["candidate_id"]: row for row in reserve}
        final = [{**by_id[candidate_id], "rank": rank} for rank, candidate_id in enumerate(final_ids, 1)]
        return {"status": "applied", "source": "precomputed", "request_id": request_id, "reason": None, "model": entry["model"], "policy_id": entry["policy_id"], "baseline_results": baseline, "final_results": final, "evidence": entry.get("evidence", [])}

    def close(self) -> None:
        return None
