#!/usr/bin/env python3
"""Valida bundle Atlas v3 contra las 12 reservas CT2L exactas y el fallback."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_postprocessor import PrecomputedVisualPostprocessor
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--bundle",type=Path,required=True);p.add_argument("--ct2l",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();bundle=json.load(open(a.bundle));ct2l=json.load(open(a.ct2l));processor=PrecomputedVisualPostprocessor(a.bundle);applied=[]
 for query,retrieval in zip(ct2l["queries"],ct2l["rankings"],strict=True):
  reserve={**retrieval,"results":retrieval["results"][:50]};result=processor.apply(query_text=query["text"],processing_variant="es_original",retrieval=reserve)
  if result["status"]!="applied" or len(result["baseline_results"])!=10 or len(result["final_results"])!=10:raise ValueError(f"bundle no aplicable a {query['query_id']}")
  applied.append({"query_id":query["query_id"],"request_id":result["request_id"],"baseline_top1":result["baseline_results"][0]["candidate_id"],"final_top1":result["final_results"][0]["candidate_id"]})
 first_query=ct2l["queries"][0];first_retrieval={**ct2l["rankings"][0],"results":ct2l["rankings"][0]["results"][:50]};fallback=processor.apply(query_text=first_query["text"]+" incompatible",processing_variant="es_original",retrieval=first_retrieval)
 if fallback["status"]!="fallback_baseline" or fallback["final_results"]!=first_retrieval["results"][:10]:raise ValueError("fallback incompatible")
 document={"schema_version":"1.0","contract_version":"h26-h37-atlas-bundle-validation-v1","inputs":{"bundle_sha256":digest(a.bundle),"ct2l_sha256":digest(a.ct2l)},"bundle_id":bundle["bundle_id"],"reserve_k":processor.reserve_k,"applied":applied,"summary":{"exact_queries_applied":len(applied),"incompatible_query_fallback":True,"baseline_preserved_on_fallback":True},"h38_h61_accessed":False};a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps(document["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
