#!/usr/bin/env python3
"""Calcula métricas F5.7 aproximadas y genera JSON/HTML deterministas."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f57_experimental_evaluation import canonical_bytes,evaluate_approximate,render_html
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--f56",required=True,type=Path); p.add_argument("--variants",required=True,type=Path); p.add_argument("--rankings",required=True,type=Path); p.add_argument("--audit",type=Path); p.add_argument("--input-manifest",type=Path); p.add_argument("--transformation-run",type=Path); p.add_argument("--output-root",type=Path,default=ROOT/"results/generated/f5/f57-final"); a=p.parse_args()
 report=evaluate_approximate(json.loads(a.f56.read_text()),json.loads(a.rankings.read_text()),streetview_sha256=digest(a.f56),variants_sha256=digest(a.variants),rankings_sha256=digest(a.rankings)); a.output_root.mkdir(parents=True,exist_ok=True); (a.output_root/"evaluation.json").write_bytes(canonical_bytes(report)+b"\n"); render_html(report,a.output_root/"report.html")
 artifacts={"f56_dataset":a.f56,"qwen_derived_sidecar":a.variants,"provisional_rankings":a.rankings,"evaluation":a.output_root/"evaluation.json","html_report":a.output_root/"report.html"}
 for name,path in (("variant_audit",a.audit),("input_manifest",a.input_manifest),("transformation_run",a.transformation_run)):
  if path is not None: artifacts[name]=path
 manifest={"contract_version":"f57-final-manifest-v2","evaluation_id":report["evaluation_id"],"artifacts":{name:{"logical_path":str(path.resolve().relative_to(ROOT)),"sha256":digest(path),"size_bytes":path.stat().st_size} for name,path in artifacts.items()},"official_f54_metrics":False,"coordinates_used_for_retrieval":False,"variants_human_reviewed":False,"provisional_execution":True}; (a.output_root/"manifest.json").write_bytes(canonical_bytes(manifest)+b"\n"); print(json.dumps({"evaluation_id":report["evaluation_id"],"rankings":report["coverage"]["observed_rankings"],"official_f54_metrics":False},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
