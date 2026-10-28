"""Promoción reversible Top-N a Top-10 sin referencias geográficas."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .mapillary_visual_pilot import reject_ground_truth


class TopNPromotionError(ValueError):
    pass


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def policy_id(policy):
    payload = {key: value for key, value in policy.items() if key != "policy_id"}
    return "topn-promotion-policy-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _reserve_blocks(input_top_n: int, output_top_k: int) -> list[list[int]]:
    boundaries = [20, 50, 100, 200, 500, input_top_n]
    start = output_top_k + 1
    blocks = []
    for end in sorted(set(min(value, input_top_n) for value in boundaries if value >= start)):
        blocks.append([start, end])
        start = end + 1
        if start > input_top_n:
            break
    return blocks


def freeze_policy(
    *,
    enabled: bool = False,
    input_top_n: int = 100,
    output_top_k: int = 10,
    positive_weight: float = 0.0,
    minimum_positive_evidence: float = 0.0,
    minimum_valid_verdicts: int = 1,
    max_promotions: int = 0,
    opened_blocks: Sequence[Sequence[int]] = (),
) -> dict[str, Any]:
    policy = {
        "schema_version": "1.1",
        "contract_version": "topn-promotion-policy-v1",
        "policy_id": "",
        "status": "frozen",
        "enabled": enabled,
        "input_top_n": input_top_n,
        "output_top_k": output_top_k,
        "baseline_score_scope": "full_topn_minmax",
        "visual_policy": {
            "positive_weight": positive_weight,
            "negative_weight": 0.0,
            "minimum_positive_evidence": minimum_positive_evidence,
            "minimum_valid_verdicts": minimum_valid_verdicts,
            "no_coverage_is_neutral": True,
            "missing_failed_unverifiable_conflict_neutral": True,
        },
        "promotion": {
            "max_promotions": max_promotions,
            "reserve_blocks": _reserve_blocks(input_top_n, output_top_k),
            "opened_blocks": [list(value) for value in opened_blocks],
            "complete_block_required": True,
        },
        "discard": {
            "available": False,
            "enabled": False,
            "reason": "contradiction_not_independently_validated",
        },
        "tie_break": ["experimental_score_desc", "baseline_rank_asc", "candidate_id_asc"],
        "ground_truth_allowed": False,
    }
    policy["policy_id"] = policy_id(policy)
    validate_policy(policy)
    return policy


def validate_policy(policy: Mapping[str, Any]) -> None:
    reject_ground_truth(policy, path="policy")
    if policy.get("contract_version") != "topn-promotion-policy-v1" or policy.get("status") != "frozen" or policy.get("policy_id") != policy_id(policy):
        raise TopNPromotionError("política no congelada o identidad inválida")
    if policy["input_top_n"] not in {10, 20, 50, 100, 200, 500} or policy["output_top_k"] != 10 or policy["input_top_n"] < 10 or policy["visual_policy"]["negative_weight"] != 0:
        raise TopNPromotionError("alcance de política v1 inválido")
    if policy["visual_policy"].get("no_coverage_is_neutral") is not True or policy["visual_policy"].get("missing_failed_unverifiable_conflict_neutral") is not True or policy.get("ground_truth_allowed") is not False:
        raise TopNPromotionError("neutralidad o separación GT inválida")
    expected_discard = {"available": False, "enabled": False, "reason": "contradiction_not_independently_validated"}
    if policy.get("discard") != expected_discard:
        raise TopNPromotionError("descarte debe permanecer no disponible")
    values = (policy["visual_policy"]["positive_weight"], policy["visual_policy"]["minimum_positive_evidence"])
    if any(not math.isfinite(value) or value < 0 for value in values) or not 0 <= values[1] <= 1:
        raise TopNPromotionError("parámetros positivos inválidos")
    allowed = {tuple(value) for value in _reserve_blocks(policy["input_top_n"], policy["output_top_k"])}
    if any(tuple(value) not in allowed for value in policy["promotion"]["opened_blocks"]) or not 0 <= policy["promotion"]["max_promotions"] <= 10:
        raise TopNPromotionError("bloques/promociones inválidos")


def apply_promotion(baseline: Sequence[Mapping[str, Any]], aggregate: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    reject_ground_truth(baseline, path="baseline")
    reject_ground_truth(aggregate, path="aggregate")
    validate_policy(policy)
    input_top_n = policy["input_top_n"]
    output_top_k = policy["output_top_k"]
    if len(baseline) != input_top_n or [row.get("rank") for row in baseline] != list(range(1, input_top_n + 1)) or len({row["candidate_id"] for row in baseline}) != input_top_n:
        raise TopNPromotionError("baseline Top-N inválido")
    scores = [float(row["cosine_similarity"]) for row in baseline]
    if any(not math.isfinite(value) for value in scores):
        raise TopNPromotionError("scores no finitos")
    evidence = {row["candidate_id"]: row for row in aggregate.get("candidates", [])}
    if len(evidence) != len(aggregate.get("candidates", [])) or set(evidence) - {row["candidate_id"] for row in baseline}:
        raise TopNPromotionError("agregado duplicado o ajeno")
    low, high = min(scores), max(scores)
    opened = {rank for start, end in policy["promotion"]["opened_blocks"] for rank in range(start, end + 1)}
    decisions = []
    for row in baseline:
        visual = evidence.get(row["candidate_id"])
        positive = float(visual.get("positive_evidence", 0)) if visual else 0.0
        valid = int(visual.get("valid_verdicts", 0)) if visual else 0
        status = visual.get("coverage_status", "missing") if visual else "missing"
        if not 0 <= positive <= 1:
            raise TopNPromotionError("evidencia fuera de rango")
        normalized = 0.5 if high == low else (row["cosine_similarity"] - low) / (high - low)
        eligible = row["rank"] in opened and status == "available" and valid >= policy["visual_policy"]["minimum_valid_verdicts"] and positive >= policy["visual_policy"]["minimum_positive_evidence"]
        modifier = policy["visual_policy"]["positive_weight"] * positive if eligible and policy["enabled"] else 0.0
        decisions.append({"candidate_id": row["candidate_id"], "baseline_rank": row["rank"], "baseline_result": dict(row), "baseline_normalized": normalized, "evidence_status": status, "positive_evidence": positive, "valid_verdicts": valid, "eligible_for_promotion": eligible, "visual_modifier": modifier, "experimental_score": normalized + modifier})
    operations = []
    if policy["enabled"]:
        reserve = sorted((row for row in decisions if row["baseline_rank"] > output_top_k and row["eligible_for_promotion"]), key=lambda row: (-row["experimental_score"], row["baseline_rank"], row["candidate_id"]))[:policy["promotion"]["max_promotions"]]
        active = list(decisions[:output_top_k])
        for promoted in reserve:
            displaced = min(active, key=lambda row: (row["experimental_score"], -row["baseline_rank"], row["candidate_id"]))
            if promoted["experimental_score"] <= displaced["experimental_score"]:
                continue
            active.remove(displaced)
            active.append(promoted)
            operations.append({"promoted_candidate_id": promoted["candidate_id"], "promoted_from_rank": promoted["baseline_rank"], "displaced_candidate_id": displaced["candidate_id"], "displaced_from_rank": displaced["baseline_rank"], "rule": "positive_evidence_v1"})
        final_top10 = sorted(active, key=lambda row: (-row["experimental_score"], row["baseline_rank"], row["candidate_id"]))
        order = sorted(decisions, key=lambda row: (0 if row in final_top10 else 1, final_top10.index(row) if row in final_top10 else 0, -row["experimental_score"], row["baseline_rank"], row["candidate_id"]))
    else:
        final_top10 = decisions[:output_top_k]
        order = list(decisions)
    for rank, row in enumerate(order, 1):
        row["final_rank"] = rank
    restored = [dict(row) for row in baseline]
    document = {
        "schema_version": "1.1",
        "contract_version": "topn-promotion-artifact-v1",
        "artifact_id": "",
        "enabled": policy["enabled"],
        "policy": policy,
        "protocol": {"ground_truth_used": False, "coverage_used_as_score": False, "baseline_immutable": True, "reversible": True, "discard_used": False},
        "baseline_results": restored,
        "candidate_decisions": decisions,
        "operations": operations,
        "final_top10_candidate_ids": [row["candidate_id"] for row in final_top10],
        "full_experimental_order": [row["candidate_id"] for row in order],
        "audit": {
            "candidate_set_invariant_topn": {row["candidate_id"] for row in baseline} == {row["candidate_id"] for row in order},
            "baseline_restoration_verified": canonical_bytes(restored) == canonical_bytes(list(baseline)),
            "disabled_full_order_identity": policy["enabled"] or [row["candidate_id"] for row in baseline] == [row["candidate_id"] for row in order],
        },
    }
    payload = {key: value for key, value in document.items() if key != "artifact_id"}
    document["artifact_id"] = "topn-promotion-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return document


def restore_baseline(document):
    payload = {key: value for key, value in document.items() if key != "artifact_id"}
    expected = "topn-promotion-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()
    if document.get("artifact_id") != expected or not document.get("audit", {}).get("baseline_restoration_verified"):
        raise TopNPromotionError("artefacto de promoción no verificable")
    return [dict(row) for row in document["baseline_results"]]
