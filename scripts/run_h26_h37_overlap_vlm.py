#!/usr/bin/env python3
"""Qwen3-VL pareado para solapamiento; separado de claims y reranking."""
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob,run_resumable,finalize_json_atomic

MODEL_PATH=Path("/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8")
MODEL_REVISION="0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
WEIGHTS={"model-00001-of-00004.safetensors":(4902275944,"d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa"),"model-00002-of-00004.safetensors":(4915962496,"8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5"),"model-00003-of-00004.safetensors":(4999831048,"83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192"),"model-00004-of-00004.safetensors":(2716270024,"0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5")}
SCHEMA={"type":"object","additionalProperties":False,"required":["verdict","facade_match","geometry_match","distinctive_elements_match","viewpoint_relation"],"properties":{"verdict":{"enum":["different_scene","same_scene","uncertain"]},"facade_match":{"enum":["yes","no","unknown"]},"geometry_match":{"enum":["yes","no","unknown"]},"distinctive_elements_match":{"enum":["yes","no","unknown"]},"viewpoint_relation":{"enum":["equivalent","clearly_different","unknown"]}}}
PROMPT="""Compara solo estas DOS fotografías para detectar contaminación visual. No localices el lugar ni uses conocimiento externo. same_scene solo si reproducen sustancialmente la misma fachada, intersección o escena desde perspectiva equivalente, aunque cambien fecha o vehículos. different_scene si geometría y elementos permanentes son claramente distintos; compartir estilo urbano o un edificio desde perspectiva claramente diferente no basta. uncertain si falta evidencia. Devuelve JSON estricto usando únicamente los enums del esquema."""
def digest(path):
 value=hashlib.sha256()
 with path.open("rb") as stream:
  while chunk:=stream.read(8*1024*1024):value.update(chunk)
 return value.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--review",type=Path,required=True);p.add_argument("--reference-assets",type=Path,required=True);p.add_argument("--candidate-assets",type=Path,required=True);p.add_argument("--checkpoint",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();review=json.loads(a.review.read_text());refs=json.loads(a.reference_assets.read_text());cands=json.loads(a.candidate_assets.read_text());docs={r["image_id"]:(a.reference_assets,r) for r in refs["assets"]}|{r["image_id"]:(a.candidate_assets,r) for r in cands["assets"]};paths={k:(m.parent/r["logical_path"]).resolve() for k,(m,r) in docs.items()}
 for name,(size,sha) in WEIGHTS.items():
  path=MODEL_PATH/name
  if path.stat().st_size!=size or digest(path)!=sha:raise ValueError(f"peso 8B incompatible: {name}")
 jobs=[]
 for index,row in enumerate(review["pairs"]):
  fingerprint={"index":index,"query_id":row["query_id"],"reference_image_id":row["reference_image_id"],"candidate_image_id":row["candidate_image_id"],"reference_sha256":digest(paths[row["reference_image_id"]]),"candidate_sha256":digest(paths[row["candidate_image_id"]]),"model_id":"Qwen/Qwen3-VL-8B-Instruct","model_revision":MODEL_REVISION,"weight_sha256":[value[1] for value in WEIGHTS.values()],"prompt_sha256":hashlib.sha256(PROMPT.encode()).hexdigest(),"schema_sha256":hashlib.sha256(json.dumps(SCHEMA,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"max_new_tokens":80};key=(row["query_id"],"overlap-8b-compact",row["reference_image_id"],row["candidate_image_id"]);jobs.append(PlannedJob(key,fingerprint,(row,paths[row["reference_image_id"]],paths[row["candidate_image_id"]]),True))
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
  row,left,right=job.payload;begin=time.perf_counter();images=[Image.open(left).convert("RGB"),Image.open(right).convert("RGB")];inputs=processor.apply_chat_template([{"role":"user","content":[{"type":"image","image":images[0]},{"type":"image","image":images[1]},{"type":"text","text":PROMPT}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(model.device)
  with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=80,do_sample=False,prefix_allowed_tokens_fn=prefix)
  raw=processor.batch_decode(generated[:,inputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0];value=json.loads(raw)
  expected={"verdict","facade_match","geometry_match","distinctive_elements_match","viewpoint_relation"}
  if set(value)!=expected or value["verdict"] not in {"same_scene","different_scene","uncertain"}:raise ValueError("salida overlap inválida")
  return {"query_id":job.key[0],"candidate_id":job.key[1],"image_id":job.key[2],"claim_id":job.key[3],"reference_image_id":row["reference_image_id"],"candidate_image_id":row["candidate_image_id"],"status":"valid","verdict":value["verdict"],"facade_match":value["facade_match"],"geometry_match":value["geometry_match"],"distinctive_elements_match":value["distinctive_elements_match"],"viewpoint_relation":value["viewpoint_relation"],"raw_output":raw,"inference_seconds":time.perf_counter()-begin}
 records=run_resumable(checkpoint_path=a.checkpoint,provenance={"task":"overlap_detection_only_8b_compact_v2","review_sha256":digest(a.review),"model_revision":MODEL_REVISION,"max_new_tokens":80},jobs=jobs,execute=execute,policy_result=lambda job:None);document={"schema_version":"1.0","contract_version":"h26-h37-overlap-vlm-8b-run-v2","protocol":{"overlap_only":True,"claims_used":False,"rankings_used":False,"ground_truth_used":False,"test_partition_used":False,"qwen3_vl_2b_results_reused":False,"previous_8b_verbose_results_reused":False},"model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":MODEL_REVISION,"weight_sha256":[value[1] for value in WEIGHTS.values()]},"generation":{"do_sample":False,"max_new_tokens":80,"schema":SCHEMA,"prompt_sha256":hashlib.sha256(PROMPT.encode()).hexdigest()},"records":records,"summary":{"pairs":len(records),"verdicts":{v:sum(r["verdict"]==v for r in records) for v in ("same_scene","different_scene","uncertain")}},"resources":{"execution_seconds":time.perf_counter()-started,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}};finalize_json_atomic(output_path=a.output,document=document);print(json.dumps(document["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
