#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json
from src.tfg_phase0.ct2l_isolated_environment import validate_ct2l_environment
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,default=ROOT/'config/ct2l_isolated_runtime_cvgtext.json');p.add_argument('--session-config',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();report=validate_ct2l_environment(a.manifest,ROOT,session_config=a.session_config)
 if a.output:
  if a.output.exists():raise ValueError('output ya existe')
  a.output.parent.mkdir(parents=True,exist_ok=True);atomic_write_json(a.output,report)
 print(json.dumps(report,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
