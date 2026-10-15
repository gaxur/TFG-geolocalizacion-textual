"""Ranking exhaustivo y determinista para la galería CrossText2Loc F4."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .f3_inputs import CatalogInput
from .f4_validation import F4ValidationError


def normalize_l2(vector: Any, *, label: str = "vector") -> Any:
    import numpy as np

    value = np.asarray(vector, dtype=np.float32)
    if value.ndim != 1 or value.shape[0] != 768:
        raise F4ValidationError(f"{label} debe tener forma (768,)")
    if not np.isfinite(value).all():
        raise F4ValidationError(f"{label} contiene valores no finitos")
    norm = float(np.linalg.norm(value))
    if not math.isfinite(norm) or norm == 0:
        raise F4ValidationError(f"{label} tiene norma cero o no finita")
    return np.ascontiguousarray(value / norm, dtype="<f4")


def exhaustive_rank(
    image_embeddings: Any,
    candidate_ids: Sequence[str],
    text_embedding: Any,
    k: int,
) -> list[tuple[str, float]]:
    import numpy as np

    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise F4ValidationError("K debe ser un entero positivo")
    matrix = np.asarray(image_embeddings)
    if matrix.ndim != 2 or matrix.shape[1] != 768 or matrix.shape[0] != len(candidate_ids):
        raise F4ValidationError("matriz e IDs de galería incompatibles")
    if len(candidate_ids) == 0 or len(set(candidate_ids)) != len(candidate_ids):
        raise F4ValidationError("candidate_ids vacíos o duplicados")
    if not np.isfinite(matrix).all():
        raise F4ValidationError("matriz contiene valores no finitos")
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms == 0) or not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
        raise F4ValidationError("matriz no está normalizada L2")
    query = normalize_l2(text_embedding, label="embedding textual")
    scores = np.asarray(matrix, dtype=np.float32) @ query
    if not np.isfinite(scores).all():
        raise F4ValidationError("scores no finitos")
    order = sorted(range(len(candidate_ids)), key=lambda index: (-float(scores[index]), candidate_ids[index]))
    return [(candidate_ids[index], float(scores[index])) for index in order[:min(k, len(order))]]


def build_retrieval_result(
    *,
    query_id: str,
    text: str,
    language: str,
    embedding_dataset_id: str,
    checkpoint_sha256: str,
    ranked: Sequence[tuple[str, float]],
    catalog: CatalogInput,
    gallery_count: int,
    requested_k: int,
    timings_ms: Mapping[str, float],
) -> dict[str, Any]:
    candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    return {
        "schema_version": "2.0",
        "contract_version": "f4-exhaustive-retrieval-v2",
        "query": {"query_id": query_id, "text": text, "language": language},
        "embedding_dataset_id": embedding_dataset_id,
        "checkpoint_sha256": checkpoint_sha256,
        "ranking_method": "exhaustive_cosine",
        "tie_break": "candidate_id_ascending",
        "gallery_count": gallery_count,
        "requested_k": requested_k,
        "effective_k": len(ranked),
        "results": [
            {
                "rank": rank,
                "candidate_id": candidate_id,
                "latitude": candidates[candidate_id].latitude,
                "longitude": candidates[candidate_id].longitude,
                "score": score,
            }
            for rank, (candidate_id, score) in enumerate(ranked, start=1)
        ],
        "timings_ms": dict(timings_ms),
    }
