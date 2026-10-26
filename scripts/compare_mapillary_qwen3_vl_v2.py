#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import canonical_bytes  # noqa: E402
from src.tfg_phase0.mapillary_vlm_smoke import LEVELS, VLMSmokeError, strict_proxy_level  # noqa: E402

HUMAN = ("useful", "partially_useful", "not_useful", "unverifiable")
PREDICTED = ("strong_match", "partial_match", "insufficient", "contradiction", "invalid_json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara post hoc Qwen3-VL v2 con anotaciones humanas")
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text(encoding="utf-8"))
    annotations_doc = json.loads(args.annotations.read_text(encoding="utf-8"))
    adjudication_doc = json.loads(args.adjudication.read_text(encoding="utf-8"))
    if adjudication_doc["inference_sha256"] != digest(args.inference):
        raise VLMSmokeError("adjudicación no corresponde a la inferencia")
    predictions = {row["image_id"]: row for row in inference["records"]}
    humans = {row["image_id"]: row for row in annotations_doc["records"] if row["image_id"]}
    audits = {row["image_id"]: row for row in adjudication_doc["records"]}
    if len(predictions) != 24 or set(predictions) != set(humans) or set(predictions) != set(audits):
        raise VLMSmokeError("IDs de inferencia, anotación y adjudicación no coinciden")

    matrix = {human: {predicted: 0 for predicted in PREDICTED} for human in HUMAN}
    rows = []
    error_types = Counter()
    exact = insufficient_correct = 0
    for image_id in predictions:
        prediction, human, audit = predictions[image_id], humans[image_id], audits[image_id]
        level = prediction["parsed_output"]["verification_level"] if prediction["parsed_output"] else "invalid_json"
        utility = human["utility"]
        matrix[utility][level] += 1
        proxy = strict_proxy_level(utility)
        exact += level == proxy
        insufficient_correct += utility in {"not_useful", "unverifiable"} and level == "insufficient"
        error_types.update(audit["error_types"])
        rows.append({"image_id": image_id, "human_utility": utility, "strict_proxy_level": proxy, "vlm_level": level, "proxy_exact": level == proxy, "contract_valid": prediction["contract_error"] is None, "overclaimed_match": audit["overclaimed_match"], "unjustified_contradiction": audit["unjustified_contradiction"], "orientation_error": audit["orientation_error"], "error_types": audit["error_types"]})
    n = len(rows)
    not_useful_n = sum(row["human_utility"] in {"not_useful", "unverifiable"} for row in rows)
    result = {
        "schema_version": "1.0",
        "contract_version": "mapillary-qwen3-vl-conservative-comparison-v2",
        "inputs": {"inference_sha256": digest(args.inference), "annotations_sha256": digest(args.annotations), "adjudication_sha256": digest(args.adjudication)},
        "category_warning": "La utilidad humana mide utilidad de la fotografía; verification_level mide compatibilidad visual. La matriz es descriptiva. La correspondencia strict_proxy es una convención operativa, no identidad semántica ni ground truth.",
        "strict_proxy_mapping": {value: strict_proxy_level(value) for value in HUMAN},
        "metrics": {
            "images": n,
            "json_valid": {"count": sum(row["contract_valid"] for row in rows), "fraction": sum(row["contract_valid"] for row in rows) / n},
            "strict_proxy_exact": {"count": exact, "fraction": exact / n},
            "overclaimed_match": {"count": sum(row["overclaimed_match"] for row in rows), "fraction": sum(row["overclaimed_match"] for row in rows) / n},
            "unjustified_contradiction": {"count": sum(row["unjustified_contradiction"] for row in rows), "fraction": sum(row["unjustified_contradiction"] for row in rows) / n},
            "orientation_error": {"count": sum(row["orientation_error"] for row in rows), "fraction": sum(row["orientation_error"] for row in rows) / n},
            "correct_insufficient_for_not_useful": {"count": insufficient_correct, "denominator": not_useful_n, "fraction": insufficient_correct / not_useful_n},
        },
        "confusion_matrix": {"rows": list(HUMAN), "columns": list(PREDICTED), "counts": matrix},
        "error_types": [{"type": key, "count": value} for key, value in error_types.most_common()],
        "per_image": rows,
        "decision": {"category": "B", "label": "solo_apoyo_exploratorio_con_revision_humana", "rationale": "El prompt conservador aumenta abstenciones, pero 5/24 salidas son JSON inválido y persisten sobreafirmaciones y contradicciones basadas en ausencia. No se justifica integración ni reranking."},
        "limitations": ["descriptive_development_evaluation", "three_images_used_for_prompt_design", "no_independent_test", "small_non_random_sample", "manual_adjudication", "human_utility_not_equivalent_to_visual_compatibility", "no_statistical_generalization"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result) + b"\n")
    print(json.dumps(result["metrics"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
