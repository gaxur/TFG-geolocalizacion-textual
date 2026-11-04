#!/usr/bin/env python3
"""Ejecución física real del A/B congelado, sin acceso a GT antes del freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.crs import wgs84_to_epsg25830
from src.tfg_phase0.selector_e2e import build_physical_plan, execute_physical_plan, freeze_arm_rankings, physical_task_id, project_results
from src.tfg_phase0.symmetric_visual_reranking import canonical_bytes, freeze_symmetric_policy
from src.tfg_phase0.visual_reranking import parse_verdict_only, verdict_only_prompt, verdict_only_schema
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS

ART = ROOT / "results/generated/mapillary/h16-h23-selector-comparison-v1"
SOURCE = ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v2"
MODEL_PATHS = {
    "qwen3-vl-2b": Path("/home/dataai/models/hf/Qwen3-VL-2B-Instruct-89644892e4d8"),
    "qwen3-vl-8b": Path("/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8"),
}
MODEL_FILES = {
    "qwen3-vl-2b": {"model.safetensors": (4255140312, "7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0")},
    "qwen3-vl-8b": {
        "model-00001-of-00004.safetensors": (4902275944, "d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa"),
        "model-00002-of-00004.safetensors": (4915962496, "8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5"),
        "model-00003-of-00004.safetensors": (4999831048, "83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192"),
        "model-00004-of-00004.safetensors": (2716270024, "0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5"),
    },
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def load_inputs():
    fixture = json.loads((SOURCE / "fixture.json").read_text())
    arms = {name: json.loads((ART / filename).read_text()) for name, filename in (("coverage_adaptive", "coverage_adaptive-manifest.json"), ("geometric_adaptive", "geometric_adaptive-manifest.json"))}
    claims = {query["query_id"]: query["claims"]["claims"] for query in fixture["queries"]}
    return fixture, arms, claims


def prepare() -> None:
    fixture, arms, claims = load_inputs()
    pending = json.loads((ART / "union-asset-manifest.json").read_text())
    historical = json.loads((SOURCE / "partial-existing-assets.json").read_text())
    expected = set().union(*(set(manifest["image_ids"]) for manifest in arms.values()))
    assets = {}
    for source_path, document in ((ART / "union-asset-manifest.json", pending), (SOURCE / "partial-existing-assets.json", historical)):
        for row in document["assets"]:
            if row["image_id"] not in expected:
                continue
            path = (source_path.parent / row["logical_path"]).resolve()
            if digest(path) != row["sha256"]:
                raise ValueError(f"hash inválido: {row['image_id']}")
            normalized = {**row, "logical_path": str(path.relative_to(ROOT))}
            previous = assets.get(row["image_id"])
            if previous and previous["sha256"] != row["sha256"]:
                raise ValueError("image_id con bytes incompatibles")
            assets[row["image_id"]] = normalized
    if set(assets) != expected or len(assets) != 511:
        raise ValueError("manifest físico no coincide con la unión congelada")
    asset_document = {"schema_version": "1.0", "contract_version": "h16-h23-selector-physical-assets-v1", "inputs": {"downloaded_manifest_sha256": digest(ART / "union-asset-manifest.json"), "historical_manifest_sha256": digest(SOURCE / "partial-existing-assets.json")}, "assets": [assets[key] for key in sorted(assets)], "summary": {"assets": 511, "new_downloads": 474, "historical_reused": 37, "total_bytes": sum(row["size_bytes"] for row in assets.values())}}
    (ART / "physical-assets.json").write_bytes(canonical_bytes(asset_document) + b"\n")
    plan = build_physical_plan(arms, assets, claims, SUPPORTED_LOCAL_MODELS)
    counts = {model: sum(row["model_key"] == model for row in plan["tasks"]) for model in SUPPORTED_LOCAL_MODELS}
    if counts["qwen3-vl-2b"] != counts["qwen3-vl-8b"] or counts["qwen3-vl-2b"] > 9613:
        raise ValueError(f"presupuesto físico inesperado: {counts}")
    (ART / "physical-task-plan.json").write_bytes(canonical_bytes(plan) + b"\n")
    print(json.dumps({"assets": asset_document["summary"], "plan": plan["summary"], "per_model": counts}, sort_keys=True))


def prior_results(model_key: str, plan: dict) -> dict:
    old = json.loads((SOURCE / f"partial-{model_key}-run-v4.json").read_text())
    tasks = {(row["image_sha256"], row["claim"]["claim_id"], row["policy_unverifiable"]): row for row in plan["tasks"] if row["model_key"] == model_key}
    output = {}
    for record in old["records"]:
        policy = record["status"] == "policy_unverifiable"
        task = tasks.get((record["image_sha256"], record["claim_id"], policy))
        if task:
            output[task["task_id"]] = record
    return output


def infer(model_key: str) -> None:
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    import transformers.tokenization_utils as tokenization_utils
    if not hasattr(tokenization_utils, "PreTrainedTokenizerBase"):
        from transformers import PreTrainedTokenizerBase
        tokenization_utils.PreTrainedTokenizerBase = PreTrainedTokenizerBase
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn

    plan = json.loads((ART / "physical-task-plan.json").read_text())
    assets_doc = json.loads((ART / "physical-assets.json").read_text())
    paths = {row["image_id"]: ROOT / row["logical_path"] for row in assets_doc["assets"]}
    model_path = MODEL_PATHS[model_key]
    for name, (size, sha) in MODEL_FILES[model_key].items():
        path = model_path / name
        if path.stat().st_size != size or digest(path) != sha:
            raise ValueError(f"peso inválido: {name}")
    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(model_path, local_files_only=True, dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa")
    model.eval()
    prefix = build_transformers_prefix_allowed_tokens_fn(processor.tokenizer, JsonSchemaParser(verdict_only_schema()))

    def execute(task):
        started = time.perf_counter()
        raw = None
        try:
            image = Image.open(paths[task["image_id"]]).convert("RGB")
            prompt = verdict_only_prompt(task["claim"])
            inputs = processor.apply_chat_template([{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}], tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt").to(model.device)
            with torch.inference_mode():
                generated = model.generate(**inputs, max_new_tokens=24, do_sample=False, prefix_allowed_tokens_fn=prefix)
            raw = processor.batch_decode(generated[:, inputs.input_ids.shape[1]:], skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
            return {"status": "valid", "verdict": parse_verdict_only(raw), "raw_output": raw, "error": None, "inference_seconds": time.perf_counter() - started}
        except Exception as error:
            return {"status": "invalid_output", "verdict": "unverifiable", "raw_output": raw, "error": str(error), "inference_seconds": time.perf_counter() - started}

    started = time.perf_counter()
    results = execute_physical_plan(plan, model_key=model_key, checkpoint_path=ART / f"{model_key}.checkpoint.jsonl", previous_results=prior_results(model_key, plan), execute=execute)
    document = {"schema_version": "1.0", "contract_version": "h16-h23-selector-physical-results-v1", "task_plan_id": plan["task_plan_id"], "model": SUPPORTED_LOCAL_MODELS[model_key], "records": [results[key] for key in sorted(results)], "resources": {"execution_seconds": time.perf_counter() - started, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}, "summary": {"tasks": len(results), "executed": sum(row["source"] == "executed" for row in results.values()), "reused": sum(row["source"] == "reused" for row in results.values()), "policy": sum(row["source"] == "policy" for row in results.values()), "invalid": sum(row["status"] == "invalid_output" for row in results.values())}}
    (ART / f"{model_key}-physical-results.json").write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps(document["summary"], sort_keys=True))


def freeze() -> None:
    fixture, arms, claims = load_inputs()
    plan = json.loads((ART / "physical-task-plan.json").read_text())
    projected = {}
    for model_key in ("qwen3-vl-2b", "qwen3-vl-8b"):
        document = json.loads((ART / f"{model_key}-physical-results.json").read_text())
        results = {row["physical_task_id"]: row for row in document["records"]}
        for arm in arms:
            projected[(arm, model_key)] = project_results(plan, results, arm=arm, model_key=model_key)
    frozen = freeze_arm_rankings(fixture_queries=fixture["queries"], arm_manifests=arms, claims_by_query=claims, projected=projected, policy=freeze_symmetric_policy(), output_path=ART / "frozen-rankings.json", synthetic_fixture=False)
    print(json.dumps({"ranking_set_id": frozen["ranking_set_id"]}, sort_keys=True))


def evaluate() -> None:
    frozen_path = ART / "frozen-rankings.json"
    frozen = json.loads(frozen_path.read_text())
    dataset_path = ROOT / "results/generated/f5/h11-h25-independent/dataset.json"
    dataset = json.loads(dataset_path.read_text())
    refs = {row["query_id"]: row["reference"] for row in dataset["observations"] if row["query_id"] in {"H16", "H23"}}
    models = {}
    for model_key, arms in frozen["models"].items():
        models[model_key] = {}
        for arm, queries in arms.items():
            rows = []
            for query in queries:
                reference = refs[query["query_id"]]
                base = query["reranking"]["baseline_results"]
                by_id = {row["candidate_id"]: row for row in base}
                reference_xy = wgs84_to_epsg25830(reference["latitude"], reference["longitude"])
                def metrics(ids):
                    distances = []
                    for candidate_id in ids:
                        xy = wgs84_to_epsg25830(by_id[candidate_id]["latitude"], by_id[candidate_id]["longitude"])
                        distances.append(((xy[0] - reference_xy[0]) ** 2 + (xy[1] - reference_xy[1]) ** 2) ** 0.5)
                    return {"top1_distance_m": distances[0], "geo_recall": {str(t): {str(k): min(distances[:k]) <= t for k in (1, 5, 10)} for t in (50, 100)}}
                rows.append({"query_id": query["query_id"], "baseline": metrics([row["candidate_id"] for row in base[:10]]), "experimental": metrics(query["reranking"]["final_top10_candidate_ids"]), "rank_changes": query["reranking"]["rank_changes"]})
            models[model_key][arm] = {"rows": rows, "aggregate": {"mean_top1_distance_m": {"baseline": statistics.fmean(row["baseline"]["top1_distance_m"] for row in rows), "experimental": statistics.fmean(row["experimental"]["top1_distance_m"] for row in rows)}, "geo_recall": {str(t): {str(k): {"baseline_hits": sum(row["baseline"]["geo_recall"][str(t)][str(k)] for row in rows), "experimental_hits": sum(row["experimental"]["geo_recall"][str(t)][str(k)] for row in rows), "total": len(rows)} for k in (1, 5, 10)} for t in (50, 100)}}}
    document = {"schema_version": "1.0", "contract_version": "h16-h23-selector-geographic-evaluation-v1", "inputs": {"frozen_rankings_sha256": digest(frozen_path), "dataset_sha256": digest(dataset_path)}, "protocol": {"references_loaded_only_after_ranking_freeze": True, "distance_crs": "EPSG:25830"}, "models": models, "limitations": ["two_retrospectively_selected_development_queries", "reference_coordinate_uncertainty_unknown", "h16_interior_exterior_domain_mismatch", "no_statistical_generalization"]}
    (ART / "geographic-evaluation.json").write_bytes(canonical_bytes(document) + b"\n")
    print(json.dumps({model: {arm: value["aggregate"] for arm, value in arms.items()} for model, arms in models.items()}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "infer-2b", "infer-8b", "freeze", "evaluate"))
    args = parser.parse_args()
    {"prepare": prepare, "infer-2b": lambda: infer("qwen3-vl-2b"), "infer-8b": lambda: infer("qwen3-vl-8b"), "freeze": freeze, "evaluate": evaluate}[args.stage]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
