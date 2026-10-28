#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json
from src.tfg_phase0.h16_h23_claim_review import canonical_bytes, pending_review, sha256_file, validate_review


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    document = pending_review(fixture, protocol, fixture_sha256=sha256_file(args.fixture), protocol_sha256=sha256_file(args.protocol))
    validate_review(document, fixture, protocol, require_complete=False, fixture_sha256=sha256_file(args.fixture), protocol_sha256=sha256_file(args.protocol))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != canonical_bytes(document) + b"\n":
        raise ValueError("el archivo canónico ya existe; use el importador versionado")
    args.output.write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({"output": str(args.output), "claims": len(document["records"]), "review_status": "pending"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
