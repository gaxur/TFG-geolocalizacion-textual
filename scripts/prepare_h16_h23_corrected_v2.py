#!/usr/bin/env python3
"""Versiona H16 corregido y prepara requests CT2L sin modificar v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


H16_OLD = "dark choir"
H16_NEW = "dark altarpiece"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-plan", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    old_plan = json.loads(args.old_plan.read_text(encoding="utf-8"))
    source = json.loads(args.source_config.read_text(encoding="utf-8"))
    original_es = next(row["text"] for row in source["observations"] if row["query_id"] == "H16")
    if "retablo oscuro" not in original_es:
        raise ValueError("el original H16 no contiene retablo oscuro")
    old_controls = {(row["query_id"], row["kind"]): row for row in old_plan["controls"]}
    h16_old = old_controls[("H16", "en_cartographic")]
    h23_old = old_controls[("H23", "en_cartographic")]
    if H16_OLD not in h16_old["text"]:
        raise ValueError("la variante H16 v1 no contiene dark choir")
    h16_text = h16_old["text"].replace(H16_OLD, H16_NEW, 1)
    controls = [
        {**h16_old, "control_id": "H16-en-cartographic-corrected-h11h25-v2", "kind": "en_cartographic_corrected_v2", "text": h16_text, "text_sha256": hashlib.sha256(h16_text.encode()).hexdigest(), "transformation_run_id": "human-semantic-correction-retablo-altarpiece-v2", "supersedes_control_id": h16_old["control_id"]},
        {**h23_old, "control_id": "H23-en-cartographic-claims-v2", "kind": "en_cartographic_claims_v2", "supersedes_control_id": h23_old["control_id"]},
    ]
    variant = {"schema_version": "1.0", "contract_version": "h16-h23-corrected-variant-plan-v2", "variant_plan_id": "", "source_plan_sha256": hashlib.sha256(args.old_plan.read_bytes()).hexdigest(), "source_config_sha256": hashlib.sha256(args.source_config.read_bytes()).hexdigest(), "correction": {"query_id": "H16", "source_es_evidence": "retablo oscuro", "old_en": H16_OLD, "new_en": H16_NEW, "method": "human_authorized_semantic_correction", "old_variant_preserved": True}, "controls": controls}
    variant["variant_plan_id"] = "h16-h23-variant-v2-sha256-" + hashlib.sha256(canonical({key: value for key, value in variant.items() if key != "variant_plan_id"})).hexdigest()
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "variant-plan.json").write_bytes(canonical(variant) + b"\n")
    request_dir = args.output_root / "requests"
    request_dir.mkdir(exist_ok=True)
    for control in controls:
        request = {"schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-request-v1", "query": {"query_id": control["control_id"], "text": control["text"], "language": "en"}, "gallery_ids": ["madrid-50m"], "top_k": 100}
        (request_dir / f"{control['query_id']}.json").write_bytes(canonical(request) + b"\n")
    print(json.dumps({"variant_plan_id": variant["variant_plan_id"], "controls": [{"query_id": row["query_id"], "control_id": row["control_id"], "text_sha256": row["text_sha256"]} for row in controls]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
