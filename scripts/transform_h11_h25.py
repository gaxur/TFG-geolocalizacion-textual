#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f5_text_transform import GenerationConfig,QwenTransformersAdapter
from src.tfg_phase0.h11_h25_independent import canonical_bytes,transform_dataset
def main():
 p=argparse.ArgumentParser(); p.add_argument("--dataset",required=True,type=Path); p.add_argument("--model-path",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args(); transformer=QwenTransformersAdapter(a.model_path,model_id="Qwen/Qwen3-8B",revision="b968826d9c46dd6066d109eabc6255188de91218")
 try: run=transform_dataset(json.loads(a.dataset.read_text()),transformer,GenerationConfig())
 finally: transformer.close()
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(canonical_bytes(run)+b"\n"); print(json.dumps({"run_id":run["run_id"],"generated":sum(x["status"]=="generated" for x in run["records"]),"rejected":sum(x["status"]!="generated" for x in run["records"])},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
