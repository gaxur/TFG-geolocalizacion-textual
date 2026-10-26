#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_visual_pilot import render_html, validate_annotations, validate_selection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera informe HTML local del piloto Mapillary")
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--photo-manifest", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    photos = json.loads(args.photo_manifest.read_text(encoding="utf-8"))
    annotations = json.loads(args.annotations.read_text(encoding="utf-8"))
    validate_selection(selection)
    validate_annotations(annotations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render_html(selection, photos, annotations, args.output)
    artifacts = {"selection": args.selection, "photo_manifest": args.photo_manifest, "annotations": args.annotations, "report": args.output}
    manifest = {"schema_version": "1.0", "contract_version": "mapillary-visual-pilot-manifest-v1", "selection_id": selection["selection_id"], "ground_truth_used": False, "reranking_performed": False, "artifacts": {name: {"logical_path": str(path.resolve().relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size} for name, path in artifacts.items()}}
    (args.output.parent / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "candidates": len(selection["candidates"]), "photos": len(photos.get("photos", []))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
