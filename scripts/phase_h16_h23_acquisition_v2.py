#!/usr/bin/env python3
"""Resume el plan v2 en fases completas de rango, sin GT ni descargas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    assets = plan["assets"]
    phases = []
    previous = set()
    for name, end_rank in (("top10", 10), ("top20", 20), ("top50", 50)):
        selected = {row["image_id"] for row in assets if any(association["baseline_rank"] <= end_rank for association in row["associations"])}
        reusable = {row["image_id"] for row in assets if row["image_id"] in selected and row["status"] == "reusable"}
        pending = selected - reusable
        incremental = selected - previous
        incremental_pending = incremental - reusable
        phase_associations = [association for row in assets if row["image_id"] in selected for association in row["associations"] if association["baseline_rank"] <= end_rank]
        phases.append({"phase": name, "complete_symmetric_ranks": [1, end_rank], "unique_assets_cumulative": len(selected), "reusable_cumulative": len(reusable), "pending_cumulative": len(pending), "new_unique_assets_this_phase": len(incremental), "new_pending_downloads_this_phase": len(incremental_pending), "candidate_image_associations": len(phase_associations), "estimated_pending_bytes": round(len(pending) * plan["storage"]["observed_local_mean_bytes"]), "hard_maximum_pending_bytes": len(pending) * 8_000_000})
        previous = selected
    document = {"schema_version": "1.0", "contract_version": "h16-h23-v2-phased-acquisition-summary-v1", "plan_id": plan["plan_id"], "authorization_status": plan["authorization"]["status"], "downloads_permitted": False, "selection_policy": "complete symmetric rank blocks; no GT; no candidate substitution", "phases": phases, "recommendation": "Top-50 remains the frozen primary experiment. Phases may stage transfer, but results must not be used to decide whether to continue."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({row["phase"]: {key: row[key] for key in ("pending_cumulative", "new_pending_downloads_this_phase", "estimated_pending_bytes", "hard_maximum_pending_bytes")} for row in phases}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
