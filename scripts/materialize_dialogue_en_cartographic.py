#!/usr/bin/env python3
"""Prepara o materializa E0-E3 sin acceso a rankings, GT, Mapillary o VLM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.dialogue_en_cartographic import (
    DialogueEnCartographicError,
    materialize_with_transformer,
    prepare_query_bundle,
    sha256_file,
)
from src.tfg_phase0.f5_text_transform import FakeTransformer, TransformResult, hash_tree_manifest


def _write(path: Path, document) -> None:
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno())


def _publish(root: Path, documents: dict[str, object]) -> None:
    if root.exists():
        raise DialogueEnCartographicError("output-root ya existe")
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = root.with_name(f".{root.name}.stage-{os.getpid()}")
    if stage.exists():shutil.rmtree(stage)
    try:
        stage.mkdir()
        for name, document in documents.items():_write(stage / name, document)
        manifest = {"schema_version":"1.0","contract_version":"dialogue-v3-en-cartographic-materialization-manifest-v1","status":"committed","files":{name:sha256_file(stage/name) for name in sorted(documents)}}
        _write(stage / "manifest.json", manifest)
        os.replace(stage, root)
    except Exception:
        if stage.exists():shutil.rmtree(stage)
        raise


class SequentialFakeTransformer:
    def __init__(self, outputs: dict[str, str]):self.outputs=outputs;self.calls=[]
    def generate_prompt(self, prompt, config):
        round_id=f"E{len(self.calls)}";self.calls.append(round_id);text=self.outputs[round_id];return TransformResult(text,text,0.0)


def _authorization(path: Path, plan_root: Path, model_path: Path) -> dict:
    document=json.loads(path.read_text())
    expected={"schema_version","contract_version","status","stage","approved","gpu_authorized","model_id","model_revision","model_snapshot_sha256","plan_sha256","contract_sha256","prompt_sha256","maximum_model_loads","maximum_calls","automatic_retries","stable_swap_required","output_root","authorization_source"}
    if set(document)!=expected or document["contract_version"]!="dialogue-v3-en-cartographic-qwen-authorization-v1" or document["status"]!="OPERATOR_AUTHORIZED" or document["approved"] is not True or document["gpu_authorized"] is not True or document["stage"]!="query_generation":raise DialogueEnCartographicError("autorización Qwen ausente o incompatible")
    if document["model_id"]!="Qwen/Qwen3-8B" or document["model_revision"]!="b968826d9c46dd6066d109eabc6255188de91218" or document["maximum_model_loads"]!=1 or document["maximum_calls"]!=4 or document["automatic_retries"]!=0 or document["stable_swap_required"] is not True:raise DialogueEnCartographicError("límites Qwen incompatibles")
    if document["plan_sha256"]!=sha256_file(plan_root/"experiment-plan.json") or document["contract_sha256"]!=sha256_file(plan_root/"query-construction-contract.json") or document["prompt_sha256"]!="91c620bf3f255912e7dfdd1a524a728f9ce48f31180f9c4ca15bb3f3967de64c":raise DialogueEnCartographicError("hashes de autorización divergentes")
    actual=hash_tree_manifest(model_path)
    if actual!=document["model_snapshot_sha256"]:raise DialogueEnCartographicError("snapshot Qwen divergente")
    return document


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--plan-root",type=Path,required=True);parser.add_argument("--output-root",type=Path,required=True);parser.add_argument("--mode",choices=("prepare","fake","real"),default="prepare");parser.add_argument("--fake-outputs",type=Path);parser.add_argument("--authorization",type=Path);parser.add_argument("--model-path",type=Path);args=parser.parse_args()
    plan=args.plan_root.resolve();output=args.output_root.resolve();prepared=prepare_query_bundle(plan)
    if args.mode=="prepare":bundle=prepared
    elif args.mode=="fake":
        if args.fake_outputs is None:raise DialogueEnCartographicError("fake requiere --fake-outputs")
        bundle=materialize_with_transformer(prepared,SequentialFakeTransformer(json.loads(args.fake_outputs.read_text())),synthetic_fixture=True)
    else:
        if args.authorization is None or args.model_path is None:raise DialogueEnCartographicError("real requiere autorización y model-path")
        authorization=_authorization(args.authorization.resolve(),plan,args.model_path.resolve())
        if Path(authorization["output_root"]).resolve()!=output:raise DialogueEnCartographicError("output-root no autorizado")
        from scripts.run_dialogue_v3_visual_worker_smoke import STABLE_SWAP_INTERVAL_SECONDS,STABLE_SWAP_SAMPLES,collect_stable_swap_samples,evaluate_memory_gate
        from scripts.run_qwen3_vl_8b_memory_smoke import compute_processes
        ollama=subprocess.run(["ollama","ps"],capture_output=True,text=True,timeout=10);ollama_status="no_model_resident" if ollama.returncode==0 and len(ollama.stdout.splitlines())<=1 else "model_resident_or_unverified";samples=collect_stable_swap_samples(count=STABLE_SWAP_SAMPLES,interval_seconds=STABLE_SWAP_INTERVAL_SECONDS);gate=evaluate_memory_gate(policy="stable-swap",host_compute_process_count=len(compute_processes()),host_ollama_status=ollama_status,samples=samples)
        if not gate["passed"]:raise DialogueEnCartographicError("stable-swap-v1 bloquea Qwen: "+",".join(gate["blocking_reasons"]))
        # Import/construcción tardíos: este punto es posterior a autorización e identidad del snapshot.
        from src.tfg_phase0.f5_text_transform import QwenTransformersAdapter
        transformer=QwenTransformersAdapter(args.model_path.resolve(),model_id=authorization["model_id"],revision=authorization["model_revision"])
        try:bundle=materialize_with_transformer(prepared,transformer,synthetic_fixture=False)
        finally:transformer.close()
    preflight={"schema_version":"1.0","contract_version":"dialogue-v3-en-cartographic-materialization-preflight-v1","status":"PASS","mode":args.mode,"plan_root":str(plan),"plan_sha256":sha256_file(plan/"experiment-plan.json"),"contract_sha256":sha256_file(plan/"query-construction-contract.json"),"models_loaded":args.mode=="real","real_model_inference":args.mode=="real","automatic_retries":0,"stable_swap_enforced":args.mode=="real"}
    _publish(output,{"queries.json":bundle,"preflight.json":preflight})
    print(json.dumps({"status":bundle["status"],"output":str(output),"mode":args.mode},sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
