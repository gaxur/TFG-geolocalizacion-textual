#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_coverage import canonical_bytes  # noqa: E402
from src.tfg_phase0.mapillary_visual_pilot import summarize_annotations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume anotaciones manuales Mapillary sin GT")
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--photo-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize_annotations(json.loads(args.annotations.read_text()), json.loads(args.photo_manifest.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(summary) + b"\n")
    print(json.dumps({"reviewed": summary["reviewed_image_count"], "pending": summary["pending_image_count"], "quantitative_results_available": summary["quantitative_results_available"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
