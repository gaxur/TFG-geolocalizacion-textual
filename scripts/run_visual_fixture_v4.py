#!/usr/bin/env python3
"""Ejecutor Qwen3-VL V4 posterior a CT2L, sin GT ni scores en prompts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.visual_reranking import canonical_bytes, parse_verdict_only, verdict_only_prompt, verdict_only_schema
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS
from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob, finalize_json_atomic, run_resumable


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecutor VLM V4 genérico posterior a CT2L, sin GT.")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--reviewed-claims", type=Path, required=True)
    parser.add_argument("--model-key", choices=sorted(MODEL_FILES), required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    assets_document = json.loads(args.assets.read_text(encoding="utf-8"))
    review = json.loads(args.reviewed_claims.read_text(encoding="utf-8"))
    config = SUPPORTED_LOCAL_MODELS[args.model_key]
    for name, (size, sha256) in MODEL_FILES[args.model_key].items():
        path = args.model_path / name
        if path.stat().st_size != size or digest(path) != sha256:
            raise ValueError(f"peso inválido: {name}")
    if review.get("fixture_id") != fixture["fixture_id"] or review.get("review_status") != "complete":
        raise ValueError("claims revisados incompatibles")
    query_claims = {row["query_id"]: {claim["claim_id"]: claim for claim in row["claims"]["claims"]} for row in fixture.get("queries", [])}
    source = {claim["claim_id"]: claim for claim in fixture.get("claims", {}).get("claims", [])}
    if not source:
        source = {claim_id: claim for claims in query_claims.values() for claim_id, claim in claims.items()}
    seen = []
    approved = []
    approved_ids = set()
    for row in review["records"]:
        claim = row["claim"]
        if claim != source.get(claim["claim_id"]) or row["decision"] not in {"approved", "rejected"}:
            raise ValueError("decisión de claim inválida")
        seen.append(claim["claim_id"])
        if row["decision"] == "approved":
            approved.append(claim)
            approved_ids.add(claim["claim_id"])
    if len(seen) != len(set(seen)) or set(seen) != set(source):
        raise ValueError("revisión incompleta o duplicada")
    approved_by_query = {query_id: [claim for claim_id, claim in claims.items() if claim_id in approved_ids] for query_id, claims in query_claims.items()}
    assets = {row["image_id"]: row for row in assets_document["assets"] if row["status"] in {"downloaded", "reused"}}
    jobs = []
    for association in fixture["associations"]:
        asset = assets.get(association["image_id"])
        if asset is None:
            continue
        path = (args.assets.parent / asset["logical_path"]).resolve()
        if digest(path) != asset["sha256"]:
            raise ValueError("hash de imagen inválido")
        claims = approved_by_query[association["query_id"]] if query_claims else approved
        for claim in claims:
            policy = claim["requires_orientation"] and not association.get("orientation_comparable", False)
            prompt = None if policy else verdict_only_prompt(claim)
            key = (association.get("query_id"), association["candidate_id"], association["image_id"], claim["claim_id"])
            fingerprint = {"key": {"query_id": key[0], "candidate_id": key[1], "image_id": key[2], "claim_id": key[3]}, "sequence_id": association.get("sequence_id"), "orientation_comparable": association.get("orientation_comparable", False), "image_sha256": asset["sha256"], "claim_sha256": hashlib.sha256(canonical_bytes(claim)).hexdigest(), "execution_mode": "policy_unverifiable" if policy else "model", "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest() if prompt else None}
            jobs.append(PlannedJob(key, fingerprint, (association, claim, path, asset["sha256"], prompt), not policy))
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    import transformers.tokenization_utils as tokenization_utils
    if not hasattr(tokenization_utils, "PreTrainedTokenizerBase"):
        from transformers import PreTrainedTokenizerBase
        tokenization_utils.PreTrainedTokenizerBase = PreTrainedTokenizerBase
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
    checkpoint_path = args.checkpoint or args.output.with_suffix(args.output.suffix + ".checkpoint.jsonl")
    generation = {"contract": "verdict_only_v4", "schema": verdict_only_schema(), "do_sample": False, "max_new_tokens": 24, "explanations_generated": False}
    protocol = {"ground_truth_used": False, "baseline_rank_sent_to_vlm": False, "scores_sent_to_vlm": False, "coordinates_sent_to_vlm": False, "reranking_performed": False}
    model_metadata = {"model_key": args.model_key, "model_id": config["model_id"], "revision": config["revision"], "files": {name: {"size_bytes": size, "sha256": sha256} for name, (size, sha256) in MODEL_FILES[args.model_key].items()}}
    provenance = {"final_contract_version": "visual-fixture-run-v4", "fixture_id": fixture["fixture_id"], "inputs": {"fixture_sha256": digest(args.fixture), "asset_manifest_sha256": digest(args.assets), "reviewed_claims_sha256": digest(args.reviewed_claims)}, "model": model_metadata, "generation": generation, "protocol": protocol, "software": {"runner_sha256": digest(Path(__file__)), "visual_reranking_sha256": digest(ROOT / "src/tfg_phase0/visual_reranking.py"), "python": sys.version.split()[0], "torch": torch.__version__}}
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_start = time.perf_counter()
    processor = AutoProcessor.from_pretrained(args.model_path, local_files_only=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(args.model_path, local_files_only=True, dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa")
    model.eval()
    load_seconds = time.perf_counter() - load_start
    prefix = build_transformers_prefix_allowed_tokens_fn(processor.tokenizer, JsonSchemaParser(verdict_only_schema()))
    started = time.perf_counter()
    last_report = {"completed": -1}
    def progress(value):
        if value.completed == value.total or value.completed == value.recovered or value.completed - last_report["completed"] >= args.progress_every:
            last_report["completed"] = value.completed
            eta = "unknown" if value.eta_seconds is None else f"{value.eta_seconds/60:.1f}m"
            key = value.last_key or (None, "-", "-", "-")
            print(f"[{args.model_key}] {value.completed}/{value.total} recovered={value.recovered} session_generate={value.executed_this_session} query={key[0]} candidate={key[1]} image={key[2]} claim={key[3]} elapsed={value.elapsed_seconds/60:.1f}m eta={eta} mean_generate={value.mean_execution_seconds}", flush=True)
    def policy_callback(job):
        association, claim, _, image_sha256, _ = job.payload
        return {"query_id": association.get("query_id"), "candidate_id": association["candidate_id"], "image_id": association["image_id"], "claim_id": claim["claim_id"], "image_sha256": image_sha256, "sequence_id": association.get("sequence_id"), "status": "policy_unverifiable", "verdict": "unverifiable", "raw_output": None, "error": None, "inference_seconds": 0.0}
    def execute_callback(job):
        association, claim, path, image_sha256, prompt = job.payload
        base = {"query_id": association.get("query_id"), "candidate_id": association["candidate_id"], "image_id": association["image_id"], "claim_id": claim["claim_id"], "image_sha256": image_sha256, "sequence_id": association.get("sequence_id")}
        image = Image.open(path).convert("RGB")
        inputs = processor.apply_chat_template([{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}], tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt").to(model.device)
        torch.cuda.synchronize();inference_start=time.perf_counter();raw=None
        try:
            with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=24,do_sample=False,prefix_allowed_tokens_fn=prefix)
            torch.cuda.synchronize();raw=processor.batch_decode(generated[:,inputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];verdict=parse_verdict_only(raw);status,error="valid",None
        except Exception as exception:
            verdict,status,error=None,"invalid_output",str(exception)
        return {**base,"status":status,"verdict":verdict,"raw_output":raw,"error":error,"inference_seconds":time.perf_counter()-inference_start}
    try:
        records = run_resumable(checkpoint_path=checkpoint_path, provenance=provenance, jobs=jobs, execute=execute_callback, policy_result=policy_callback, on_progress=progress)
    finally:
        del model
        torch.cuda.empty_cache()
    document = {"schema_version": "1.1", "contract_version": "visual-fixture-run-v4", "fixture_id": fixture["fixture_id"], "approved_claims": approved, "inputs": provenance["inputs"], "model": model_metadata, "generation": generation, "protocol": protocol, "records": records, "resources": {"model_load_seconds": load_seconds, "execution_seconds": time.perf_counter() - started, "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(), "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(), "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}, "summary": {"jobs": len(records), "valid": sum(row["status"] == "valid" for row in records), "policy_unverifiable": sum(row["status"] == "policy_unverifiable" for row in records), "invalid": sum(row["status"] == "invalid_output" for row in records), "verdicts": {verdict: sum(row["verdict"] == verdict for row in records) for verdict in ("supported", "contradicted", "unverifiable")}}}
    finalize_json_atomic(output_path=args.output,document=document)
    print(json.dumps(document["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
