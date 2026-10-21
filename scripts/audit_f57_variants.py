#!/usr/bin/env python3
"""Audita variantes Qwen F5.7 y permite solo rankings provisionales seguros."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f57_experimental_evaluation import audit_variants,canonical_bytes
from src.tfg_phase0.validation import validate_document
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--sidecar",required=True,type=Path); p.add_argument("--transformation-run",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args()
 sidecar=json.loads(a.sidecar.read_text()); run=json.loads(a.transformation_run.read_text()); validate_document(sidecar,"f5_textual_variant_dataset"); validate_document(run,"f5_transformation_run"); audit=audit_variants(sidecar,run); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(canonical_bytes(audit)+b"\n"); print(json.dumps({"eligible":len(audit["eligible_pairs"]),"excluded":sum(not row["experimental_execution_allowed"] for row in audit["issues"]),"output":str(a.output)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
