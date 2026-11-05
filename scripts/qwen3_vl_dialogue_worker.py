#!/usr/bin/env python3
"""Worker Qwen3-VL aislado: una petición, una imagen allowlisted, una inferencia."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json, cuda_memory, digest, system_memory, utc_now, verify_model
from src.tfg_phase0.dialogue_visual_evidence import parse_qwen3_vl_dialogue_output
from src.tfg_phase0.fail_closed_lmfe import build_fail_closed_transformers_prefix
from src.tfg_phase0.visual_reranking import compact_atomic_verdict_schema


class WorkerTimeout(TimeoutError): pass


DIAGNOSTIC_OUTPUT_LIMIT = 8192


@contextmanager
def deadline(seconds: int, stage: str):
    def handler(signum, frame): raise WorkerTimeout(f"{stage}_timeout")
    previous = signal.signal(signal.SIGALRM, handler); signal.alarm(seconds)
    try: yield
    finally: signal.alarm(0); signal.signal(signal.SIGALRM, previous)


def validate_request(document: dict, schema_path: Path, authorized_root: Path = Path("/authorized-images")) -> Path:
    schema = json.loads(schema_path.read_text(encoding="utf-8")); errors = list(Draft202012Validator(schema).iter_errors(document))
    if errors: raise ValueError("worker request inválida: " + errors[0].message)
    payload={key:value for key,value in document.items() if key!="request_id"};expected="visual-worker-request-sha256-"+hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if document["request_id"]!=expected:raise ValueError("request_id no corresponde al contenido")
    declared=Path(document["image"]["path"])
    if declared.parent != Path("/authorized-images") or declared.name != declared.as_posix().split("/")[-1]: raise ValueError("ruta visual fuera de allowlist")
    image_path=authorized_root/declared.name
    if not image_path.is_file() or digest(image_path) != document["image"]["sha256"]: raise ValueError("imagen ausente o hash inválido")
    if not document["image"]["provenance"].get("source"): raise ValueError("procedencia ausente")
    return image_path


def persist_generation_diagnostic(*, output_root: Path, raw: str, output_tokens: int, max_new_tokens: int, inference_ms: float, decode_ms: float, eos_reached: bool, lmfe_metrics: dict | None = None) -> dict:
    schema=compact_atomic_verdict_schema();syntax_valid=False;schema_valid=False;contract_valid=False;error=None;parsed=None
    try:
        parsed=json.loads(raw);syntax_valid=True
        schema_errors=list(Draft202012Validator(schema).iter_errors(parsed));schema_valid=not schema_errors
        if schema_errors:error="schema: "+schema_errors[0].message
        else:parse_qwen3_vl_dialogue_output(raw);contract_valid=True
    except Exception as exception:error=f"{type(exception).__name__}: {exception}"
    termination_reason="eos" if eos_reached else "max_new_tokens" if output_tokens>=max_new_tokens else "other"
    document={"schema_version":"1.0","contract_version":"dialogue-visual-generation-diagnostic-v1","scope":"synthetic_fixture_only","raw_output":raw[:DIAGNOSTIC_OUTPUT_LIMIT],"raw_output_truncated_for_persistence":len(raw)>DIAGNOSTIC_OUTPUT_LIMIT,"raw_output_sha256":hashlib.sha256(raw.encode()).hexdigest(),"output_tokens":output_tokens,"max_new_tokens":max_new_tokens,"termination_reason":termination_reason,"latencies_ms":{"inference":inference_ms,"decode":decode_ms},"lmfe":{"enabled":True,"adapter":"fail_closed_incremental_decoded_prefix_v2","eos_requires_complete_document":True,"metrics":lmfe_metrics or "NOT_AVAILABLE"},"validation":{"json_syntax":syntax_valid,"json_schema":schema_valid,"semantic_contract":contract_valid,"error":error}}
    path=output_root/"generation-diagnostic.json";previous_umask=os.umask(0o177)
    try:atomic_write_json(path,document)
    finally:os.umask(previous_umask)
    return document


def generate_with_constraints(*, model, inputs, max_new_tokens: int, prefix_allowed_tokens_fn):
    return model.generate(**inputs,max_new_tokens=max_new_tokens,do_sample=False,prefix_allowed_tokens_fn=prefix_allowed_tokens_fn)


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--request",type=Path,required=True);parser.add_argument("--output-root",type=Path,required=True);parser.add_argument("--schema",type=Path,default=ROOT/"schemas/dialogue_visual_worker_request.schema.json");parser.add_argument("--authorized-root",type=Path,default=Path("/authorized-images"));parser.add_argument("--validate-only",action="store_true");args=parser.parse_args()
    request=json.loads(args.request.read_text(encoding="utf-8"));image_path=validate_request(request,args.schema,args.authorized_root)
    args.output_root.mkdir(parents=True,exist_ok=True);atomic_write_json(args.output_root/"request.validated.json",request)
    if args.validate_only:return 0
    import torch
    from PIL import Image
    from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
    model=processor=inputs=generated=prefix=None;started=time.perf_counter();completed="validated"
    try:
        identity=verify_model(Path(request["model"]["model_path"]));atomic_write_json(args.output_root/"model.identity.json",identity)
        with deadline(request["timeouts"]["load_seconds"],"load"):
            load=time.perf_counter();processor=AutoProcessor.from_pretrained(request["model"]["model_path"],local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(request["model"]["model_path"],local_files_only=True,dtype=torch.bfloat16,device_map="cuda",attn_implementation="sdpa");model.eval();torch.cuda.synchronize();load_ms=(time.perf_counter()-load)*1000
        completed="loaded";atomic_write_json(args.output_root/"loaded.json",{"recorded_at_utc":utc_now(),"load_ms":load_ms,"cuda":cuda_memory(torch),"system":system_memory()})
        claim=request["claim"];prompt=("Clasifica una afirmación usando solo esta imagen. supported requiere evidencia visible específica. contradicted requiere evidencia explícitamente incompatible; la ausencia nunca contradice. unverifiable ante duda. Devuelve JSON estricto con verdict, observed_evidence, ocr_text y limitations. observed_evidence debe ser una observación breve de máximo 120 caracteres, sin explicación. " f"Afirmación: {json.dumps(claim['value'],ensure_ascii=False)}. Texto fuente: {json.dumps(claim['source_text'],ensure_ascii=False)}.")
        if digest(image_path)!=request["image"]["sha256"]:raise ValueError("imagen alterada antes de inferencia")
        image=Image.open(image_path).convert("RGB");messages=[{"role":"user","content":[{"type":"image","image":image},{"type":"text","text":prompt}]}];inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(model.device);eos_ids=model.generation_config.eos_token_id;eos_ids=[eos_ids] if isinstance(eos_ids,int) else list(eos_ids or [processor.tokenizer.eos_token_id]);prefix=build_fail_closed_transformers_prefix(tokenizer=processor.tokenizer,schema=compact_atomic_verdict_schema(),eos_token_ids=eos_ids)
        with deadline(request["timeouts"]["inference_seconds"],"inference"):
            infer=time.perf_counter()
            with torch.inference_mode():generated=generate_with_constraints(model=model,inputs=inputs,max_new_tokens=request["generation"]["max_new_tokens"],prefix_allowed_tokens_fn=prefix)
            torch.cuda.synchronize();infer_ms=(time.perf_counter()-infer)*1000
        completed="generated";generated_only=generated[:,inputs.input_ids.shape[1]:];decode=time.perf_counter();raw=processor.batch_decode(generated_only,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];decode_ms=(time.perf_counter()-decode)*1000;output_tokens=int(generated_only.shape[1]);last_token=int(generated_only[0,-1]) if output_tokens else None;diagnostic=persist_generation_diagnostic(output_root=args.output_root,raw=raw,output_tokens=output_tokens,max_new_tokens=request["generation"]["max_new_tokens"],inference_ms=infer_ms,decode_ms=decode_ms,eos_reached=last_token in eos_ids,lmfe_metrics=prefix.metrics_snapshot());parsed=parse_qwen3_vl_dialogue_output(raw)
        if not all(diagnostic["validation"][key] for key in ("json_syntax","json_schema","semantic_contract")):raise ValueError("validación diagnóstica divergente")
        completed="inferred";atomic_write_json(args.output_root/"response.json",{"schema_version":"1.0","contract_version":"dialogue-visual-worker-response-v1","request_id":request["request_id"],"status":"PASS","parsed_output":parsed,"input_tokens":int(inputs.input_ids.shape[1]),"output_tokens":output_tokens,"termination_reason":diagnostic["termination_reason"],"latencies_ms":{"load":load_ms,"inference":infer_ms,"decode":decode_ms,"total":(time.perf_counter()-started)*1000},"cuda":cuda_memory(torch),"system":system_memory(),"image_sha256":request["image"]["sha256"],"observer_relation":request["image"]["observer_relation"],"lmfe":diagnostic["lmfe"],"validation":diagnostic["validation"]})
        return 0
    except Exception as error:
        atomic_write_json(args.output_root/"error.json",{"schema_version":"1.0","contract_version":"dialogue-visual-worker-error-v1","completed_stage":completed,"type":type(error).__name__,"message":str(error),"automatic_retry":False,"lmfe_metrics":prefix.metrics_snapshot() if prefix is not None else "NOT_AVAILABLE"});return 1
    finally:
        if not args.validate_only:
            del generated,inputs,model,processor
            import gc;gc.collect();torch.cuda.empty_cache();torch.cuda.synchronize();atomic_write_json(args.output_root/"release.json",{"recorded_at_utc":utc_now(),"cuda":cuda_memory(torch),"system":system_memory()})


if __name__=="__main__":raise SystemExit(main())
