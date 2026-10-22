#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
from src.tfg_phase0.h11_h25_independent import build_plan,canonical_bytes,run_rankings
def main():
 p=argparse.ArgumentParser(); p.add_argument("--dataset",required=True,type=Path); p.add_argument("--qwen-run",required=True,type=Path); p.add_argument("--clip-weights",required=True,type=Path); p.add_argument("--cvg-utils-sha256",required=True); p.add_argument("--plan-output",required=True,type=Path); p.add_argument("--rankings-output",required=True,type=Path); a=p.parse_args(); dataset=json.loads(a.dataset.read_text()); run=json.loads(a.qwen_run.read_text()); plan=build_plan(dataset,run); model,galleries=load_runtime_config(ROOT/"config/madrid_f46_retriever.json",project_root=ROOT,cvg_utils_sha256=a.cvg_utils_sha256,clip_weights_path=a.clip_weights); retriever=CrossText2LocRetriever.load(model_config=model,gallery_configs=galleries,region_config=ROOT/"config/madrid.yaml",deep_validate_visual_assets=False)
 try: rankings=run_rankings(plan,retriever)
 finally: retriever.close()
 for path,value in ((a.plan_output,plan),(a.rankings_output,rankings)): path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(canonical_bytes(value)+b"\n")
 print(json.dumps({"controls":len(plan["controls"]),"excluded":len(plan["excluded"]),"rankings":len(rankings["rows"])},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
