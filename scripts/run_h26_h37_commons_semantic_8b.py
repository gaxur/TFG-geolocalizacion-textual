#!/usr/bin/env python3
"""Piloto 8B Commons como evidencia semántica de objeto, nunca cámara."""
from __future__ import annotations
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob,finalize_json_atomic,run_resumable
MODEL=Path("/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8");REV="0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
SCHEMA={"type":"object","additionalProperties":False,"required":["target_visible","description_support","evidence_type","ocr_text","limitation"],"properties":{"target_visible":{"enum":["yes","no","uncertain"]},"description_support":{"enum":["specific","generic","none","uncertain"]},"evidence_type":{"enum":["named_text","landmark","architecture","object","none"]},"ocr_text":{"type":["string","null"],"maxLength":80},"limitation":{"enum":["none","different_view","interior","historical","occluded","low_resolution","unrelated","uncertain"]}}}
PROMPT="""Usa solo esta imagen Commons como evidencia semántica del objeto indicado. No infieras posición de cámara ni ubicación del observador. Comprueba si el objeto objetivo es visible y si aporta evidencia específica para la descripción. Una coincidencia genérica no es específica. named_text requiere texto legible y transcripción literal en ocr_text. Si la foto es interior, histórica, de evento o no muestra la escena descrita, indícalo como limitación. Devuelve JSON estricto."""
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--assets",type=Path,required=True);p.add_argument("--campaign",type=Path,required=True);p.add_argument("--checkpoint",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();plan=json.load(open(a.plan));assets=json.load(open(a.assets));campaign=json.load(open(a.campaign));descriptions={r["query_id"]:r["description"]["text_es"] for r in campaign["observations"]};paths={r["page_id"]:(a.assets.parent/r["logical_path"]).resolve() for r in assets["assets"]};jobs=[]
 for index,row in enumerate(plan["assets"]):
  key=(row["query_id"],"commons-object",str(row["page_id"]),row["target"]["osm_ref"]);fingerprint={"index":index,"query_id":row["query_id"],"page_id":row["page_id"],"image_sha256":digest(paths[row["page_id"]]),"description_sha256":hashlib.sha256(descriptions[row["query_id"]].encode()).hexdigest(),"target":row["target"],"model_revision":REV,"prompt_sha256":hashlib.sha256(PROMPT.encode()).hexdigest(),"schema_sha256":hashlib.sha256(json.dumps(SCHEMA,sort_keys=True,separators=(",",":")).encode()).hexdigest()};jobs.append(PlannedJob(key,fingerprint,(row,paths[row["page_id"]],descriptions[row["query_id"]]),True))
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,"PreTrainedTokenizerBase"):
  from transformers import PreTrainedTokenizerBase;tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 from lmformatenforcer import JsonSchemaParser
 from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
 processor=AutoProcessor.from_pretrained(MODEL,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(MODEL,local_files_only=True,dtype=torch.bfloat16,device_map="cuda",attn_implementation="sdpa");model.eval();prefix=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(SCHEMA));started=time.perf_counter()
 def execute(job):
  row,path,description=job.payload;begin=time.perf_counter();target=row["target"].get("label") or row["target"].get("wikidata_id");text=PROMPT+f"\nObjeto objetivo: {target}\nDescripción: {description}";values=processor.apply_chat_template([{"role":"user","content":[{"type":"image","image":Image.open(path).convert("RGB")},{"type":"text","text":text}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(model.device)
  with torch.inference_mode():generated=model.generate(**values,max_new_tokens=128,do_sample=False,prefix_allowed_tokens_fn=prefix)
  raw=processor.batch_decode(generated[:,values.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
  try:parsed=json.loads(raw);status,error="valid",None
  except json.JSONDecodeError as exc:parsed={"target_visible":"uncertain","description_support":"uncertain","evidence_type":"none","ocr_text":None,"limitation":"uncertain"};status,error="invalid_output",f"strict_json_parse_failed:{exc.msg}"
  return {"query_id":job.key[0],"candidate_id":job.key[1],"image_id":job.key[2],"claim_id":job.key[3],"status":status,**parsed,"raw_output":raw,"error":error,"inference_seconds":time.perf_counter()-begin}
 records=run_resumable(checkpoint_path=a.checkpoint,provenance={"task":"commons_semantic_object_evidence","plan_sha256":digest(a.plan),"model_revision":REV},jobs=jobs,execute=execute,policy_result=lambda job:None);document={"schema_version":"1.0","contract_version":"h26-h37-commons-semantic-8b-run-v1","protocol":{"ground_truth_used":False,"camera_position_used":False,"coordinates_sent":False,"candidate_ids_sent":False,"osm_object_link_used":True,"object_evidence_only":True},"model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":REV},"records":records,"summary":{"jobs":len(records),"valid":sum(r["status"]=="valid" for r in records),"invalid":sum(r["status"]=="invalid_output" for r in records),"specific_support":sum(r["description_support"]=="specific" for r in records),"target_visible":sum(r["target_visible"]=="yes" for r in records)},"resources":{"execution_seconds":time.perf_counter()-started,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}};finalize_json_atomic(output_path=a.output,document=document);print(json.dumps(document["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
