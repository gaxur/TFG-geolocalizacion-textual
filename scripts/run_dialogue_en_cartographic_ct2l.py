#!/usr/bin/env python3
"""Recupera E0-E3 exhaustivamente; el modo real exige autorización inmutable."""

from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.dialogue_en_cartographic import DialogueEnCartographicError,retrieve_query_bundle,sha256_file

class FakeRetriever:
    gallery_id="madrid-50m";gallery_count=253
    def __init__(self):self.calls=[]
    def retrieve_full(self,*,query_id,text,language):
        self.calls.append((query_id,text,language));rows=[{"rank":i+1,"candidate_id":f"fixture-{i:03d}","latitude":40.0+i/10000,"longitude":-3.0,"cosine_similarity":1-i/1000} for i in range(253)];return {"gallery_id":self.gallery_id,"gallery_count":253,"requested_k":253,"effective_k":253,"ranking_method":"exhaustive_cosine","tie_break":"candidate_id_ascending","results":rows}

def _authorization(path,queries,clip_audit,session_config,output):
    d=json.loads(path.read_text());required={"schema_version","contract_version","status","stage","approved","gpu_authorized","queries_sha256","clip_audit_sha256","session_config_sha256","checkpoint_sha256","embedding_dataset_id","gallery_id","candidate_count","maximum_model_loads","maximum_calls","automatic_retries","stable_swap_required","output","authorization_source"}
    if set(d)!=required or d["contract_version"]!="dialogue-v3-en-cartographic-ct2l-authorization-v1" or d["status"]!="OPERATOR_AUTHORIZED" or d["stage"]!="ct2l_retrieval" or d["approved"] is not True or d["gpu_authorized"] is not True:raise DialogueEnCartographicError("autorización CT2L incompatible")
    expected=("d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d","f4-madrid-embeddings-sha256-199dae0e3eb38b206004557f20fae0ef98f620621458fc64c2dfa3f7ef7f84c1","madrid-50m",253,1,4,0,True)
    actual=(d["checkpoint_sha256"],d["embedding_dataset_id"],d["gallery_id"],d["candidate_count"],d["maximum_model_loads"],d["maximum_calls"],d["automatic_retries"],d["stable_swap_required"])
    if actual!=expected or d["queries_sha256"]!=sha256_file(queries) or d["clip_audit_sha256"]!=sha256_file(clip_audit) or d["session_config_sha256"]!=sha256_file(session_config) or Path(d["output"]).resolve()!=output.resolve():raise DialogueEnCartographicError("límites o hashes CT2L divergentes")
    return d

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--queries",type=Path,required=True);p.add_argument("--clip-audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--mode",choices=("fake","real"),required=True);p.add_argument("--authorization",type=Path);p.add_argument("--session-config",type=Path);p.add_argument("--runtime-config",type=Path,default=ROOT/"config/madrid_f46_retriever.json");a=p.parse_args();bundle=json.loads(a.queries.read_text());audit=json.loads(a.clip_audit.read_text())
    if a.mode=="fake":retriever=FakeRetriever();result=retrieve_query_bundle(bundle,retriever,audit,real_model_inference=False)
    else:
        if a.authorization is None or a.session_config is None:raise DialogueEnCartographicError("modo real requiere autorización y session-config")
        session_config=a.session_config.resolve();_authorization(a.authorization,a.queries,a.clip_audit,session_config,a.output)
        # Imports y carga tardíos: solo después de autorización y hashes.
        from scripts.run_dialogue_v3_visual_worker_smoke import STABLE_SWAP_INTERVAL_SECONDS,STABLE_SWAP_SAMPLES,collect_stable_swap_samples,evaluate_memory_gate
        from scripts.run_qwen3_vl_8b_memory_smoke import compute_processes
        from src.tfg_phase0.ct2l_isolated_environment import validate_ct2l_environment
        environment=validate_ct2l_environment(ROOT/"config/ct2l_isolated_runtime_cvgtext.json",ROOT,session_config=session_config)
        if Path(sys.executable).resolve()!=Path(environment["python_entrypoint"]).resolve():raise DialogueEnCartographicError("runner real debe ejecutarse con .venv-cvgtext")
        ollama=subprocess.run(["ollama","ps"],capture_output=True,text=True,timeout=10);ollama_status="no_model_resident" if ollama.returncode==0 and len(ollama.stdout.splitlines())<=1 else "model_resident_or_unverified";samples=collect_stable_swap_samples(count=STABLE_SWAP_SAMPLES,interval_seconds=STABLE_SWAP_INTERVAL_SECONDS);gate=evaluate_memory_gate(policy="stable-swap",host_compute_process_count=len(compute_processes()),host_ollama_status=ollama_status,samples=samples)
        if not gate["passed"]:raise DialogueEnCartographicError("stable-swap-v1 bloquea CT2L: "+",".join(gate["blocking_reasons"]))
        from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
        from src.tfg_phase0.interactive_dialogue import ResidentCT2LAdapter
        config=json.loads(session_config.read_text());model,galleries=load_runtime_config(a.runtime_config,project_root=ROOT,cvg_utils_sha256=config["cvg_utils_sha256"],clip_weights_path=Path(config["clip_weights"]));gallery=[g for g in galleries if g.gallery_id=="madrid-50m"]
        if len(gallery)!=1:raise DialogueEnCartographicError("galería madrid-50m ausente")
        runtime=CrossText2LocRetriever.load(model_config=model,gallery_configs=gallery,region_config=ROOT/config["region_config"],deep_validate_visual_assets=False)
        try:
            adapter=ResidentCT2LAdapter(runtime,"madrid-50m")
            class Wrapper:
                gallery_id="madrid-50m";gallery_count=253
                def retrieve_full(self,**kwargs):return adapter.retrieve_full(**kwargs)
            result=retrieve_query_bundle(bundle,Wrapper(),audit,real_model_inference=True)
        finally:runtime.close()
    finalize_json_atomic(output_path=a.output,document=result);print(json.dumps({"status":result["status"],"output":str(a.output)}));return 0
if __name__=="__main__":raise SystemExit(main())
