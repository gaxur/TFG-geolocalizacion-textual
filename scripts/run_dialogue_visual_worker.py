#!/usr/bin/env python3
"""Ejecutor externo del worker visual real para DialogueVPR v3."""
from __future__ import annotations
import json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from jsonschema import Draft202012Validator
from scripts.run_dialogue_v3_visual_worker_smoke import STABLE_SWAP_INTERVAL_SECONDS,STABLE_SWAP_SAMPLES,collect_stable_swap_samples,evaluate_memory_gate,request_id,run_supervised
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json,compute_processes,utc_now
from src.tfg_phase0.dialogue_visual_evidence import VisualImageReference,parse_qwen3_vl_dialogue_output
from src.tfg_phase0.visual_reranking import compact_atomic_verdict_schema

class ExternalVisualWorkerError(RuntimeError):pass

def ollama_is_empty():
    result=subprocess.run(["ollama","ps"],capture_output=True,text=True,timeout=10)
    return result.returncode==0 and len(result.stdout.splitlines())<=1

class ExternalQwen3VLWorkerExecutor:
    EXPECTED_IMAGE="qwen3-vl-dialogue-worker:lmfe-0.11.3-tf5.9-v1";EXPECTED_IMAGE_ID="sha256:4ed13751602503ee412fc854e4c33bee0ae172df67690d5420e32650bae2edd2"
    def __init__(self,*,output_root:Path,model_dir:Path,docker_image:str,total_timeout:int=240):self.output_root=output_root;self.model_dir=model_dir;self.docker_image=docker_image;self.total_timeout=total_timeout;self.calls=0
    def verify_runtime(self):
        if self.docker_image!=self.EXPECTED_IMAGE or not self.model_dir.is_dir():raise ExternalVisualWorkerError("runtime visual no autorizado o ausente")
        result=subprocess.run(["docker","image","inspect",self.docker_image,"--format","{{.Id}}"],capture_output=True,text=True,timeout=10)
        if result.returncode or result.stdout.strip()!=self.EXPECTED_IMAGE_ID:raise ExternalVisualWorkerError("digest Docker visual divergente")
    def __call__(self,dialogue_request,reference:VisualImageReference):
        if self.calls:raise ExternalVisualWorkerError("el ejecutor permite una única inferencia")
        self.verify_runtime();self.calls+=1;run_root=self.output_root;run_root.mkdir(parents=True,exist_ok=False);worker_out=run_root/"worker";worker_out.mkdir()
        samples=collect_stable_swap_samples(count=STABLE_SWAP_SAMPLES,interval_seconds=STABLE_SWAP_INTERVAL_SECONDS);ollama="no_model_resident" if ollama_is_empty() else "model_resident_or_unverified";gate=evaluate_memory_gate(policy="stable-swap",host_compute_process_count=len(compute_processes()),host_ollama_status=ollama,samples=samples);atomic_write_json(run_root/"memory-samples.json",{"schema_version":"1.0","contract_version":"dialogue-visual-memory-samples-v1","memory_policy":"stable-swap","samples":samples});atomic_write_json(run_root/"preflight.json",{"recorded_at_utc":utc_now(),"ollama":ollama,"gate":gate})
        if not gate["passed"]:raise ExternalVisualWorkerError("preflight visual bloqueado: "+",".join(gate["blocking_reasons"]))
        claim=dialogue_request["claim"];document={"schema_version":"1.0","contract_version":"dialogue-visual-worker-request-v2","model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":"0c351dd01ed87e9c1b53cbc748cba10e6187ff3b","model_path":"/models/Qwen3-VL-8B"},"image":{"image_id":reference.image_id,"path":"/authorized-images/"+reference.path.name,"sha256":reference.sha256,"provenance":dict(reference.provenance),"authorized":True,"authorization_id":reference.authorization_id,"observer_relation":"observer_view"},"claim":{"claim_id":claim["claim_id"],"kind":"object_presence","value":claim["value"],"source_text":dialogue_request["intent"]["label"]},"generation":{"dtype":"bfloat16","attention":"sdpa","do_sample":False,"max_new_tokens":192},"timeouts":{"load_seconds":150,"inference_seconds":30,"total_seconds":self.total_timeout},"protocol":{"ground_truth_used":False,"reserved_sets_used":False,"network_used":False,"single_inference":True}};document["request_id"]=request_id(document);atomic_write_json(run_root/"request.json",document)
        project=ROOT.resolve();request_inside="/workspace/project/"+str((run_root/"request.json").resolve().relative_to(project));output_inside="/workspace/project/"+str(worker_out.resolve().relative_to(project));command=["docker","run","--rm","--gpus","all","--network","none","--ipc=host","--ulimit","memlock=-1","--ulimit","stack=67108864","-e","CUDA_VISIBLE_DEVICES=0","-e","HOME=/root","-e","HF_HOME=/tmp/huggingface","-v",f"{project}:/workspace/project","-v",f"{self.model_dir.resolve()}:/models/Qwen3-VL-8B:ro","-v",f"{reference.path.parent.resolve()}:/authorized-images:ro","-w","/workspace/project",self.docker_image,"python","scripts/qwen3_vl_dialogue_worker.py","--request",request_inside,"--output-root",output_inside]
        result=run_supervised(command,self.total_timeout,run_root);response_path=worker_out/"response.json"
        if result["returncode"] or result["timed_out"] or not response_path.is_file():raise ExternalVisualWorkerError("worker visual falló")
        response=json.loads(response_path.read_text());parsed=response.get("parsed_output");Draft202012Validator(compact_atomic_verdict_schema()).validate(parsed);parse_qwen3_vl_dialogue_output(json.dumps(parsed,ensure_ascii=False));return {"status":"PASS","parsed_output":parsed}
