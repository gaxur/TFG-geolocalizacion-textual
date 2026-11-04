#!/usr/bin/env python3
"""Plan físico, inferencia 8B y rankings de calibración H26-H37."""
from __future__ import annotations
import argparse,hashlib,json,resource,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.discriminative_visual_reranking import aggregate_discriminative_evidence,apply_discriminative_reranking,freeze_discriminative_policy
from src.tfg_phase0.selector_e2e import build_physical_plan,execute_physical_plan,project_results
from src.tfg_phase0.symmetric_visual_reranking import apply_symmetric_reranking,freeze_symmetric_policy
from src.tfg_phase0.visual_reranking import aggregate_candidate_evidence,parse_verdict_only,verdict_only_prompt,verdict_only_schema
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS
ART=ROOT/"results/generated/mapillary/h26-h37-calibration-v1";MODEL_PATH=Path("/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8")
FILES={"model-00001-of-00004.safetensors":(4902275944,"d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa"),"model-00002-of-00004.safetensors":(4915962496,"8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5"),"model-00003-of-00004.safetensors":(4999831048,"83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192"),"model-00004-of-00004.safetensors":(2716270024,"0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5")}
BETAS=(0.1,0.2,0.35,0.5)
def digest(path):
 v=hashlib.sha256()
 with path.open("rb") as f:
  while c:=f.read(8*1024*1024):v.update(c)
 return v.hexdigest()
def inputs():
 plan=json.loads((ART/"visual-plan-top50.filtered.json").read_text());rankings=json.loads((ART/"ct2l-top100.json").read_text());assets=json.loads((ART/"candidate-assets-top50.json").read_text());return plan,rankings,assets
def prepare():
 plan,rankings,assets_doc=inputs();asset_rows={r["image_id"]:r for r in assets_doc["assets"] if r["image_id"] in set(plan["asset_ids"])};assets={}
 for image_id,row in asset_rows.items():
  path=(ART/row["logical_path"]).resolve()
  if digest(path)!=row["sha256"]:raise ValueError(f"asset inválido {image_id}")
  assets[image_id]={**row,"logical_path":str(path.relative_to(ROOT))}
 if set(assets)!=set(plan["asset_ids"]):raise ValueError("assets filtrados incompletos")
 claims={q["query_id"]:q["claims"] for q in plan["queries"]};arm={"calibration_top50":{"associations":plan["associations"]}};models={"qwen3-vl-8b":SUPPORTED_LOCAL_MODELS["qwen3-vl-8b"]};physical=build_physical_plan(arm,assets,claims,models);tasks=[r for r in physical["tasks"] if r["model_key"]=="qwen3-vl-8b"]
 document={"schema_version":"1.0","contract_version":"h26-h37-8b-physical-plan-v1","source_plan_id":plan["plan_id"],"source_plan_sha256":digest(ART/"visual-plan-top50.filtered.json"),"physical_plan":physical,"assets":[assets[k] for k in sorted(assets)],"summary":{"assets":len(assets),"logical_jobs":physical["summary"]["logical_jobs"],"physical_tasks":len(tasks),"generate_calls":sum(not r["policy_unverifiable"] for r in tasks),"automatic_abstentions":sum(r["policy_unverifiable"] for r in tasks),"estimated_seconds":sum(not r["policy_unverifiable"] for r in tasks)*1.922200057920001}}
 finalize_json_atomic(output_path=ART/"8b-physical-plan.json",document=document);print(json.dumps(document["summary"],sort_keys=True))
def infer():
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,"PreTrainedTokenizerBase"):
  from transformers import PreTrainedTokenizerBase;tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 from lmformatenforcer import JsonSchemaParser
 from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
 document=json.loads((ART/"8b-physical-plan.json").read_text());plan=document["physical_plan"];paths={r["image_id"]:ROOT/r["logical_path"] for r in document["assets"]}
 for name,(size,sha) in FILES.items():
  path=MODEL_PATH/name
  if path.stat().st_size!=size or digest(path)!=sha:raise ValueError(f"peso inválido {name}")
 processor=AutoProcessor.from_pretrained(MODEL_PATH,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(MODEL_PATH,local_files_only=True,dtype=torch.bfloat16,device_map="cuda",attn_implementation="sdpa");model.eval();prefix=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(verdict_only_schema()))
 def execute(task):
  begin=time.perf_counter();raw=None
  try:
   image=Image.open(paths[task["image_id"]]).convert("RGB");prompt=verdict_only_prompt(task["claim"]);values=processor.apply_chat_template([{"role":"user","content":[{"type":"image","image":image},{"type":"text","text":prompt}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(model.device)
   with torch.inference_mode():generated=model.generate(**values,max_new_tokens=24,do_sample=False,prefix_allowed_tokens_fn=prefix)
   raw=processor.batch_decode(generated[:,values.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];return {"status":"valid","verdict":parse_verdict_only(raw),"raw_output":raw,"error":None,"inference_seconds":time.perf_counter()-begin}
  except Exception as error:return {"status":"invalid_output","verdict":"unverifiable","raw_output":raw,"error":str(error),"inference_seconds":time.perf_counter()-begin}
 begin=time.perf_counter();results=execute_physical_plan(plan,model_key="qwen3-vl-8b",checkpoint_path=ART/"qwen3-vl-8b-claims-v2.checkpoint.jsonl",previous_results={},execute=execute);output={"schema_version":"1.0","contract_version":"h26-h37-8b-physical-results-v2","task_plan_id":plan["task_plan_id"],"model":SUPPORTED_LOCAL_MODELS["qwen3-vl-8b"],"checkpoint_identity_fix":"execution_mode_in_job_key","records":[results[k] for k in sorted(results)],"summary":{"tasks":len(results),"executed":sum(r["source"]=="executed" for r in results.values()),"policy":sum(r["source"]=="policy" for r in results.values()),"invalid":sum(r["status"]=="invalid_output" for r in results.values()),"verdicts":{v:sum(r["verdict"]==v for r in results.values()) for v in ("supported","contradicted","unverifiable")}},"resources":{"execution_seconds":time.perf_counter()-begin,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}};finalize_json_atomic(output_path=ART/"qwen3-vl-8b-claims-results.json",document=output);print(json.dumps(output["summary"],sort_keys=True))
def freeze():
 source,rankings,_=inputs();physical_doc=json.loads((ART/"8b-physical-plan.json").read_text());physical=physical_doc["physical_plan"];run=json.loads((ART/"qwen3-vl-8b-claims-results.json").read_text());results={r["physical_task_id"]:r for r in run["records"]};projected=project_results(physical,results,arm="calibration_top50",model_key="qwen3-vl-8b");claims={q["query_id"]:q["claims"] for q in source["queries"]};rank_by={q["query_id"]:r for q,r in zip(rankings["queries"],rankings["rankings"],strict=True)};queries={}
 for query in source["queries"]:
  qid=query["query_id"];baseline=rank_by[qid]["results"][:50];associations=[r for r in source["associations"] if r["query_id"]==qid];verdicts=[r for r in projected if r["query_id"]==qid];candidate_ids=[r["candidate_id"] for r in baseline];original=aggregate_candidate_evidence(claims[qid],associations,verdicts,candidate_ids=candidate_ids);disc=aggregate_discriminative_evidence(claims[qid],associations,verdicts,candidate_ids=candidate_ids);variants={"baseline":[r["candidate_id"] for r in baseline]}
  for beta in BETAS:
   variants[f"original_beta_{beta}"]=apply_symmetric_reranking(baseline,original,freeze_symmetric_policy(positive_weight=beta))["full_experimental_order"]
   variants[f"discriminative_beta_{beta}"]=apply_discriminative_reranking(baseline,disc,freeze_discriminative_policy(positive_weight=beta))["full_experimental_order"]
  queries[qid]={"baseline_results":baseline,"original_aggregate":original,"discriminative_aggregate":disc,"variants":variants}
 output={"schema_version":"1.0","contract_version":"h26-h37-calibration-rankings-v1","ranking_set_id":"","protocol":{"ground_truth_used":False,"weights_predefined":list(BETAS),"all_variants_frozen_before_evaluation":True},"inputs":{"source_plan_sha256":digest(ART/"visual-plan-top50.filtered.json"),"physical_results_sha256":digest(ART/"qwen3-vl-8b-claims-results.json"),"ct2l_sha256":digest(ART/"ct2l-top100.json")},"queries":queries};output["ranking_set_id"]="h26-h37-calibration-rankings-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in output.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();finalize_json_atomic(output_path=ART/"calibration-rankings.frozen.json",document=output);print(json.dumps({"ranking_set_id":output["ranking_set_id"],"queries":len(queries)},sort_keys=True))
def main():
 p=argparse.ArgumentParser();p.add_argument("stage",choices=("prepare","infer","freeze"));stage=p.parse_args().stage;{"prepare":prepare,"infer":infer,"freeze":freeze}[stage]();return 0
if __name__=="__main__":raise SystemExit(main())
