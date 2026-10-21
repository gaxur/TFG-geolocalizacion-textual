#!/usr/bin/env python3
"""Aplica decisiones humanas completas a un benchmark synthetic_osm congelado."""

from __future__ import annotations
import argparse,json,os
from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f5_synthetic_osm_benchmark import apply_human_review,render_benchmark_html,synthetic_evaluation_adapter,validate_synthetic_benchmark
from src.tfg_phase0.validation import validate_document
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--benchmark",required=True,type=Path); p.add_argument("--decisions",required=True,type=Path); p.add_argument("--output-root",required=True,type=Path); a=p.parse_args(); document=json.loads(a.benchmark.read_text()); decisions=json.loads(a.decisions.read_text()); reviewed=apply_human_review(document,decisions); validate_document(reviewed,"f5_synthetic_osm_benchmark"); summary=validate_synthetic_benchmark(reviewed); final=a.output_root/reviewed["benchmark_id"]; raw=(json.dumps(reviewed,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
 if not final.exists():
  a.output_root.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".f55c-review-",dir=a.output_root) as t:
   path=Path(t); (path/"benchmark.json").write_bytes(raw); (path/"evaluation-input.json").write_text(json.dumps(synthetic_evaluation_adapter(reviewed),ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n"); render_benchmark_html(reviewed,path/"review.html"); os.replace(path,final)
 elif (final/"benchmark.json").read_bytes()!=raw: raise RuntimeError("revisión synthetic_osm existente incompatible")
 print(json.dumps({**summary,"approved":sum(r["review"]["status"]=="approved" for r in reviewed["observations"]),"rejected":sum(r["review"]["status"]=="rejected" for r in reviewed["observations"]),"output":str(final)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
