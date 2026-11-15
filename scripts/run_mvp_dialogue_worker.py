#!/usr/bin/env python3
"""Proceso efímero Qwen o CT2L para el servicio DialogueVPR web."""
from __future__ import annotations
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.atlas_api.dialogue_sessions import atomic_write
def main():
 p=argparse.ArgumentParser();p.add_argument('stage',choices=('qwen','ct2l'));p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model',type=Path);p.add_argument('--runtime-config',type=Path);p.add_argument('--region-config',type=Path);p.add_argument('--clip',type=Path);p.add_argument('--cvg-utils-sha256');a=p.parse_args();request=json.loads(a.request.read_text())
 if a.stage=='qwen':
  from src.tfg_phase0.f5_text_transform import GenerationConfig,QwenTransformersAdapter
  transformer=QwenTransformersAdapter(a.model,model_id='Qwen/Qwen3-8B',revision='b968826d9c46dd6066d109eabc6255188de91218')
  try:result=transformer.transform(request['spanish_text'],'translate_en_cartographic',[],GenerationConfig())
  finally:transformer.close()
  document={'schema_version':'1.0','contract_version':'atlas-dialogue-en-v1','round':request['round'],'text':result.text,'raw_output':result.raw_output,'text_sha256':hashlib.sha256(result.text.encode()).hexdigest(),'duration_ms':result.duration_ms,'model':transformer.metadata.__dict__}
 else:
  from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
  from src.tfg_phase0.interactive_dialogue import ResidentCT2LAdapter
  model,galleries=load_runtime_config(a.runtime_config,project_root=ROOT,cvg_utils_sha256=a.cvg_utils_sha256,clip_weights_path=a.clip);selected=[row for row in galleries if row.gallery_id=='madrid-50m'];runtime=CrossText2LocRetriever.load(model_config=model,gallery_configs=selected,region_config=a.region_config,deep_validate_visual_assets=False);started=time.perf_counter()
  try:ranking=ResidentCT2LAdapter(runtime,'madrid-50m').retrieve_full(query_id=f"{request['query_id']}-E{request['round']}",text=request['text'],language='en')
  finally:runtime.close()
  document={**ranking,'retrieval_elapsed_ms':(time.perf_counter()-started)*1000}
 atomic_write(a.output,document);return 0
if __name__=='__main__':raise SystemExit(main())
