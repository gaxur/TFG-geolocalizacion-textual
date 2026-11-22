#!/usr/bin/env python3
"""Prepara o convierte artefactos del VLM final en CPU. No lanza el runner."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tfg_phase0.final_visual_v4 import associations_from_d112, evidence_from_v4, prepare_v4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    prepare, convert = sub.add_parser('prepare'), sub.add_parser('convert')
    for command in (prepare, convert):
        command.add_argument('--context', type=Path, required=True)
        command.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--associations', type=Path, required=True)
    for field in ('fixture', 'assets', 'review', 'run'):
        convert.add_argument('--' + field, type=Path, required=True)
    args = parser.parse_args()
    context = json.loads(args.context.read_text(encoding='utf-8'))
    if args.operation == 'prepare':
        rows = json.loads(args.associations.read_text(encoding='utf-8'))
        document = prepare_v4(context, associations_from_d112(rows) if isinstance(rows, dict) else rows)
    else:
        document = evidence_from_v4(context, fixture_path=args.fixture, assets_path=args.assets,
                                    review_path=args.review, run_path=args.run)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(document, stream, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
