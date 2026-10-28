"""Reranking visual positivo simétrico Top-50, sin GT ni evidencia negativa."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .mapillary_visual_pilot import reject_ground_truth


class SymmetricRerankingError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def freeze_symmetric_policy(*, enabled: bool = True, positive_weight: float = 0.2, minimum_positive_evidence: float = 0.01) -> dict[str, Any]:
    policy = {"schema_version": "1.0", "contract_version": "h16-h23-symmetric-visual-reranking-policy-v1", "policy_id": "", "status": "frozen", "enabled": enabled, "input_top_n": 50, "output_top_k": 10, "baseline_score_scope": "full_top50_minmax", "positive_weight": positive_weight, "minimum_positive_evidence": minimum_positive_evidence, "negative_weight": 0.0, "no_coverage_is_neutral": True, "missing_failed_unverifiable_conflict_neutral": True, "tie_break": ["experimental_score_desc", "baseline_rank_asc", "candidate_id_asc"], "ground_truth_allowed": False}
    policy["policy_id"] = "symmetric-reranking-policy-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in policy.items() if key != "policy_id"})).hexdigest()
    validate_policy(policy)
    return policy


def validate_policy(policy: Mapping[str, Any]) -> None:
    reject_ground_truth(policy, path="symmetric_policy")
    expected = "symmetric-reranking-policy-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in policy.items() if key != "policy_id"})).hexdigest()
    if policy.get("contract_version") != "h16-h23-symmetric-visual-reranking-policy-v1" or policy.get("status") != "frozen" or policy.get("policy_id") != expected:
        raise SymmetricRerankingError("política simétrica no congelada")
    if policy.get("input_top_n") != 50 or policy.get("output_top_k") != 10 or policy.get("negative_weight") != 0 or policy.get("ground_truth_allowed") is not False:
        raise SymmetricRerankingError("alcance simétrico inválido")
    if any(not math.isfinite(float(policy[key])) or float(policy[key]) < 0 for key in ("positive_weight", "minimum_positive_evidence")) or policy["minimum_positive_evidence"] > 1:
        raise SymmetricRerankingError("parámetros simétricos inválidos")


def apply_symmetric_reranking(baseline: Sequence[Mapping[str, Any]], aggregate: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    reject_ground_truth(baseline, path="baseline")
    reject_ground_truth(aggregate, path="aggregate")
    validate_policy(policy)
    if len(baseline) != 50 or [row.get("rank") for row in baseline] != list(range(1, 51)) or len({row.get("candidate_id") for row in baseline}) != 50:
        raise SymmetricRerankingError("baseline Top-50 inválido")
    scores = [float(row["cosine_similarity"]) for row in baseline]
    if any(not math.isfinite(value) for value in scores):
        raise SymmetricRerankingError("scores CT2L no finitos")
    rows = aggregate.get("candidates", [])
    evidence = {row.get("candidate_id"): row for row in rows}
    baseline_ids = {row["candidate_id"] for row in baseline}
    if len(evidence) != len(rows) or set(evidence) - baseline_ids:
        raise SymmetricRerankingError("evidencia duplicada o ajena")
    low, high = min(scores), max(scores)
    decisions = []
    for row in baseline:
        visual = evidence.get(row["candidate_id"])
        positive = float(visual.get("positive_evidence", 0.0)) if visual else 0.0
        status = visual.get("coverage_status", "missing") if visual else "missing"
        valid = int(visual.get("valid_verdicts", 0)) if visual else 0
        if not math.isfinite(positive) or not 0 <= positive <= 1:
            raise SymmetricRerankingError("evidencia positiva inválida")
        available = status == "available" and valid > 0
        effective = positive if available and positive >= policy["minimum_positive_evidence"] else 0.0
        normalized = 0.5 if high == low else (float(row["cosine_similarity"]) - low) / (high - low)
        modifier = policy["positive_weight"] * effective if policy["enabled"] else 0.0
        decisions.append({"candidate_id": row["candidate_id"], "baseline_rank": row["rank"], "baseline_result": dict(row), "baseline_normalized": normalized, "evidence_status": status, "positive_evidence": positive, "effective_positive_evidence": effective, "valid_verdicts": valid, "negative_evidence_used": False, "visual_modifier": modifier, "experimental_score": normalized + modifier})
    ordered = sorted(decisions, key=lambda row: (-row["experimental_score"], row["baseline_rank"], row["candidate_id"])) if policy["enabled"] else list(decisions)
    changes = []
    for final_rank, row in enumerate(ordered, 1):
        row["final_rank"] = final_rank
        if final_rank != row["baseline_rank"]:
            changes.append({"candidate_id": row["candidate_id"], "baseline_rank": row["baseline_rank"], "final_rank": final_rank, "rank_delta": row["baseline_rank"] - final_rank, "crossed_top10_boundary": (row["baseline_rank"] <= 10) != (final_rank <= 10)})
    baseline_top10 = {row["candidate_id"] for row in baseline[:10]}
    final_top10 = {row["candidate_id"] for row in ordered[:10]}
    operations = ([{"type": "enter_top10", "candidate_id": row["candidate_id"], "from_rank": row["baseline_rank"], "to_rank": row["final_rank"]} for row in ordered[:10] if row["candidate_id"] not in baseline_top10] + [{"type": "leave_top10", "candidate_id": row["candidate_id"], "from_rank": row["baseline_rank"], "to_rank": row["final_rank"]} for row in ordered if row["candidate_id"] in baseline_top10 and row["candidate_id"] not in final_top10])
    document = {"schema_version": "1.0", "contract_version": "h16-h23-symmetric-visual-reranking-artifact-v1", "artifact_id": "", "policy": dict(policy), "protocol": {"ground_truth_used": False, "same_formula_all_candidates": True, "coverage_used_as_score": False, "negative_evidence_used": False, "baseline_immutable": True, "reversible": True}, "baseline_results": [dict(row) for row in baseline], "candidate_decisions": decisions, "full_experimental_order": [row["candidate_id"] for row in ordered], "final_top10_candidate_ids": [row["candidate_id"] for row in ordered[:10]], "final_top10": [{"final_rank": row["final_rank"], "candidate_id": row["candidate_id"], "baseline_rank": row["baseline_rank"], "experimental_score": row["experimental_score"]} for row in ordered[:10]], "rank_changes": changes, "operations": operations, "audit": {"candidate_set_invariant_top50": {row["candidate_id"] for row in baseline} == {row["candidate_id"] for row in ordered}, "baseline_restoration_verified": canonical_bytes([dict(row) for row in baseline]) == canonical_bytes(list(baseline)), "top10_entries_equal_exits": sum(row["type"] == "enter_top10" for row in operations) == sum(row["type"] == "leave_top10" for row in operations)}}
    document["artifact_id"] = "symmetric-reranking-artifact-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in document.items() if key != "artifact_id"})).hexdigest()
    return document


def restore_baseline(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected = "symmetric-reranking-artifact-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in document.items() if key != "artifact_id"})).hexdigest()
    if document.get("artifact_id") != expected or not document.get("audit", {}).get("baseline_restoration_verified"):
        raise SymmetricRerankingError("artefacto simétrico manipulado")
    return [dict(row) for row in document["baseline_results"]]
