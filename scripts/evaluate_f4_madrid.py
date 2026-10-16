#!/usr/bin/env python3
"""Evalúa rankings F4 ya generados contra referencias validadas."""

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

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import evaluate_rankings, query_inputs_sha256, ranking_set_id, validate_evaluation_result, validate_query_dataset
from src.tfg_phase0.f4_preflight import load_verified_selection
from src.tfg_phase0.f4_validation import (
    load_verified_f1_catalog,
    validate_embedding_bundle,
    validate_retrieval_result,
    validate_visual_manifest,
    verify_visual_image_files,
)
from src.tfg_phase0.validation import validate_document


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--ranking-set", required=True, type=Path)
    parser.add_argument("--partition", choices=("development", "evaluation"), required=True)
    parser.add_argument("--catalog-manifest", required=True, type=Path)
    parser.add_argument("--visual-bundle", required=True, type=Path)
    parser.add_argument("--embedding-bundle", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    args = parser.parse_args()

    catalog = load_verified_f1_catalog(args.catalog_manifest, load_region_config(args.config))
    dataset_raw = args.dataset.read_bytes()
    dataset = json.loads(dataset_raw.decode("utf-8"))
    validate_query_dataset(dataset, catalog)
    visual_manifest_path = args.visual_bundle / "manifest.json"
    embedding_manifest_path = args.embedding_bundle / "manifest.json"
    visual = json.loads(visual_manifest_path.read_text(encoding="utf-8"))
    embedding = json.loads(embedding_manifest_path.read_text(encoding="utf-8"))
    selection, selection_hash = load_verified_selection(args.selection, catalog)
    visual_raw = visual_manifest_path.read_bytes()
    validate_visual_manifest(visual, catalog, selection=selection, selection_sha256=selection_hash)
    verify_visual_image_files(visual, args.visual_bundle)
    matrix, candidate_ids = validate_embedding_bundle(embedding, args.embedding_bundle, visual, visual_raw, catalog)
    ranking_set = json.loads(args.ranking_set.read_text(encoding="utf-8"))
    validate_document(ranking_set, "f4_ranking_set")
    if (
        ranking_set["ranking_set_id"] != ranking_set_id(ranking_set)
        or ranking_set["query_inputs_sha256"] != query_inputs_sha256(dataset, args.partition)
        or ranking_set["embedding_dataset_id"] != embedding["embedding_dataset_id"]
        or ranking_set["checkpoint_sha256"] != embedding["checkpoint"]["sha256"]
        or ranking_set["partition"] != args.partition
        or (args.partition == "evaluation" and ranking_set["frozen_before_reference_access"] is not True)
    ):
        raise RuntimeError("manifest de rankings incompatible o no congelado")
    results = {}
    ranking_artifacts = []
    partition_ids = {query["query_id"] for query in dataset["queries"] if query["partition"] == args.partition}
    for ranking in ranking_set["rankings"]:
        if ranking["query_id"] not in partition_ids:
            raise RuntimeError("ranking ajeno a la partición")
        path = args.results_dir / ranking["logical_path"]
        if not path.is_file() or sha256(path) != ranking["sha256"]:
            raise RuntimeError(f"ranking ausente o modificado: {ranking['query_id']}")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["query"]["query_id"] != ranking["query_id"] or result["effective_k"] != ranking["effective_k"]:
            raise RuntimeError("manifest y ranking no coinciden")
        validate_retrieval_result(result, catalog, embedding_manifest=embedding, candidate_ids=candidate_ids)
        results[ranking["query_id"]] = result
        ranking_artifacts.append({"query_id": ranking["query_id"], "logical_path": ranking["logical_path"], "sha256": ranking["sha256"]})
    document = evaluate_rankings(
        dataset, results, catalog, partition=args.partition,
        dataset_sha256=hashlib.sha256(dataset_raw).hexdigest(),
        visual_dataset_id=visual["visual_dataset_id"], visual_manifest_sha256=sha256(visual_manifest_path),
        embedding_dataset_id=embedding["embedding_dataset_id"], embedding_manifest_sha256=sha256(embedding_manifest_path),
        checkpoint_sha256=embedding["checkpoint"]["sha256"],
        ranking_artifacts=ranking_artifacts,
        ranking_set_id_value=ranking_set["ranking_set_id"],
        ranking_set_sha256=sha256(args.ranking_set),
        rankings_frozen_before_reference_access=ranking_set["frozen_before_reference_access"],
    )
    validate_evaluation_result(document)
    args.output_root.mkdir(parents=True, exist_ok=True)
    final = args.output_root / document["evaluation_id"]
    raw = (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if final.exists():
        if (final / "evaluation.json").read_bytes() != raw:
            raise RuntimeError("evaluación existente incompatible")
    else:
        with tempfile.TemporaryDirectory(prefix=".f4-evaluation-", dir=args.output_root) as temporary:
            temp = Path(temporary)
            (temp / "evaluation.json").write_bytes(raw)
            os.replace(temp, final)
    print(json.dumps({"evaluation_id": document["evaluation_id"], "coverage": document["coverage"], "metrics": document["metrics"]}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
