#!/usr/bin/env python3
"""Ejecuta los 24 rankings F5.9 exhaustivos sobre ambas galerías."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever,load_runtime_config
from src.tfg_phase0.f59_human_streetview import canonical_bytes,run_rankings
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--plan",required=True,type=Path); p.add_argument("--runtime-config",type=Path,default=ROOT/"config/madrid_f46_retriever.json"); p.add_argument("--cvg-utils-sha256",required=True); p.add_argument("--clip-weights",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args(); model,galleries=load_runtime_config(a.runtime_config,project_root=ROOT,cvg_utils_sha256=a.cvg_utils_sha256,clip_weights_path=a.clip_weights); retriever=CrossText2LocRetriever.load(model_config=model,gallery_configs=galleries,region_config=ROOT/"config/madrid.yaml",deep_validate_visual_assets=False)
 try: report=run_rankings(json.loads(a.plan.read_text()),retriever)
 finally: retriever.close()
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(canonical_bytes(report)+b"\n"); print(json.dumps({"ranking_id":report["ranking_id"],"rankings":len(report["rows"]),"output":str(a.output)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
