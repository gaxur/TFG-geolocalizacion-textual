#!/usr/bin/env python3
"""Compara descriptivamente rankings congelados de las galerías F4 25 m/50 m."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import COMPARISON_PREFIX, gallery_comparison_id, haversine_m, query_inputs_sha256, ranking_set_id, validate_query_dataset
from src.tfg_phase0.f4_preflight import load_verified_selection
from src.tfg_phase0.f4_validation import load_verified_f1_catalog, validate_embedding_bundle, validate_retrieval_result, validate_visual_manifest, verify_visual_image_files
from src.tfg_phase0.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-25m", required=True, type=Path)
    parser.add_argument("--dataset-50m", required=True, type=Path)
    parser.add_argument("--ranking-set-25m", required=True, type=Path)
    parser.add_argument("--ranking-set-50m", required=True, type=Path)
    parser.add_argument("--results-25m", required=True, type=Path)
    parser.add_argument("--results-50m", required=True, type=Path)
    parser.add_argument("--catalog-25m", required=True, type=Path)
    parser.add_argument("--catalog-50m", required=True, type=Path)
    parser.add_argument("--selection-25m", required=True, type=Path)
    parser.add_argument("--selection-50m", required=True, type=Path)
    parser.add_argument("--visual-bundle-25m", required=True, type=Path)
    parser.add_argument("--visual-bundle-50m", required=True, type=Path)
    parser.add_argument("--embedding-bundle-25m", required=True, type=Path)
    parser.add_argument("--embedding-bundle-50m", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    datasets = {label: json.loads(path.read_text(encoding="utf-8")) for label, path in (("25m", args.dataset_25m), ("50m", args.dataset_50m))}
    ranking_sets = {label: json.loads(path.read_text(encoding="utf-8")) for label, path in (("25m", args.ranking_set_25m), ("50m", args.ranking_set_50m))}
    catalogs = {label: load_verified_f1_catalog(path, load_region_config(args.config)) for label, path in (("25m", args.catalog_25m), ("50m", args.catalog_50m))}
    visual_roots = {"25m": args.visual_bundle_25m, "50m": args.visual_bundle_50m}
    embedding_roots = {"25m": args.embedding_bundle_25m, "50m": args.embedding_bundle_50m}
    embeddings = {}
    candidate_ids = {}
    profiles = {}
    model_contracts = {}
    for label in ("25m", "50m"):
        validate_query_dataset(datasets[label], catalogs[label])
        selection, selection_hash = load_verified_selection(getattr(args, f"selection_{label}"), catalogs[label])
        visual_raw = (visual_roots[label] / "manifest.json").read_bytes()
        visual = json.loads(visual_raw.decode("utf-8"))
        validate_visual_manifest(visual, catalogs[label], selection=selection, selection_sha256=selection_hash)
        verify_visual_image_files(visual, visual_roots[label])
        embedding = json.loads((embedding_roots[label] / "manifest.json").read_text(encoding="utf-8"))
        _, candidate_ids[label] = validate_embedding_bundle(embedding, embedding_roots[label], visual, visual_raw, catalogs[label])
        embeddings[label] = embedding
        profiles[label] = visual["profile"]
        model_contracts[label] = {"model": embedding["model"], "checkpoint": embedding["checkpoint"], "preprocessing": embedding["preprocessing"]}
    if profiles["25m"] != profiles["50m"] or model_contracts["25m"] != model_contracts["50m"]:
        raise RuntimeError("perfil visual o modelo no comparables")
    for ranking_set in ranking_sets.values():
        validate_document(ranking_set, "f4_ranking_set")
    hashes = {label: query_inputs_sha256(dataset, "development") for label, dataset in datasets.items()}
    if hashes["25m"] != hashes["50m"]:
        raise RuntimeError("las galerías no usan el mismo conjunto de consultas")
    if any(item["ranking_set_id"] != ranking_set_id(item) for item in ranking_sets.values()):
        raise RuntimeError("ranking set incompatible")
    if ranking_sets["25m"]["checkpoint_sha256"] != ranking_sets["50m"]["checkpoint_sha256"]:
        raise RuntimeError("las galerías no usan el mismo checkpoint")
    for label in ("25m", "50m"):
        if ranking_sets[label]["query_inputs_sha256"] != hashes[label] or ranking_sets[label]["embedding_dataset_id"] != embeddings[label]["embedding_dataset_id"]:
            raise RuntimeError(f"ranking set {label} no corresponde a sus consultas o embeddings")
    by_label = {}
    for label, directory in (("25m", args.results_25m), ("50m", args.results_50m)):
        by_label[label] = {}
        expected_queries = {
            query["query_id"]: {"query_id": query["query_id"], "text": query["description"]["text"], "language": query["description"]["language"]}
            for query in datasets[label]["queries"] if query["partition"] == ranking_sets[label]["partition"]
        }
        if {entry["query_id"] for entry in ranking_sets[label]["rankings"]} != set(expected_queries):
            raise RuntimeError(f"ranking set {label} no cubre exactamente la partición")
        for entry in ranking_sets[label]["rankings"]:
            path = directory / entry["logical_path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError(f"ranking {label} modificado: {entry['query_id']}")
            result = json.loads(path.read_text(encoding="utf-8"))
            expected_count = 1115 if label == "25m" else 253
            if result["gallery_count"] != expected_count or result["effective_k"] != 10 or len(result["results"]) != 10 or result["embedding_dataset_id"] != ranking_sets[label]["embedding_dataset_id"]:
                raise RuntimeError(f"ranking {label} incompatible: {entry['query_id']}")
            validate_retrieval_result(result, catalogs[label], embedding_manifest=embeddings[label], candidate_ids=candidate_ids[label])
            if result["query"] != expected_queries[entry["query_id"]] or result["checkpoint_sha256"] != ranking_sets[label]["checkpoint_sha256"]:
                raise RuntimeError(f"ranking {label} no corresponde al manifest: {entry['query_id']}")
            by_label[label][entry["query_id"]] = result
    if set(by_label["25m"]) != set(by_label["50m"]):
        raise RuntimeError("los ranking sets no contienen las mismas consultas")
    queries = []
    for query_id in sorted(by_label["25m"]):
        left, right = by_label["25m"][query_id], by_label["50m"][query_id]
        if left["query"] != right["query"] or left["checkpoint_sha256"] != right["checkpoint_sha256"]:
            raise RuntimeError("consulta o checkpoint no comparable")
        top1_25, top1_50 = left["results"][0], right["results"][0]
        pair_distances = [
            haversine_m(row_25["latitude"], row_25["longitude"], row_50["latitude"], row_50["longitude"])
            for row_25 in left["results"] for row_50 in right["results"]
        ]
        queries.append({
            "query_id": query_id,
            "top1_25m": top1_25,
            "top1_50m": top1_50,
            "top1_cross_gallery_distance_m": haversine_m(top1_25["latitude"], top1_25["longitude"], top1_50["latitude"], top1_50["longitude"]),
            "minimum_top10_cross_gallery_distance_m": min(pair_distances),
        })
    document = {
        "schema_version": "1.0", "contract_version": "f4-gallery-comparison-v1",
        "comparison_id": COMPARISON_PREFIX + "0" * 64, "query_inputs_sha256": hashes["25m"],
        "checkpoint_sha256": ranking_sets["25m"]["checkpoint_sha256"],
        "galleries": {
            "25m": {"candidate_count": 1115, "dataset_id": datasets["25m"]["dataset_id"], "embedding_dataset_id": ranking_sets["25m"]["embedding_dataset_id"], "ranking_set_id": ranking_sets["25m"]["ranking_set_id"]},
            "50m": {"candidate_count": 253, "dataset_id": datasets["50m"]["dataset_id"], "embedding_dataset_id": ranking_sets["50m"]["embedding_dataset_id"], "ranking_set_id": ranking_sets["50m"]["ranking_set_id"]},
        },
        "queries": queries,
        "empirical_metrics_available": False,
        "limitations": ["no_validated_geographic_references", "different_gallery_cardinalities", "exact_cell_recall_not_directly_comparable"],
    }
    document["comparison_id"] = gallery_comparison_id(document)
    validate_document(document, "f4_gallery_comparison")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"comparison_id": document["comparison_id"], "query_count": len(queries), "empirical_metrics_available": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
