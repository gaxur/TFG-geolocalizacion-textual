#!/usr/bin/env python3
"""Materializa las anotaciones proporcionadas por el responsable, sin inferirlas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.tfg_phase0.visual_reranking import canonical_bytes


VERDICTS_BY_IMAGE = {
    "1210433070142949": ["supported"] * 5,
    "1401333830797121": ["unverifiable"] * 5,
    "1467353800748949": ["contradicted", "unverifiable", "unverifiable", "unverifiable", "unverifiable"],
    "483221386454901": ["unverifiable", "unverifiable", "unverifiable", "supported", "supported"],
    "174852081596618": ["contradicted", "unverifiable", "unverifiable", "supported", "supported"],
    "496369941555121": ["unverifiable", "unverifiable", "unverifiable", "supported", "supported"],
    "1000448337748748": ["unverifiable", "unverifiable", "supported", "supported", "unverifiable"],
    "224548649040144": ["unverifiable"] * 5,
    "880688654590164": ["unverifiable"] * 5,
    "484760569616148": ["unverifiable"] * 5,
    "1353042103210892": ["unverifiable"] * 5,
    "284314086703727": ["unverifiable"] * 5,
}
EVIDENCE_BY_IMAGE = {
    "1210433070142949": ["Se observa una interseccion en frente.", "Se observa una iglesia en frente.", "Se observa un arco en la entrada a la iglesia.", "Se observa un arco en frente.", "Se observa una iglesia construida por ladrillos."],
    "1467353800748949": ["Se observa una recta.", None, None, None, None],
    "483221386454901": [None, None, None, "Se observan edificios.", "Se observan edificios."],
    "174852081596618": ["Se observa una recta.", None, None, "Se observan edificios.", "Se observan edificios."],
    "496369941555121": [None, None, None, "Se observan edificios.", "Se observan edificios."],
    "1000448337748748": [None, None, "Se observa un edificio con un arco.", "Se observan arcos en frente.", None],
}
ANNOTATION_TIME = "2026-10-26T08:48:02.296Z"
FIRST_ANNOTATION_TIME = "2026-10-26T08:48:02.295Z"
CLAIM_REVIEW_TIME_FIRST = "2026-10-26T08:35:49.520Z"
CLAIM_REVIEW_TIME_REST = "2026-10-26T08:35:49.521Z"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atomic-fixture", type=Path, required=True)
    parser.add_argument("--h11-fixture", type=Path, required=True)
    parser.add_argument("--atomic-output", type=Path, required=True)
    parser.add_argument("--claims-output", type=Path, required=True)
    args = parser.parse_args()
    atomic_fixture = json.loads(args.atomic_fixture.read_text(encoding="utf-8"))
    h11_fixture = json.loads(args.h11_fixture.read_text(encoding="utf-8"))

    grouped: dict[str, list[dict]] = {}
    for record in atomic_fixture["annotation_template"]["records"]:
        grouped.setdefault(record["image_id"], []).append(record)
    if set(grouped) != set(VERDICTS_BY_IMAGE):
        raise ValueError("las imágenes suministradas no coinciden con la fixture")
    records = []
    for image_id, source_records in grouped.items():
        verdicts = VERDICTS_BY_IMAGE[image_id]
        if len(source_records) != len(verdicts):
            raise ValueError(f"número de veredictos incompatible: {image_id}")
        for source, verdict in zip(source_records, verdicts):
            records.append({
                **source,
                "human_verdict": verdict,
                "observed_evidence": None,
                "reason": None,
                "review_status": "reviewed",
                "reviewer": "marcos",
                "reviewed_at_utc": FIRST_ANNOTATION_TIME if image_id in {"1210433070142949", "1401333830797121"} else ANNOTATION_TIME,
            })
    index_by_image = {image_id: 0 for image_id in grouped}
    for record in records:
        index = index_by_image[record["image_id"]]
        record["observed_evidence"] = EVIDENCE_BY_IMAGE.get(record["image_id"], [None] * len(grouped[record["image_id"]]))[index]
        index_by_image[record["image_id"]] += 1
    annotations = {
        "schema_version": "1.0",
        "contract_version": "visual-atomic-human-annotations-v1",
        "instructions": dict(atomic_fixture["annotation_template"]["instructions"]),
        "records": records,
    }

    reviewed_records = []
    for index, claim in enumerate(h11_fixture["claims"]["claims"]):
        reviewed_records.append({
            "claim": claim,
            "decision": "approved",
            "reason": None,
            "reviewer": "marcos",
            "reviewed_at_utc": CLAIM_REVIEW_TIME_FIRST if index == 0 else CLAIM_REVIEW_TIME_REST,
        })
    reviewed_claims = {
        "schema_version": "1.0",
        "contract_version": "visual-reviewed-claim-set-v1",
        "fixture_id": h11_fixture["fixture_id"],
        "fixture_role": "development",
        "review_status": "complete",
        "records": reviewed_records,
    }
    args.atomic_output.write_bytes(canonical_bytes(annotations) + b"\n")
    args.claims_output.write_bytes(canonical_bytes(reviewed_claims) + b"\n")
    print(json.dumps({"atomic_records": len(records), "reviewed_claims": len(reviewed_records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
