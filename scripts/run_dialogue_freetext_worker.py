#!/usr/bin/env python3
"""Worker Qwen efímero para el prompt literal FreeText-v1."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.atlas_api.dialogue_sessions import atomic_write
from src.tfg_phase0.f5_text_transform import GenerationConfig,QwenTransformersAdapter
def main():
 p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model',type=Path,required=True);a=p.parse_args();request=json.loads(a.request.read_text());required={'contract_version':'atlas-dialogue-freetext-qwen-worker-request-v1','prompt_version':'dialogue-vpr-freetext-qwen-v1'}
 if any(request.get(k)!=v for k,v in required.items()) or hashlib.sha256(request['transcript'].encode()).hexdigest()!=request['transcript_sha256'] or hashlib.sha256(request['prompt'].encode()).hexdigest()!=request['prompt_sha256']:raise ValueError('request FreeText divergente')
 transformer=QwenTransformersAdapter(a.model,model_id='Qwen/Qwen3-8B',revision='b968826d9c46dd6066d109eabc6255188de91218')
 try:result=transformer.generate_prompt(request['prompt'],GenerationConfig())
 finally:transformer.close()
 if not result.text or len(result.text)>2400 or result.text.startswith(('```','{')):raise ValueError('salida FreeText inválida')
 document={'schema_version':'1.0','contract_version':'atlas-dialogue-freetext-en-v1','stage':request['stage'],'transcript_sha256':request['transcript_sha256'],'prompt_version':request['prompt_version'],'prompt_sha256':request['prompt_sha256'],'text':result.text,'raw_output':result.raw_output,'text_sha256':hashlib.sha256(result.text.encode()).hexdigest(),'duration_ms':result.duration_ms,'model':transformer.metadata.__dict__};atomic_write(a.output,document);return 0
if __name__=='__main__':raise SystemExit(main())
