#!/usr/bin/env python3
"""Compara extracciones F5.3 válidas entre variantes de cada observación."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f5_geographic_extraction import compare_extraction_set
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-set", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    raw = args.extraction_set.read_bytes(); document = json.loads(raw); validate_document(document, "f5_geographic_extraction_set")
    report = compare_extraction_set(document, extraction_set_sha256=hashlib.sha256(raw).hexdigest()); validate_document(report, "f5_geographic_extraction_comparison")
    final = args.output_root / report["comparison_id"]
    output_raw = (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if final.exists():
        if (final / "comparison.json").read_bytes() != output_raw: raise RuntimeError("comparación F5.3 existente incompatible")
    else:
        args.output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".f53-comparison-", dir=args.output_root) as temporary:
            path = Path(temporary); (path / "comparison.json").write_bytes(output_raw); os.replace(path, final)
    print(json.dumps({"comparison_id": report["comparison_id"], "comparisons": len(report["comparisons"]), "accuracy_available": False, "output": str(final)}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
