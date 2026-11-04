#!/usr/bin/env python3
"""Congela CT2L Top-100 H26-H37 usando solo descripciones ya congeladas."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--clip-weights",type=Path,required=True);p.add_argument("--cvg-utils-sha256",required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();campaign=json.loads(a.campaign.read_text());rows=campaign["observations"]
 if [r["query_id"] for r in rows]!=[f"H{i:02d}" for i in range(26,38)] or any(r["lifecycle_status"]!="frozen" for r in rows):raise ValueError("campaña H26-H37 no congelada")
 inputs=[{"query_id":r["query_id"],"text":r["description"]["text_es"],"language":"es","text_sha256":hashlib.sha256(r["description"]["text_es"].encode()).hexdigest(),"annotation_sha256":r["freeze"]["canonical_sha256"]} for r in rows]
 reject_ground_truth(inputs,path="ranking_inputs")
 model,galleries=load_runtime_config(ROOT/"config/madrid_f46_retriever.json",project_root=ROOT,cvg_utils_sha256=a.cvg_utils_sha256,clip_weights_path=a.clip_weights);retriever=CrossText2LocRetriever.load(model_config=model,gallery_configs=galleries,region_config=ROOT/"config/madrid.yaml",deep_validate_visual_assets=False)
 try: rankings=[retriever.retrieve(gallery_id="madrid-50m",query_id=r["query_id"],text=r["text"],language="es",k=100) for r in inputs]
 finally:retriever.close()
 document={"schema_version":"1.0","contract_version":"h26-h37-ct2l-top100-v1","ranking_set_id":"","inputs":{"campaign_sha256":digest(a.campaign),"gallery":"madrid-50m","variant":"es_original","ground_truth_used":False,"coordinates_used_for_retrieval":False},"queries":inputs,"rankings":rankings}
 payload={k:v for k,v in document.items() if k!="ranking_set_id"};document["ranking_set_id"]="h26-h37-top100-sha256-"+hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest();finalize_json_atomic(output_path=a.output,document=document);print(json.dumps({"rankings":len(rankings),"ranking_set_id":document["ranking_set_id"],"sha256":digest(a.output)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
