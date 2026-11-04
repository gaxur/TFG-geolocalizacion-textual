#!/usr/bin/env python3
"""Top-100 8B incremental: reutiliza tareas físicas Top-50 exactas."""
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.selector_e2e import build_physical_plan,execute_physical_plan
from src.tfg_phase0.visual_reranking import parse_verdict_only,verdict_only_prompt,verdict_only_schema
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS
ART=ROOT/"results/generated/mapillary/h26-h37-calibration-v1";MODEL_PATH=Path("/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8")
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  while c:=f.read(8*1024*1024):h.update(c)
 return h.hexdigest()
def prepare():
 plan=json.load(open(ART/"visual-plan-top100.filtered.json"));assets_doc=json.load(open(ART/"candidate-assets-top100.json"));asset_rows={r["image_id"]:r for r in assets_doc["assets"] if r["image_id"] in set(plan["asset_ids"])};assets={}
 for image_id,row in asset_rows.items():
  path=(ART/row["logical_path"]).resolve()
  if digest(path)!=row["sha256"]:raise ValueError("asset Top-100 inválido")
  assets[image_id]={**row,"logical_path":str(path.relative_to(ROOT))}
 claims={q["query_id"]:q["claims"] for q in plan["queries"]};physical=build_physical_plan({"top100":{"associations":plan["associations"]}},assets,claims,{"qwen3-vl-8b":SUPPORTED_LOCAL_MODELS["qwen3-vl-8b"]});old=json.load(open(ART/"qwen3-vl-8b-claims-results.json"));old_index={r["physical_task_id"]:r for r in old["records"]};tasks=[r for r in physical["tasks"] if r["model_key"]=="qwen3-vl-8b"]
 doc={"schema_version":"1.0","contract_version":"h26-h37-top100-8b-physical-plan-v1","physical_plan":physical,"assets":[assets[k] for k in sorted(assets)],"previous_results":{k:v for k,v in old_index.items() if k in {r["task_id"] for r in tasks}},"summary":{"assets":len(assets),"physical_tasks":len(tasks),"reusable":sum(r["task_id"] in old_index for r in tasks),"new_generate":sum(not r["policy_unverifiable"] and r["task_id"] not in old_index for r in tasks),"new_policy":sum(r["policy_unverifiable"] and r["task_id"] not in old_index for r in tasks)}};finalize_json_atomic(output_path=ART/"top100-8b-physical-plan.json",document=doc);print(json.dumps(doc["summary"],sort_keys=True))
def infer():
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,"PreTrainedTokenizerBase"):
  from transformers import PreTrainedTokenizerBase;tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 from lmformatenforcer import JsonSchemaParser
 from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
 doc=json.load(open(ART/"top100-8b-physical-plan.json"));plan=doc["physical_plan"];previous=doc["previous_results"];paths={r["image_id"]:ROOT/r["logical_path"] for r in doc["assets"]};processor=AutoProcessor.from_pretrained(MODEL_PATH,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(MODEL_PATH,local_files_only=True,dtype=torch.bfloat16,device_map="cuda",attn_implementation="sdpa");model.eval();prefix=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(verdict_only_schema()))
 def execute(task):
  begin=time.perf_counter();image=Image.open(paths[task["image_id"]]).convert("RGB");prompt=verdict_only_prompt(task["claim"]);values=processor.apply_chat_template([{"role":"user","content":[{"type":"image","image":image},{"type":"text","text":prompt}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(model.device)
  with torch.inference_mode():generated=model.generate(**values,max_new_tokens=24,do_sample=False,prefix_allowed_tokens_fn=prefix)
  raw=processor.batch_decode(generated[:,values.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];return {"status":"valid","verdict":parse_verdict_only(raw),"raw_output":raw,"error":None,"inference_seconds":time.perf_counter()-begin}
 begin=time.perf_counter();results=execute_physical_plan(plan,model_key="qwen3-vl-8b",checkpoint_path=ART/"qwen3-vl-8b-top100.checkpoint.jsonl",previous_results=previous,execute=execute);output={"schema_version":"1.0","contract_version":"h26-h37-top100-8b-results-v1","task_plan_id":plan["task_plan_id"],"records":[results[k] for k in sorted(results)],"summary":{"tasks":len(results),"executed_new":sum(r["source"]=="executed" for r in results.values()),"reused":sum(r["source"]=="reused" for r in results.values()),"policy_new":sum(r["source"]=="policy" for r in results.values()),"verdicts":{v:sum(r["verdict"]==v for r in results.values()) for v in ("supported","contradicted","unverifiable")}},"resources":{"execution_seconds":time.perf_counter()-begin,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}};finalize_json_atomic(output_path=ART/"qwen3-vl-8b-top100-results.json",document=output);print(json.dumps(output["summary"],sort_keys=True))
def main():
 p=argparse.ArgumentParser();p.add_argument("stage",choices=("prepare","infer"));{"prepare":prepare,"infer":infer}[p.parse_args().stage]();return 0
if __name__=="__main__":raise SystemExit(main())
