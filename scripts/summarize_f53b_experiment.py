#!/usr/bin/env python3
"""Resume estrategias F5.3b y la comparación de cinco variantes sin accuracy."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--literal", required=True, type=Path)
    parser.add_argument("--guided", required=True, type=Path)
    parser.add_argument("--five-variants", required=True, type=Path)
    parser.add_argument("--ranking-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    strategy_rows = []
    for strategy, path in (("baseline", args.baseline), ("literal_evidence", args.literal), ("guided_schema_literal_evidence", args.guided)):
        document = json.loads(path.read_text(encoding="utf-8"))
        records = document["records"]
        strategy_rows.append({
            "strategy": strategy, "extraction_set_id": document["extraction_set_id"], "sha256": sha256(path),
            "records": len(records), "json_syntax_valid": sum("invalid_json" not in codes(record) for record in records),
            "structurally_valid": sum(record["validation"]["structurally_valid"] for record in records),
            "contract_valid": sum(record["status"] == "valid" for record in records),
            "mean_duration_ms": statistics.fmean(record["duration_ms"] for record in records),
            "issue_counts": dict(sorted(Counter(code for record in records for code in codes(record)).items())),
        })
    five = json.loads(args.five_variants.read_text(encoding="utf-8"))
    by_variant = []
    for kind in ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved", "en_cartographic"):
        records = [record for record in five["records"] if record["variant_kind"] == kind]
        by_variant.append({
            "variant_kind": kind, "records": len(records),
            "json_syntax_valid": sum("invalid_json" not in codes(record) for record in records),
            "structurally_valid": sum(record["validation"]["structurally_valid"] for record in records),
            "contract_valid": sum(record["status"] == "valid" for record in records),
            "mean_duration_ms": statistics.fmean(record["duration_ms"] for record in records),
            "issue_counts": dict(sorted(Counter(code for record in records for code in codes(record)).items())),
        })
    ranking = json.loads(args.ranking_report.read_text(encoding="utf-8"))
    comparisons = [row for row in ranking["comparisons"] if row["variant_kind"] == "en_cartographic"]
    en_ranking = {
        "report_id": ranking["report_id"], "sha256": sha256(args.ranking_report), "comparisons": len(comparisons),
        "top1_agreement": statistics.fmean(row["top1_agreement"] for row in comparisons),
        "mean_jaccard_at_k": statistics.fmean(row["jaccard_at_k"] for row in comparisons),
        "mean_top1_output_distance_m": statistics.fmean(row["top1_output_distance_m"] for row in comparisons),
        "mean_transformation_ms": statistics.fmean(row["transformation_ms"] for row in comparisons),
        "mean_retrieval_ms": statistics.fmean(row["retrieval_ms"] for row in comparisons),
        "geographic_accuracy_available": ranking["geographic_accuracy_available"],
    }
    report = {"schema_version": "1.0", "contract_version": "f53b-experiment-summary-v1", "strategies": strategy_rows, "five_variant_extraction": by_variant, "en_cartographic_ranking": en_ranking, "automatic_integration_approved": False, "limitations": ["technical_development_probes", "no_ground_truth_accuracy", "contract_validity_is_not_semantic_accuracy", "human_review_required"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "automatic_integration_approved": False}, sort_keys=True))
    return 0


def codes(record: dict) -> list[str]:
    return [row["code"] for row in record["validation"]["issues"]]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
