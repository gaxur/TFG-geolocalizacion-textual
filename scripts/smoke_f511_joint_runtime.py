#!/usr/bin/env python3
"""Smoke real de coexistencia Qwen + CrossText2Loc en un proceso."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
from src.tfg_phase0.f5_text_transform import GenerationConfig,QwenTransformersAdapter
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--qwen-model-path",required=True,type=Path); p.add_argument("--clip-weights",required=True,type=Path); p.add_argument("--cvg-utils-sha256",required=True); a=p.parse_args(); import torch; model,galleries=load_runtime_config(ROOT/"config/madrid_f46_retriever.json",project_root=ROOT,cvg_utils_sha256=a.cvg_utils_sha256,clip_weights_path=a.clip_weights); retriever=CrossText2LocRetriever.load(model_config=model,gallery_configs=galleries,region_config=ROOT/"config/madrid.yaml",deep_validate_visual_assets=False); transformer=None; stages=[]
 try:
  stages.append({"stage":"crosstext2loc_loaded","allocated":torch.cuda.memory_allocated(),"reserved":torch.cuda.memory_reserved()}); transformer=QwenTransformersAdapter(a.qwen_model_path,model_id="Qwen/Qwen3-8B",revision="b968826d9c46dd6066d109eabc6255188de91218"); stages.append({"stage":"both_loaded","allocated":torch.cuda.memory_allocated(),"reserved":torch.cuda.memory_reserved(),"peak":torch.cuda.max_memory_allocated()}); transformed=transformer.transform("Estoy en una plaza junto a una estación.","translate_en_cartographic",[],GenerationConfig()); response=retriever.retrieve_many(gallery_ids=("madrid-25m",),query_id="f511-joint-smoke",text=transformed.text,language="en",k=10); stages.append({"stage":"pipeline_complete","transformed_text":transformed.text,"results":len(response["retrievals"][0]["results"]),"allocated":torch.cuda.memory_allocated(),"reserved":torch.cuda.memory_reserved(),"peak":torch.cuda.max_memory_allocated()})
 finally:
  if transformer is not None: transformer.close()
  retriever.close()
 print(json.dumps({"status":"pass","stages":stages},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
