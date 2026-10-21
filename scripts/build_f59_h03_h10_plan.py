#!/usr/bin/env python3
"""Audita relaciones y nombres y congela 40 variantes H03-H10."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f59_oriented_extension import build_plan,canonical_bytes
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--dataset",required=True,type=Path); p.add_argument("--sidecar",required=True,type=Path); p.add_argument("--transformation-run",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args(); plan=build_plan(json.loads(a.dataset.read_text()),json.loads(a.sidecar.read_text()),json.loads(a.transformation_run.read_text())); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(canonical_bytes(plan)+b"\n"); print(json.dumps({"controls":len(plan["controls"]),"audits":len(plan["audit"]),"output":str(a.output)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
