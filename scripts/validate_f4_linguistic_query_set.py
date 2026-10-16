#!/usr/bin/env python3
"""Valida el conjunto controlado de robustez lingüística F4.5."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f4_robustness import linguistic_query_inputs, validate_linguistic_query_set


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-set", required=True, type=Path)
    args = parser.parse_args()
    document = json.loads(args.query_set.read_text(encoding="utf-8"))
    validate_linguistic_query_set(document)
    variants = linguistic_query_inputs(document)
    print(json.dumps({"query_set_id": document["query_set_id"], "groups": len(document["groups"]), "variants": len(variants), "status": "valid"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
