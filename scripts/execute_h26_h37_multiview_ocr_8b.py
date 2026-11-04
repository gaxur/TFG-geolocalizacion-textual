#!/usr/bin/env python3
"""Inferencia estructurada 8B sobre vistas multivista adicionales autorizadas."""
from __future__ import annotations
import argparse,hashlib,json,re,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob,finalize_json_atomic,run_resumable
MODEL=Path("/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8");REV="0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
TEXT=re.compile(r"\b(?:cartel|letrero|placa|nombre|starbucks|sportium|alonzo|escarp[ií]n|oxo|la concha|farmacia|mini supermarket|pisos)\b",re.I);EGO=re.compile(r"\b(?:a la izquierda|a la derecha|delante del observador|delante y|frente a|al fondo de la calle|extremo derecho)\b",re.I);GENERIC=re.compile(r"\b(?:calle|edificios?|vehículos?|personas?|balcones?|bolardos?|árboles?)\b",re.I)
BASE_SCHEMA={"type":"object","additionalProperties":False,"required":["verdict","evidence_type","visibility","limitation"],"properties":{"verdict":{"enum":["supported","contradicted","unverifiable"]},"evidence_type":{"enum":["object","attribute","text","geometry","relation","generic","none"]},"visibility":{"enum":["clear","partial","not_visible"]},"limitation":{"enum":["none","occluded","out_of_frame","too_far","low_resolution","orientation_not_comparable","ambiguous"]}}}
OCR_SCHEMA={"type":"object","additionalProperties":False,"required":["verdict","evidence_type","visibility","limitation","ocr_text"],"properties":{**BASE_SCHEMA["properties"],"ocr_text":{"type":["string","null"],"maxLength":80}}}
PROMPT="""Verifica UNA afirmación usando solo la fotografía. supported exige evidencia específica visible. contradicted exige incompatibilidad visible; ausencia no contradice. unverifiable para duda, oclusión, fuera de campo o baja resolución. Devuelve JSON estricto. Para texto visible, supported exige transcribir literalmente el texto en ocr_text. No localices el lugar ni uses conocimiento externo."""
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  while c:=f.read(8*1024*1024):h.update(c)
 return h.hexdigest()
def classify(claim):
 text=claim["value"]["text_es"];requires_ocr=bool(TEXT.search(text));requires_orientation=claim["value"]["human_kind"]=="relation" and bool(EGO.search(text));specificity="generic" if GENERIC.search(text) and not requires_ocr else "distinctive";kind="visible_text" if requires_ocr else "egocentric_relation" if requires_orientation else "spatial_relation" if claim["value"]["human_kind"]=="relation" else claim["value"]["human_kind"];return {**claim,"kind":kind,"specificity":specificity,"requires_ocr":requires_ocr,"requires_orientation":requires_orientation}
def main():
 p=argparse.ArgumentParser();p.add_argument("stage",choices=("prepare","infer"));p.add_argument("--plan",type=Path,default=ROOT/"results/generated/mapillary/h26-h37-exploratory-v2/multiview-ocr-plan.filtered.json");p.add_argument("--source-plan",type=Path,default=ROOT/"results/generated/mapillary/h26-h37-calibration-v1/visual-plan-top100.filtered.json");p.add_argument("--assets",type=Path,default=ROOT/"results/generated/mapillary/h26-h37-exploratory-v2/multiview-assets.json");p.add_argument("--output-root",type=Path,default=ROOT/"results/generated/mapillary/h26-h37-exploratory-v2");a=p.parse_args();plan=json.load(open(a.plan));source=json.load(open(a.source_plan));assets=json.load(open(a.assets));claims={q["query_id"]:[classify(c) for c in q["claims"]] for q in source["queries"]};paths={r["image_id"]:(a.assets.parent/r["logical_path"]).resolve() for r in assets["assets"]};jobs=[]
 for association in plan["associations"]:
  for claim in claims[association["query_id"]]:
   policy=claim["requires_orientation"] # vistas adicionales no tienen comparabilidad externa congelada
   schema=OCR_SCHEMA if claim["requires_ocr"] else BASE_SCHEMA;mode="policy" if policy else "ocr" if claim["requires_ocr"] else "model";key=(association["query_id"],association["candidate_id"],association["image_id"],claim["claim_id"]+":"+mode);fingerprint={"query_id":association["query_id"],"candidate_id":association["candidate_id"],"image_sha256":digest(paths[association["image_id"]]),"claim":claim,"mode":mode,"model_revision":REV,"schema_sha256":hashlib.sha256(json.dumps(schema,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"prompt_sha256":hashlib.sha256(PROMPT.encode()).hexdigest()};jobs.append(PlannedJob(key,fingerprint,(association,claim,paths[association["image_id"]],schema),not policy))
 if a.stage=="prepare":
  document={"schema_version":"1.0","contract_version":"h26-h37-multiview-ocr-physical-plan-v1","inputs":{"plan_sha256":digest(a.plan),"assets_sha256":digest(a.assets),"source_plan_sha256":digest(a.source_plan)},"claims":claims,"jobs":[job.fingerprint for job in jobs],"summary":{"logical_jobs":len(jobs),"generate_calls":sum(j.requires_execution for j in jobs),"automatic_abstentions":sum(not j.requires_execution for j in jobs),"ocr_calls":sum(j.payload[1]["requires_ocr"] and j.requires_execution for j in jobs)}};finalize_json_atomic(output_path=a.output_root/"multiview-ocr-physical-plan.json",document=document);print(json.dumps(document["summary"],sort_keys=True));return 0
 import torch
 from PIL import Image
 from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
 import transformers.tokenization_utils as tokenization_utils
 if not hasattr(tokenization_utils,"PreTrainedTokenizerBase"):
  from transformers import PreTrainedTokenizerBase;tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
 from lmformatenforcer import JsonSchemaParser
 from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
 processor=AutoProcessor.from_pretrained(MODEL,local_files_only=True);model=Qwen3VLForConditionalGeneration.from_pretrained(MODEL,local_files_only=True,dtype=torch.bfloat16,device_map="cuda",attn_implementation="sdpa");model.eval();prefix_base=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(BASE_SCHEMA));prefix_ocr=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,JsonSchemaParser(OCR_SCHEMA));started=time.perf_counter()
 def policy(job):
  association,claim,_,_=job.payload;return {"query_id":job.key[0],"candidate_id":job.key[1],"image_id":job.key[2],"claim_id":job.key[3],"atomic_claim_id":claim["claim_id"],"status":"policy_unverifiable","verdict":"unverifiable","evidence_type":"none","visibility":"not_visible","limitation":"orientation_not_comparable","ocr_text":None,"raw_output":None,"error":None,"inference_seconds":0.0}
 def execute(job):
  association,claim,path,schema=job.payload;begin=time.perf_counter();text=PROMPT+"\nTipo: "+claim["kind"]+"\nAfirmación: "+claim["value"]["text_es"];values=processor.apply_chat_template([{"role":"user","content":[{"type":"image","image":Image.open(path).convert("RGB")},{"type":"text","text":text}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(model.device)
  with torch.inference_mode():generated=model.generate(**values,max_new_tokens=128,do_sample=False,prefix_allowed_tokens_fn=prefix_ocr if claim["requires_ocr"] else prefix_base)
  raw=processor.batch_decode(generated[:,values.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
  try:parsed=json.loads(raw);status,error="valid",None
  except json.JSONDecodeError as exc:parsed={"verdict":"unverifiable","evidence_type":"none","visibility":"not_visible","limitation":"ambiguous","ocr_text":None};status,error="invalid_output",f"strict_json_parse_failed:{exc.msg}"
  if claim["requires_ocr"] and parsed.get("verdict")=="supported" and not parsed.get("ocr_text"):parsed["verdict"]="unverifiable";status="invalid_output";error="supported_ocr_without_literal_text"
  return {"query_id":job.key[0],"candidate_id":job.key[1],"image_id":job.key[2],"claim_id":job.key[3],"atomic_claim_id":claim["claim_id"],"status":status,"verdict":parsed["verdict"],"evidence_type":parsed["evidence_type"],"visibility":parsed["visibility"],"limitation":parsed["limitation"],"ocr_text":parsed.get("ocr_text"),"raw_output":raw,"error":error,"inference_seconds":time.perf_counter()-begin}
 records=run_resumable(checkpoint_path=a.output_root/"multiview-ocr-8b.checkpoint.jsonl",provenance={"task":"multiview_structured_claim_verification","plan_sha256":digest(a.plan),"model_revision":REV},jobs=jobs,execute=execute,policy_result=policy);document={"schema_version":"1.0","contract_version":"h26-h37-multiview-ocr-8b-run-v1","protocol":{"ground_truth_used":False,"rankings_sent":False,"scores_sent":False,"coordinates_sent":False,"reference_images_used":False,"json_repair":False},"model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":REV},"records":records,"summary":{"jobs":len(records),"valid":sum(r["status"]=="valid" for r in records),"invalid":sum(r["status"]=="invalid_output" for r in records),"policy":sum(r["status"]=="policy_unverifiable" for r in records),"ocr_jobs":sum(r.get("ocr_text") is not None for r in records),"verdicts":{v:sum(r["verdict"]==v for r in records) for v in ("supported","contradicted","unverifiable")}},"resources":{"execution_seconds":time.perf_counter()-started,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}};finalize_json_atomic(output_path=a.output_root/"multiview-ocr-8b-run.json",document=document);print(json.dumps(document["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
