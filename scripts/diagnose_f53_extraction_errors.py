#!/usr/bin/env python3
"""Clasifica errores F5.3/F5.3b sin modificar los artefactos de extracción."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f5_extraction_diagnostics import diagnose_extraction_sets
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-set", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    documents, hashes = [], []
    for path in args.extraction_set:
        raw = path.read_bytes()
        document = json.loads(raw)
        validate_document(document, "f5_geographic_extraction_set")
        documents.append(document)
        hashes.append(hashlib.sha256(raw).hexdigest())
    report = diagnose_extraction_sets(documents, hashes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"diagnostic_id": report["diagnostic_id"], "campaigns": len(report["campaigns"]), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
