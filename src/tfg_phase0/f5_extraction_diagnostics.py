"""Diagnóstico reproducible de errores estructurales y semánticos F5.3/F5.3b."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping, Sequence


REPORT_PREFIX = "f53b-extraction-diagnostics-sha256-"
STRUCTURAL_CODES = {
    "invalid_json", "root_not_object", "invalid_root_fields", "invalid_root_types",
    "invalid_entity", "duplicate_entity_id", "invalid_entity_name", "invalid_attribute",
    "duplicate_attribute_id", "invalid_relation", "duplicate_relation_id",
    "unknown_relation_reference", "between_requires_two_objects", "relation_requires_one_object",
    "invalid_negation", "duplicate_negation_id", "unknown_negation_target",
    "invalid_observer_orientation", "invalid_ambiguity", "duplicate_ambiguity_id",
    "unknown_ambiguity_reference", "invalid_evidence", "invalid_evidence_span",
    "invalid_literal_evidence", "extractor_error",
}
SEMANTIC_CODES = {
    "evidence_span_mismatch", "evidence_not_literal", "evidence_not_unique",
    "protected_toponym_missing", "negation_index_mismatch", "negation_target_kind_mismatch",
    "negation_lost", "orientation_cannot_be_verified_from_text", "unknown_orientation_has_values",
    "reported_orientation_without_evidence", "egocentric_frame_mismatch",
    "cardinal_frame_mismatch", "forbidden_numeric_geography", "no_geographic_content",
}


def diagnose_extraction_sets(documents: Sequence[Mapping[str, Any]], source_sha256: Sequence[str]) -> dict[str, Any]:
    if len(documents) != len(source_sha256) or not documents:
        raise ValueError("documentos y hashes de diagnóstico no corresponden")
    campaigns = []
    aggregate_codes = Counter()
    aggregate_categories = Counter()
    for document, digest in zip(documents, source_sha256):
        code_counts = Counter()
        category_counts = Counter()
        records = []
        for record in document["records"]:
            codes = [row["code"] for row in record["validation"]["issues"]]
            categories = sorted({_category(code) for code in codes})
            code_counts.update(codes)
            category_counts.update(_category(code) for code in codes)
            records.append({
                "source_query_id": record["source_query_id"],
                "variant_id": record["variant_id"],
                "status": record["status"],
                "attempt_count": record["attempt_count"],
                "json_syntax_valid": "invalid_json" not in codes,
                "structurally_valid": record["validation"]["structurally_valid"],
                "semantically_valid": record["validation"]["semantically_valid"],
                "error_categories": categories,
                "issue_codes": codes,
                "duration_ms": record["duration_ms"],
            })
        aggregate_codes.update(code_counts)
        aggregate_categories.update(category_counts)
        campaigns.append({
            "extraction_set_id": document["extraction_set_id"],
            "source_sha256": digest,
            "prompt_version": document["generation"]["prompt_version"],
            "strategy": document["generation"].get("strategy", "baseline"),
            "max_attempts": document["generation"]["max_attempts"],
            "record_count": len(records),
            "json_syntax_valid_count": sum(row["json_syntax_valid"] for row in records),
            "structurally_valid_count": sum(row["structurally_valid"] for row in records),
            "semantically_valid_count": sum(row["semantically_valid"] for row in records),
            "status_counts": dict(sorted(Counter(row["status"] for row in records).items())),
            "error_category_counts": dict(sorted(category_counts.items())),
            "issue_code_counts": dict(sorted(code_counts.items())),
            "mean_duration_ms": sum(row["duration_ms"] for row in records) / len(records) if records else 0.0,
            "records": records,
        })
    report = {
        "schema_version": "1.0",
        "contract_version": "f53b-extraction-diagnostics-v1",
        "diagnostic_id": REPORT_PREFIX + "0" * 64,
        "campaigns": campaigns,
        "aggregate_error_category_counts": dict(sorted(aggregate_categories.items())),
        "aggregate_issue_code_counts": dict(sorted(aggregate_codes.items())),
        "interpretation": [
            "structural_validity_is_distinct_from_semantic_validity",
            "json_syntax_does_not_imply_contract_compliance",
            "automatic_validation_does_not_measure_semantic_accuracy_against_human_annotations",
        ],
    }
    report["diagnostic_id"] = diagnostic_report_id(report)
    return report


def diagnostic_report_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "campaigns", "aggregate_error_category_counts", "aggregate_issue_code_counts", "interpretation")}
    return REPORT_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def _category(code: str) -> str:
    if code in STRUCTURAL_CODES:
        return "structural"
    if code in SEMANTIC_CODES:
        return "semantic"
    return "unclassified"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
