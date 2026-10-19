#!/usr/bin/env python3
"""Materializa variantes F5.2 sin sobrescribir el sidecar F5.1 de origen."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_text_transform import FakeTransformer, GenerationConfig, QwenTransformersAdapter, finalize_transformation_run_resources, materialize_variants
from src.tfg_phase0.f5_textual_variants import source_dataset_sha256, validate_textual_variant_dataset
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--source-query-dataset", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/catalog/manifest-50m.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--transformer", choices=("qwen", "fake"), default="qwen")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B")
    parser.add_argument("--model-revision")
    parser.add_argument("--fake-outputs", type=Path)
    parser.add_argument("--technical-smoke", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()

    if args.transformer == "qwen" and (args.model_path is None or not args.model_revision):
        parser.error("Qwen requiere --model-path local y --model-revision exacta")
    if args.transformer == "fake" and not args.technical_smoke:
        parser.error("FakeTransformer solo se admite con --technical-smoke")

    source_sidecar_raw = args.sidecar.read_bytes()
    source_sidecar = json.loads(source_sidecar_raw)
    source_dataset = json.loads(args.source_query_dataset.read_text(encoding="utf-8"))
    catalog = load_verified_f1_catalog(args.manifest, load_region_config(args.config))
    validate_textual_variant_dataset(source_sidecar, source_dataset, source_sha256=source_dataset_sha256(args.source_query_dataset), catalog=catalog)

    if args.transformer == "qwen":
        transformer = QwenTransformersAdapter(args.model_path, model_id=args.model_id, revision=args.model_revision)
    else:
        outputs = json.loads(args.fake_outputs.read_text(encoding="utf-8")) if args.fake_outputs else {}
        transformer = FakeTransformer(outputs)
    generation = GenerationConfig(max_new_tokens=args.max_new_tokens, seed=args.seed)
    try:
        derived, run = materialize_variants(source_sidecar, transformer, generation, source_logical_path=args.sidecar.name, source_sha256=_sha256(source_sidecar_raw))
    finally:
        transformer.close()
    finalize_transformation_run_resources(run, transformer)

    validate_textual_variant_dataset(derived, source_dataset, source_sha256=source_dataset_sha256(args.source_query_dataset), catalog=catalog)
    validate_document(run, "f5_transformation_run")
    final = args.output_root / run["run_id"]
    derived_raw = (json.dumps(derived, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    run_raw = (json.dumps(run, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if final.exists():
        if (final / "derived-sidecar.json").read_bytes() != derived_raw or (final / "run.json").read_bytes() != run_raw:
            raise RuntimeError("ejecución F5.2 existente incompatible")
    else:
        args.output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".f52-transform-", dir=args.output_root) as temporary:
            path = Path(temporary)
            (path / "derived-sidecar.json").write_bytes(derived_raw)
            (path / "run.json").write_bytes(run_raw)
            os.replace(path, final)
    print(json.dumps({"run_id": run["run_id"], "output": str(final), "real_model_inference": run["transformer"]["real_model_inference"], "records": len(run["records"])}, sort_keys=True))
    return 0


def _sha256(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
