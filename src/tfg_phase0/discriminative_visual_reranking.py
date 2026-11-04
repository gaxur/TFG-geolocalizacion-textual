"""Reranking visual discriminativo: soporte compartido y geometría explícitos."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .mapillary_visual_pilot import reject_ground_truth


class DiscriminativeRerankingError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def freeze_discriminative_policy(*, positive_weight: float = 0.2, contradiction_weight: float = 0.0) -> dict[str, Any]:
    policy = {"schema_version": "1.0", "contract_version": "discriminative-visual-reranking-policy-v1", "policy_id": "", "status": "diagnostic_frozen", "input_top_n": 50, "output_top_k": 10, "baseline_score_scope": "full_top50_minmax", "positive_weight": positive_weight, "contradiction_weight": contradiction_weight, "shared_support": "inverse_candidate_frequency_per_image_claim", "sequence_aggregation": "noisy_or_over_independent_sequences", "spatial_weights": {"camera_inside_candidate": 1.0, "camera_outside_view_compatible": 0.75, "spatially_ambiguous": "inverse_competing_candidate_count", "orientation_incompatible": 0.0, "insufficient_orientation_metadata": 0.0, "not_computed_for_arm": 0.5}, "missing_unverifiable_conflict_neutral": True, "ground_truth_allowed": False}
    policy["policy_id"] = "discriminative-policy-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in policy.items() if key != "policy_id"})).hexdigest()
    validate_policy(policy)
    return policy


def validate_policy(policy: Mapping[str, Any]) -> None:
    reject_ground_truth(policy, path="discriminative_policy")
    expected = "discriminative-policy-sha256-" + hashlib.sha256(canonical_bytes({key: value for key, value in policy.items() if key != "policy_id"})).hexdigest()
    if policy.get("policy_id") != expected or policy.get("status") != "diagnostic_frozen" or policy.get("input_top_n") != 50 or policy.get("output_top_k") != 10:
        raise DiscriminativeRerankingError("política discriminativa incompatible")
    for key in ("positive_weight", "contradiction_weight"):
        if not math.isfinite(float(policy[key])) or float(policy[key]) < 0:
            raise DiscriminativeRerankingError("peso discriminativo inválido")


def _spatial_weight(association: Mapping[str, Any]) -> float:
    classification = association.get("classification", "not_computed_for_arm")
    if classification == "spatially_ambiguous":
        return 1.0 / max(2, int(association.get("competing_candidate_count", 2)))
    return {"camera_inside_candidate": 1.0, "camera_outside_view_compatible": 0.75, "orientation_incompatible": 0.0, "insufficient_orientation_metadata": 0.0, "not_computed_for_arm": 0.5}.get(classification, 0.0)


def aggregate_discriminative_evidence(claims: Sequence[Mapping[str, Any]], associations: Sequence[Mapping[str, Any]], verdicts: Sequence[Mapping[str, Any]], *, candidate_ids: Sequence[str]) -> dict[str, Any]:
    reject_ground_truth((claims, associations, verdicts), path="discriminative_inputs")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise DiscriminativeRerankingError("candidate_ids duplicados")
    claim_by = {row["claim_id"]: row for row in claims}
    association_by = {(row["candidate_id"], row["image_id"]): row for row in associations}
    image_claim_candidates: dict[tuple[str, str], set[str]] = {}
    for row in verdicts:
        if row.get("status") == "valid" and row.get("verdict") in {"supported", "contradicted"}:
            image_claim_candidates.setdefault((row["image_id"], row["claim_id"]), set()).add(row["candidate_id"])
    candidates = []
    total_claim_weight = sum(0.5 if claim["specificity"] == "generic" else 1.0 for claim in claims) or 1.0
    for candidate_id in candidate_ids:
        claim_outputs = []
        positive = negative = 0.0
        for claim_id, claim in claim_by.items():
            sequence_values: dict[str, list[tuple[str, float, str]]] = {}
            for row in verdicts:
                if row.get("candidate_id") != candidate_id or row.get("claim_id") != claim_id or row.get("status") != "valid":
                    continue
                association = association_by.get((candidate_id, row["image_id"]))
                if association is None:
                    raise DiscriminativeRerankingError("veredicto sin asociación")
                frequency = len(image_claim_candidates.get((row["image_id"], claim_id), {candidate_id}))
                value = _spatial_weight(association) / max(1, frequency)
                sequence = association.get("sequence_id") or f"image:{row['image_id']}"
                sequence_values.setdefault(sequence, []).append((row["verdict"], value, row["image_id"]))
            support_probabilities = []
            contradiction_probabilities = []
            contributions = []
            for sequence, values in sorted(sequence_values.items()):
                verdict_set = {value[0] for value in values}
                state = "conflict" if {"supported", "contradicted"} <= verdict_set else "supported" if "supported" in verdict_set else "contradicted" if "contradicted" in verdict_set else "unverifiable"
                strength = max((value[1] for value in values if value[0] == state), default=0.0)
                if state == "supported": support_probabilities.append(strength)
                if state == "contradicted": contradiction_probabilities.append(strength)
                contributions.append({"sequence_id": sequence, "state": state, "strength": strength, "image_ids": sorted({value[2] for value in values})})
            support = 1.0 - math.prod(1.0 - value for value in support_probabilities)
            contradiction = 1.0 - math.prod(1.0 - value for value in contradiction_probabilities)
            if support and contradiction:
                support = contradiction = 0.0
                state = "conflict"
            else:
                state = "supported" if support else "contradicted" if contradiction else "unverifiable"
            weight = 0.5 if claim["specificity"] == "generic" else 1.0
            positive += weight * support;negative += weight * contradiction
            claim_outputs.append({"claim_id": claim_id, "state": state, "weight": weight, "support_strength": support, "contradiction_strength": contradiction, "sequence_contributions": contributions})
        covered = any(row["candidate_id"] == candidate_id for row in associations)
        candidates.append({"candidate_id": candidate_id, "positive_evidence": positive / total_claim_weight, "negative_evidence": negative / total_claim_weight, "claims": claim_outputs, "coverage_status": "available" if covered else "no_coverage", "valid_verdicts": sum(row.get("candidate_id") == candidate_id and row.get("status") == "valid" for row in verdicts)})
    return {"schema_version": "1.0", "contract_version": "discriminative-visual-aggregate-v1", "candidates": candidates, "protocol": {"ground_truth_used": False, "shared_support_discounted": True, "spatial_compatibility_used": True, "unverifiable_is_neutral": True}}


def apply_discriminative_reranking(baseline: Sequence[Mapping[str, Any]], aggregate: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    reject_ground_truth((baseline, aggregate), path="discriminative_reranking")
    validate_policy(policy)
    if len(baseline) != 50 or [row.get("rank") for row in baseline] != list(range(1, 51)):
        raise DiscriminativeRerankingError("baseline Top-50 inválido")
    evidence = {row["candidate_id"]: row for row in aggregate.get("candidates", [])}
    if set(evidence) - {row["candidate_id"] for row in baseline}:
        raise DiscriminativeRerankingError("evidencia ajena")
    scores = [float(row["cosine_similarity"]) for row in baseline];low, high = min(scores), max(scores)
    decisions = []
    for row in baseline:
        visual = evidence.get(row["candidate_id"], {})
        positive = float(visual.get("positive_evidence", 0.0));negative = float(visual.get("negative_evidence", 0.0))
        reliable = visual.get("coverage_status") == "available" and int(visual.get("valid_verdicts", 0)) > 0
        normalized = 0.5 if high == low else (float(row["cosine_similarity"]) - low) / (high - low)
        modifier = policy["positive_weight"] * positive - policy["contradiction_weight"] * negative if reliable else 0.0
        decisions.append({"candidate_id": row["candidate_id"], "baseline_rank": row["rank"], "baseline_result": dict(row), "baseline_normalized": normalized, "positive_evidence": positive, "negative_evidence": negative, "visual_spatial_modifier": modifier, "experimental_score": normalized + modifier})
    ordered = sorted(decisions, key=lambda row: (-row["experimental_score"], row["baseline_rank"], row["candidate_id"]))
    for rank, row in enumerate(ordered, 1): row["final_rank"] = rank
    baseline_top10 = {row["candidate_id"] for row in baseline[:10]};final_top10 = {row["candidate_id"] for row in ordered[:10]}
    return {"schema_version": "1.0", "contract_version": "discriminative-visual-reranking-artifact-v1", "policy": dict(policy), "protocol": {"ground_truth_used": False, "baseline_fallback_when_no_reliable_evidence": True}, "candidate_decisions": decisions, "full_experimental_order": [row["candidate_id"] for row in ordered], "final_top10_candidate_ids": [row["candidate_id"] for row in ordered[:10]], "operations": [{"type": "enter_top10", "candidate_id": row["candidate_id"]} for row in ordered[:10] if row["candidate_id"] not in baseline_top10] + [{"type": "leave_top10", "candidate_id": row["candidate_id"]} for row in ordered if row["candidate_id"] in baseline_top10 and row["candidate_id"] not in final_top10]}
