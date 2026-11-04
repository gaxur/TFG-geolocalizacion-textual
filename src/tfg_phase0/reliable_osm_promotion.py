"""Confianza heurística para promociones OSM/F3 conservadoras y auditables."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from .structured_osm_reranking import category_matches, normalize_text, object_names


def catalog_statistics(
    objects: Mapping[str, Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    object_cells: dict[str, set[str]] = defaultdict(set)
    for row in associations:
        if row["osm_ref"] in objects:
            object_cells[row["osm_ref"]].add(row["candidate_id"])
    name_objects: dict[str, set[str]] = defaultdict(set)
    name_cells: dict[str, set[str]] = defaultdict(set)
    for osm_ref, obj in objects.items():
        for name in object_names(obj.get("tags", {})):
            name_objects[name["normalized"]].add(osm_ref)
            name_cells[name["normalized"]].update(object_cells.get(osm_ref, ()))
    return {
        "candidate_count": len({row["candidate_id"] for row in associations}),
        "object_cells": {key: sorted(value) for key, value in object_cells.items()},
        "name_objects": {key: sorted(value) for key, value in name_objects.items()},
        "name_cells": {key: sorted(value) for key, value in name_cells.items()},
    }


def classify_description_claims(textual_evidence: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    output = {
        "entities": [], "cartographic_categories": [], "spatial_relations": [],
        "visual_attributes": [], "mixed_attributes": [], "unverifiable": [],
    }
    output["entities"] = [dict(row) for row in textual_evidence.get("names", ())]
    output["cartographic_categories"] = [dict(row) for row in textual_evidence.get("categories", ())]
    output["spatial_relations"] = [dict(row) for row in textual_evidence.get("spatial_relations", ())]
    return output


def visual_support_index(
    claims_by_query: Mapping[str, Sequence[Mapping[str, Any]]],
    aggregate_by_query: Mapping[str, Mapping[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    output = {}
    for query_id, aggregate in aggregate_by_query.items():
        claims = {row["claim_id"]: row for row in claims_by_query.get(query_id, ())}
        for candidate in aggregate.get("candidates", ()):
            supported = []
            for row in candidate.get("claims", ()):
                claim = claims.get(row["claim_id"])
                if row.get("state") != "supported" or claim is None:
                    continue
                supported.append({
                    "claim_id": row["claim_id"],
                    "text": claim["evidence"]["text"],
                    "specificity": claim["specificity"],
                    "independent_sequences": row.get("independent_sequences", 0),
                    "supporting_image_ids": row.get("supporting_image_ids", []),
                })
            output[(query_id, candidate["candidate_id"])] = {
                "coverage_status": candidate.get("coverage_status"),
                "positive_evidence": candidate.get("positive_evidence", 0.0),
                "supported_claims": supported,
            }
    return output


def _visual_family_support(supported_claims: Sequence[Mapping[str, Any]], category: str) -> bool:
    patterns = {
        "crossing": ("paso de peatones",),
        "bollard": ("bolardo",),
        "pharmacy": ("farmacia",),
        "cafe": ("starbucks", "cafeter"),
        "hairdresser": ("peluquer", "alonzo"),
        "museum": ("museo", "oxo"),
        "restaurant": ("escarpin",),
    }
    expected = patterns.get(category, ())
    return any(any(token in normalize_text(row["text"]) for token in expected) for row in supported_claims)


def promotion_confidence(
    *,
    query_id: str,
    candidate: Mapping[str, Any],
    textual_evidence: Mapping[str, Any],
    catalog: Mapping[str, Any],
    visual: Mapping[str, Any] | None,
    require_global_ambiguity: bool = True,
    require_nominal_consistency: bool = True,
    group_objects: bool = True,
    use_visual: bool = True,
) -> dict[str, Any]:
    matches = candidate.get("matches", ())
    proper_names = [row for row in textual_evidence.get("names", ()) if not row.get("generic")]
    name_matches = [row for row in matches if row.get("kind") != "category"]
    exact_names = [row for row in name_matches if row["kind"] in {"exact_name", "compact_name"}]
    global_name_cells = set()
    global_name_objects = set()
    for row in exact_names:
        normalized = normalize_text(row["value"])
        global_name_cells.update(catalog["name_cells"].get(normalized, ()))
        global_name_objects.update(catalog["name_objects"].get(normalized, ()))

    specific = [row for row in matches if row.get("kind") == "category" and row.get("specificity") == "specific" and row.get("score", 0) > 0]
    families = sorted({row["category"] for row in specific})
    object_ids = sorted({row["osm_ref"] for row in specific})
    independent_units = sorted({(row["category"], row["osm_ref"]) for row in specific})
    if group_objects:
        family_count = len(families)
        independent_count = len({row["osm_ref"] for row in specific})
    else:
        family_count = len(specific)
        independent_count = len(specific)

    matched_query_names = {normalize_text(row["query"]) for row in name_matches}
    unmatched_names = [row["text"] for row in proper_names if row["normalized"] not in matched_query_names]
    nominal_mismatch = bool(proper_names and not exact_names and specific)
    if not require_nominal_consistency:
        nominal_mismatch = False

    supported_claims = [] if visual is None else visual.get("supported_claims", [])
    visual_families = sorted(category for category in families if _visual_family_support(supported_claims, category)) if use_visual else []
    visually_corroborated = bool(visual_families)
    globally_unique_name = bool(exact_names) and (len(global_name_cells) <= 1 if require_global_ambiguity else len({row["candidate_frequency"] for row in exact_names}) >= 1)
    chain_or_repeated_name = bool(exact_names) and require_global_ambiguity and len(global_name_cells) > 1
    source_rank = int(candidate["original_rank"])

    high = globally_unique_name and source_rank <= 10 and not nominal_mismatch
    two_families = family_count >= 2 and independent_count >= 2
    medium = not nominal_mismatch and source_rank <= 20 and (two_families or visually_corroborated)
    if high:
        level = "high"
    elif medium:
        level = "medium"
    else:
        level = "low" if name_matches or specific else "none"
    reasons = []
    if globally_unique_name: reasons.append("globally_unique_exact_name")
    if chain_or_repeated_name: reasons.append("name_repeated_across_catalog_cells")
    if two_families: reasons.append("two_distinct_specific_families")
    if visually_corroborated: reasons.append("existing_visual_support_for_specific_family")
    if nominal_mismatch: reasons.append("distinctive_query_name_not_matched")
    if source_rank > 20: reasons.append("weak_ct2l_agreement_below_top20")
    return {
        "query_id": query_id,
        "candidate_id": candidate["candidate_id"],
        "source_rank": source_rank,
        "confidence": level,
        "reasons": reasons,
        "proper_names": [row["text"] for row in proper_names],
        "unmatched_proper_names": unmatched_names,
        "global_name_object_count": len(global_name_objects),
        "global_name_cell_count": len(global_name_cells),
        "specific_families": families,
        "specific_object_ids": object_ids,
        "independent_units": [list(row) for row in independent_units],
        "family_count": family_count,
        "independent_object_count": independent_count,
        "visual_specific_families": visual_families,
        "visual_supported_claims": supported_claims,
        "heuristic_not_calibrated_probability": True,
    }


def insert_at(order: Sequence[str], candidate_id: str, rank: int) -> list[str]:
    output = list(order)
    current = output.index(candidate_id)
    target = max(0, min(rank - 1, len(output) - 1))
    if current <= target:
        return output
    output.pop(current)
    output.insert(target, candidate_id)
    return output


def build_reliable_variants(
    atlas_order: Sequence[str],
    confidence_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    ranked = sorted(confidence_rows, key=lambda row: ({"high": 0, "medium": 1, "low": 2, "none": 3}[row["confidence"]], row["source_rank"], row["candidate_id"]))
    eligible = next((row for row in ranked if row["confidence"] in {"high", "medium"}), None)
    high = next((row for row in ranked if row["confidence"] == "high"), None)
    protected = insert_at(atlas_order, eligible["candidate_id"], 5) if eligible else list(atlas_order)
    conditioned = insert_at(atlas_order, high["candidate_id"], 1) if high else list(atlas_order)
    abstaining = list(atlas_order)
    selected = high or next((row for row in ranked if row["confidence"] == "medium"), None)
    if selected:
        abstaining = insert_at(atlas_order, selected["candidate_id"], 1 if selected["confidence"] == "high" else 5)
    return {
        "top1_protected": protected,
        "top1_conditioned": conditioned,
        "confidence_abstention": abstaining,
    }, {
        "fallback": "atlas_v3",
        "selected_candidate_id": selected["candidate_id"] if selected else None,
        "selected_confidence": selected["confidence"] if selected else None,
        "abstained": selected is None,
        "top1_protected": True,
    }
