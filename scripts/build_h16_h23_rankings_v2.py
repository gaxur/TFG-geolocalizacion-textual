#!/usr/bin/env python3
"""Envuelve respuestas CT2L H16/H23 v2 en un ranking trazable."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant-plan", type=Path, required=True)
    parser.add_argument("--h16-response", type=Path, required=True)
    parser.add_argument("--h23-response", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.variant_plan.read_text(encoding="utf-8"))
    controls = {row["query_id"]: row for row in plan["controls"]}
    rows = []
    checkpoint = None
    for query_id, path in (("H16", args.h16_response), ("H23", args.h23_response)):
        response = json.loads(path.read_text(encoding="utf-8"))
        retrievals = response["retrievals"]
        if len(retrievals) != 1 or retrievals[0]["gallery_id"] != "madrid-50m" or len(retrievals[0]["results"]) != 100:
            raise ValueError("respuesta CT2L incompatible")
        current = response["model"]["checkpoint_sha256"]
        checkpoint = current if checkpoint is None else checkpoint
        if current != checkpoint:
            raise ValueError("checkpoint cambió entre consultas")
        results = retrievals[0]["results"]
        if [row["rank"] for row in results] != list(range(1, 101)) or len({row["candidate_id"] for row in results}) != 100:
            raise ValueError("ranking Top-100 inválido")
        control = controls[query_id]
        rows.append({"query_id": query_id, "control_id": control["control_id"], "kind": control["kind"], "text_sha256": control["text_sha256"], "gallery_id": "madrid-50m", "results": results, "gallery_count": retrievals[0]["gallery_count"], "visual_dataset_id": retrievals[0]["visual_dataset_id"], "embedding_dataset_id": retrievals[0]["embedding_dataset_id"], "ranking_method": retrievals[0]["ranking_method"], "tie_break": retrievals[0]["tie_break"]})
    document = {"schema_version": "1.0", "contract_version": "h16-h23-corrected-top100-rankings-v2", "ranking_id": "", "variant_plan_id": plan["variant_plan_id"], "variant_plan_sha256": hashlib.sha256(args.variant_plan.read_bytes()).hexdigest(), "checkpoint_sha256": checkpoint, "protocol": {"ranking_method": "exhaustive_cosine", "ground_truth_used": False, "coordinates_used_for_retrieval": False, "fine_tuning": False}, "rows": rows, "inputs": {"h16_response_sha256": hashlib.sha256(args.h16_response.read_bytes()).hexdigest(), "h23_response_sha256": hashlib.sha256(args.h23_response.read_bytes()).hexdigest()}}
    document["ranking_id"] = "h16-h23-top100-v2-sha256-" + hashlib.sha256(canonical({key: value for key, value in document.items() if key != "ranking_id"})).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(document) + b"\n")
    print(json.dumps({"ranking_id": document["ranking_id"], "rows": len(rows), "checkpoint_sha256": checkpoint}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
