#!/usr/bin/env python3
"""Calcula estabilidad anchor-variante F4.5 desde rankings congelados."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import ranking_set_id
from src.tfg_phase0.f4_preflight import load_verified_selection
from src.tfg_phase0.f4_robustness import aggregate_comparisons, compare_rankings, length_bucket, linguistic_query_inputs_sha256, robustness_result_id, validate_linguistic_query_set, validate_robustness_result
from src.tfg_phase0.f4_validation import load_verified_f1_catalog, validate_embedding_bundle, validate_retrieval_result, validate_visual_manifest, verify_visual_image_files
from src.tfg_phase0.validation import validate_document


def sha256(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-set", required=True, type=Path)
    parser.add_argument("--ranking-set", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--gallery-label", choices=("25m", "50m"), required=True)
    parser.add_argument("--gallery-count", type=int, required=True)
    parser.add_argument("--catalog-manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--visual-bundle", required=True, type=Path)
    parser.add_argument("--embedding-bundle", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    query_set_raw = args.query_set.read_bytes()
    query_set = json.loads(query_set_raw)
    validate_linguistic_query_set(query_set)
    ranking_set = json.loads(args.ranking_set.read_text(encoding="utf-8"))
    validate_document(ranking_set, "f4_ranking_set")
    if ranking_set["ranking_set_id"] != ranking_set_id(ranking_set) or ranking_set["query_inputs_sha256"] != linguistic_query_inputs_sha256(query_set):
        raise RuntimeError("ranking set no corresponde al query set")
    catalog = load_verified_f1_catalog(args.catalog_manifest, load_region_config(args.config))
    if len(catalog.candidates) != args.gallery_count:
        raise RuntimeError("cardinalidad de catálogo incompatible")
    expected_spacing = 25 if args.gallery_label == "25m" else 50
    if (catalog.spacing_m, catalog.cell_size_m) != (expected_spacing, expected_spacing):
        raise RuntimeError("etiqueta de galería no corresponde al catálogo")
    selection, selection_hash = load_verified_selection(args.selection, catalog)
    visual_manifest_path = args.visual_bundle / "manifest.json"
    visual_raw = visual_manifest_path.read_bytes()
    visual = json.loads(visual_raw.decode("utf-8"))
    validate_visual_manifest(visual, catalog, selection=selection, selection_sha256=selection_hash)
    verify_visual_image_files(visual, args.visual_bundle)
    embedding_manifest_path = args.embedding_bundle / "manifest.json"
    embedding = json.loads(embedding_manifest_path.read_text(encoding="utf-8"))
    _, candidate_ids = validate_embedding_bundle(embedding, args.embedding_bundle, visual, visual_raw, catalog)
    if ranking_set["embedding_dataset_id"] != embedding["embedding_dataset_id"] or ranking_set["checkpoint_sha256"] != embedding["checkpoint"]["sha256"]:
        raise RuntimeError("ranking set no corresponde a embeddings/checkpoint")
    ranking_entries = {row["query_id"]: row for row in ranking_set["rankings"]}
    variants = {variant["query_id"]: (group, variant) for group in query_set["groups"] for variant in group["variants"]}
    if set(ranking_entries) != set(variants): raise RuntimeError("cobertura incompleta del ranking set")
    rankings = {}
    for query_id, entry in ranking_entries.items():
        path = args.results_dir / entry["logical_path"]
        if sha256(path) != entry["sha256"]: raise RuntimeError(f"ranking modificado: {query_id}")
        result = json.loads(path.read_text())
        group, variant = variants[query_id]
        if result["query"] != {"query_id": query_id, "text": variant["text"], "language": variant["language"]} or result["gallery_count"] != args.gallery_count or result["effective_k"] != 10 or result["embedding_dataset_id"] != ranking_set["embedding_dataset_id"]:
            raise RuntimeError(f"ranking incompatible: {query_id}")
        validate_retrieval_result(result, catalog, embedding_manifest=embedding, candidate_ids=candidate_ids)
        if result["checkpoint_sha256"] != ranking_set["checkpoint_sha256"]:
            raise RuntimeError(f"checkpoint de ranking incompatible: {query_id}")
        rankings[query_id] = result
    comparisons = []
    for group in query_set["groups"]:
        anchor = next(variant for variant in group["variants"] if variant["transformation"] == "anchor")
        for variant in group["variants"]:
            if variant is anchor: continue
            comparisons.append({"group_id": group["group_id"], "anchor_query_id": anchor["query_id"], "variant_query_id": variant["query_id"], "language": variant["language"], "transformation": variant["transformation"], "semantic_relation": variant["semantic_relation"], "word_count": variant["word_count"], "attribute_count": variant["attribute_count"], "length_bucket": length_bucket(variant["word_count"]), "metrics": compare_rankings(rankings[anchor["query_id"]], rankings[variant["query_id"]])})
    document = {"schema_version": "1.0", "contract_version": "f4-linguistic-robustness-result-v1", "robustness_result_id": "f4-madrid-linguistic-robustness-sha256-" + "0" * 64, "query_set_id": query_set["query_set_id"], "query_set_sha256": hashlib.sha256(query_set_raw).hexdigest(), "gallery": {"label": args.gallery_label, "candidate_count": args.gallery_count, "catalog_manifest_id": catalog.manifest_id, "catalog_manifest_sha256": catalog.sha256, "visual_dataset_id": visual["visual_dataset_id"], "visual_manifest_sha256": sha256(visual_manifest_path), "embedding_dataset_id": embedding["embedding_dataset_id"], "embedding_manifest_sha256": sha256(embedding_manifest_path)}, "checkpoint_sha256": ranking_set["checkpoint_sha256"], "ranking_set_id": ranking_set["ranking_set_id"], "ranking_set_sha256": sha256(args.ranking_set), "top_k": 10, "comparisons": comparisons, "aggregates": aggregate_comparisons(comparisons), "geographic_accuracy_available": False, "limitations": ["technical_controlled_queries", "no_validated_ground_truth", "top10_censored_rank_shift", "scores_are_not_probabilities"]}
    document["robustness_result_id"] = robustness_result_id(document)
    validate_robustness_result(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"robustness_result_id": document["robustness_result_id"], "gallery": args.gallery_label, "comparisons": len(comparisons)}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
