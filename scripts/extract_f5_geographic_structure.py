#!/usr/bin/env python3
"""Materializa extracciones geográficas F5.3 desde variantes F5.1/F5.2."""

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

from src.tfg_phase0.f5_geographic_extraction import ExtractionConfig, FakeGeographicExtractor, QwenGeographicExtractor, finalize_extraction_resources, materialize_extractions, validate_extraction_set_against_sidecar
from src.tfg_phase0.f5_text_transform import QwenTransformersAdapter
from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--extractor", choices=("qwen", "fake"), default="qwen")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B")
    parser.add_argument("--model-revision")
    parser.add_argument("--fake-outputs", type=Path)
    parser.add_argument("--technical-smoke", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, choices=(1, 2), default=2)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    if args.extractor == "qwen" and (args.model_path is None or not args.model_revision): parser.error("Qwen requiere --model-path local y --model-revision")
    if args.extractor == "fake" and not args.technical_smoke: parser.error("FakeGeographicExtractor solo se admite con --technical-smoke")

    raw = args.sidecar.read_bytes(); sidecar = json.loads(raw)
    validate_document(sidecar, "f5_textual_variant_dataset")
    if sidecar["dataset_id"] != textual_variant_dataset_id(sidecar):
        raise RuntimeError("dataset_id del sidecar F5.1 no corresponde al contenido")
    if args.extractor == "qwen":
        adapter = QwenTransformersAdapter(args.model_path, model_id=args.model_id, revision=args.model_revision)
        extractor = QwenGeographicExtractor(adapter)
    else:
        outputs = json.loads(args.fake_outputs.read_text(encoding="utf-8")) if args.fake_outputs else {}
        extractor = FakeGeographicExtractor(outputs)
    try:
        document = materialize_extractions(sidecar, extractor, ExtractionConfig(args.max_new_tokens, args.seed, args.max_attempts), sidecar_logical_path=args.sidecar.name, sidecar_sha256=hashlib.sha256(raw).hexdigest())
    finally:
        extractor.close()
    finalize_extraction_resources(document, extractor)
    validate_document(document, "f5_geographic_extraction_set")
    validate_extraction_set_against_sidecar(document, sidecar, sidecar_sha256=hashlib.sha256(raw).hexdigest())
    final = args.output_root / document["extraction_set_id"]
    output_raw = (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if final.exists():
        if (final / "extractions.json").read_bytes() != output_raw: raise RuntimeError("extracción F5.3 existente incompatible")
    else:
        args.output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".f53-extraction-", dir=args.output_root) as temporary:
            path = Path(temporary); (path / "extractions.json").write_bytes(output_raw); os.replace(path, final)
    print(json.dumps({"extraction_set_id": document["extraction_set_id"], "records": len(document["records"]), "valid": sum(row["status"] == "valid" for row in document["records"]), "rejected": sum(row["status"] == "rejected" for row in document["records"]), "real_model_inference": document["extractor"]["real_model_inference"], "output": str(final)}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
