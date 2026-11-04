#!/usr/bin/env python3
"""Comparación A/B ciega Qwen3-VL-8B para dos planes development congelados."""
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob,finalize_json_atomic,run_resumable
MODEL_PATH=Path("/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8");REVISION="0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
SCHEMA={"type":"object","additionalProperties":False,"required":["winner","a_specific_match","b_specific_match","evidence_type","confidence"],"properties":{"winner":{"enum":["A","B","tie","unverifiable"]},"a_specific_match":{"enum":["yes","no","unknown"]},"b_specific_match":{"enum":["yes","no","unknown"]},"evidence_type":{"enum":["text","landmark","geometry","attribute","generic","none"]},"confidence":{"enum":["low","medium","high"]}}}
PROMPT="""Compara dos vistas candidatas A y B para la descripción dada. Decide cuál satisface mejor las pistas visuales específicas y permanentes. No localices el lugar, no uses conocimiento externo y no premies elementos urbanos genéricos. Un rótulo solo cuenta si es legible. Las relaciones izquierda/derecha solo cuentan si ambas vistas permiten compararlas. winner=A o B solo con evidencia diferencial observable; tie si ambas son equivalentes; unverifiable si falta evidencia. Devuelve JSON estricto."""
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  while c:=f.read(8*1024*1024):h.update(c)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--local-plan",type=Path,required=True);p.add_argument("--deep-plan",type=Path,required=True);p.add_argument("--assets",type=Path,required=True);p.add_argument("--checkpoint",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();plans={"local":json.load(open(a.local_plan)),"deep":json.load(open(a.deep_plan))};assets=json.load(open(a.assets));paths={r["image_id"]:(a.assets.parent/r["logical_path"]).resolve() for r in assets["assets"]};logical=[]
 for strategy,plan in plans.items():
  for row in plan["pairs"]:
   if row["status"]=="ready":logical.append({"strategy":strategy,**row})
 physical={}
 for row in logical:
  key=(row["query_id"],row["description"],row["incumbent"]["image_id"],row["challenger"]["image_id"]);physical.setdefault(key,row)
 jobs=[]
 for index,(key,row) in enumerate(sorted(physical.items())):
   left,right=paths[row["incumbent"]["image_id"]],paths[row["challenger"]["image_id"]];fingerprint={"index":index,"query_id":row["query_id"],"description_sha256":hashlib.sha256(row["description"].encode()).hexdigest(),"image_a_sha256":digest(left),"image_b_sha256":digest(right),"model_revision":REVISION,"prompt_sha256":hashlib.sha256(PROMPT.encode()).hexdigest(),"schema_sha256":hashlib.sha256(json.dumps(SCHEMA,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"max_new_tokens":64};job_key=(row["query_id"],"pairwise-8b-compact",row["incumbent"]["image_id"],row["challenger"]["image_id"]);jobs.append(PlannedJob(job_key,fingerprint,(row,left,right),True))
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,"PreTrainedTokenizerBase"):
  from transformers import PreTrainedTokenizerBase;tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 from lmformatenforcer import JsonSchemaParser
 from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
 processor=AutoProcessor.from_pretrained(MODEL_PATH,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(MODEL_PATH,local_files_only=True,dtype=torch.bfloat16,device_map="cuda",attn_implementation="sdpa");model.eval();prefix=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(SCHEMA));started=time.perf_counter()
 def execute(job):
  row,left,right=job.payload;begin=time.perf_counter();text=PROMPT+"\nDescripción: "+row["description"];values=processor.apply_chat_template([{"role":"user","content":[{"type":"text","text":"Imagen A"},{"type":"image","image":Image.open(left).convert("RGB")},{"type":"text","text":"Imagen B"},{"type":"image","image":Image.open(right).convert("RGB")},{"type":"text","text":text}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(model.device)
  with torch.inference_mode():generated=model.generate(**values,max_new_tokens=64,do_sample=False,prefix_allowed_tokens_fn=prefix)
  raw=processor.batch_decode(generated[:,values.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
  try:parsed=json.loads(raw);status,error="valid",None
  except json.JSONDecodeError as exception:parsed={"winner":"unverifiable","a_specific_match":"unknown","b_specific_match":"unknown","evidence_type":"none","confidence":"low"};status,error="invalid_output",f"strict_json_parse_failed:{exception.msg}"
  return {"query_id":job.key[0],"candidate_id":job.key[1],"image_id":job.key[2],"claim_id":job.key[3],"status":status,"winner":parsed["winner"],"a_specific_match":parsed["a_specific_match"],"b_specific_match":parsed["b_specific_match"],"evidence_type":parsed["evidence_type"],"confidence":parsed["confidence"],"raw_output":raw,"error":error,"inference_seconds":time.perf_counter()-begin}
 records=run_resumable(checkpoint_path=a.checkpoint,provenance={"task":"pairwise_candidate_comparison_compact_v2","local_plan_sha256":digest(a.local_plan),"deep_plan_sha256":digest(a.deep_plan),"model_revision":REVISION,"max_new_tokens":64},jobs=jobs,execute=execute,policy_result=lambda job:None);by_physical={(r["query_id"],r["image_id"],r["claim_id"]):r for r in records};projections=[]
 for row in logical:
  result=by_physical[(row["query_id"],row["incumbent"]["image_id"],row["challenger"]["image_id"])];projections.append({"strategy":row["strategy"],"query_id":row["query_id"],"incumbent":row["incumbent"],"challenger":row["challenger"],"winner":result["winner"],"a_specific_match":result["a_specific_match"],"b_specific_match":result["b_specific_match"],"evidence_type":result["evidence_type"],"confidence":result["confidence"]})
  document={"schema_version":"1.0","contract_version":"h26-h37-pairwise-8b-run-v2","protocol":{"ground_truth_used":False,"coordinates_sent":False,"candidate_ids_sent":False,"ct2l_scores_sent":False,"rank_sent":False,"maximum_promotions_per_query":2,"previous_verbose_results_reused":False,"json_repair":False,"invalid_outputs_are_unverifiable":True},"model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":REVISION},"generation":{"do_sample":False,"max_new_tokens":64,"schema":SCHEMA,"prompt_sha256":hashlib.sha256(PROMPT.encode()).hexdigest()},"physical_records":records,"projections":projections,"summary":{"logical_pairs":len(logical),"physical_calls":len(records),"deduplicated":len(logical)-len(records),"invalid_outputs":sum(r["status"]=="invalid_output" for r in records),"winners":{v:sum(r["winner"]==v for r in records) for v in ("A","B","tie","unverifiable")}},"resources":{"execution_seconds":time.perf_counter()-started,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}};finalize_json_atomic(output_path=a.output,document=document);print(json.dumps(document["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
