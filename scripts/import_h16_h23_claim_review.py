#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.h16_h23_claim_review import canonical_bytes, import_complete_review, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa una revisión humana completa con copia versionada.")
    parser.add_argument("--exported", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--history-dir", type=Path, required=True)
    args = parser.parse_args()
    exported = json.loads(args.exported.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    previous_sha = sha256_file(args.canonical) if args.canonical.is_file() else None
    document = import_complete_review(exported, fixture, protocol, fixture_sha256=sha256_file(args.fixture), protocol_sha256=sha256_file(args.protocol), source_export_sha256=sha256_file(args.exported), previous_canonical_sha256=previous_sha)
    args.canonical.parent.mkdir(parents=True, exist_ok=True)
    args.history_dir.mkdir(parents=True, exist_ok=True)
    if args.canonical.is_file():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = args.history_dir / f"h16-h23-top50-claims-review.{stamp}.{previous_sha[:12]}.json"
        backup.write_bytes(args.canonical.read_bytes())
    temporary = args.canonical.with_suffix(".json.tmp")
    temporary.write_bytes(canonical_bytes(document) + b"\n")
    temporary.replace(args.canonical)
    print(json.dumps({"canonical": str(args.canonical), "canonical_sha256": sha256_file(args.canonical), "previous_sha256": previous_sha, "review_status": "complete"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
