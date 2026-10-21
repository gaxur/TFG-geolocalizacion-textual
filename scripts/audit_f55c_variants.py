#!/usr/bin/env python3
"""Audita las cinco variantes F5.5c sin conceder revisión humana."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f55c_experimental_evaluation import audit_variants,canonical_bytes
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--benchmark",required=True,type=Path); p.add_argument("--sidecar",required=True,type=Path); p.add_argument("--transformation-run",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args(); audit=audit_variants(json.loads(a.sidecar.read_text()),json.loads(a.transformation_run.read_text()),json.loads(a.benchmark.read_text())); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(canonical_bytes(audit)+b"\n"); print(json.dumps({"eligible":len(audit["eligible_pairs"]),"excluded":sum(not row["exploratory_execution_allowed"] for row in audit["issues"]),"output":str(a.output)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
