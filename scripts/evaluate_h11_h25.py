#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.h11_h25_independent import canonical_bytes,evaluate,render_html
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(); p.add_argument("--dataset",required=True,type=Path); p.add_argument("--qwen-run",required=True,type=Path); p.add_argument("--plan",required=True,type=Path); p.add_argument("--rankings",required=True,type=Path); p.add_argument("--output-root",required=True,type=Path); a=p.parse_args(); dataset=json.loads(a.dataset.read_text()); run=json.loads(a.qwen_run.read_text()); report=evaluate(dataset,json.loads(a.rankings.read_text()),run); a.output_root.mkdir(parents=True,exist_ok=True); ep=a.output_root/"evaluation.json"; hp=a.output_root/"report.html"; ep.write_bytes(canonical_bytes(report)+b"\n"); render_html(dataset,run,report,hp); artifacts={"dataset":a.dataset,"qwen_run":a.qwen_run,"plan":a.plan,"rankings":a.rankings,"evaluation":ep,"html_report":hp}; manifest={"contract_version":"h11-h25-final-manifest-v1","evaluation_id":report["evaluation_id"],"artifacts":{n:{"logical_path":str(x.resolve().relative_to(ROOT)),"sha256":digest(x),"size_bytes":x.stat().st_size} for n,x in artifacts.items()},"official_f54":False,"no_fallback":True}; (a.output_root/"manifest.json").write_bytes(canonical_bytes(manifest)+b"\n"); print(json.dumps({"evaluation_id":report["evaluation_id"],"rankings":report["coverage"]["rankings"]},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
