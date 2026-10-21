#!/usr/bin/env python3
"""Evalúa H01/H02 contra la coordenada de panorama y genera informe/manifest."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.f59_human_streetview import canonical_bytes,evaluate,render_html
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--dataset",required=True,type=Path); p.add_argument("--plan",required=True,type=Path); p.add_argument("--rankings",required=True,type=Path); p.add_argument("--sidecar",required=True,type=Path); p.add_argument("--transformation-run",required=True,type=Path); p.add_argument("--output-root",required=True,type=Path); a=p.parse_args(); report=evaluate(json.loads(a.dataset.read_text()),json.loads(a.rankings.read_text()),dataset_sha256=digest(a.dataset),plan_sha256=digest(a.plan),rankings_sha256=digest(a.rankings)); a.output_root.mkdir(parents=True,exist_ok=True); evaluation=a.output_root/"evaluation.json"; html=a.output_root/"report.html"; evaluation.write_bytes(canonical_bytes(report)+b"\n"); render_html(report,html); artifacts={"dataset":a.dataset,"control_plan":a.plan,"qwen_sidecar":a.sidecar,"transformation_run":a.transformation_run,"rankings":a.rankings,"evaluation":evaluation,"html_report":html}; manifest={"contract_version":"f59-final-manifest-v1","evaluation_id":report["evaluation_id"],"artifacts":{name:{"logical_path":str(path.resolve().relative_to(ROOT)),"sha256":digest(path),"size_bytes":path.stat().st_size} for name,path in artifacts.items()},"official_f54_metrics":False,"reference_kind":"streetview_panorama_coordinate_unknown_uncertainty","coordinates_used_for_retrieval":False,"human_english_control":True,"provisional_execution":True}; (a.output_root/"manifest.json").write_bytes(canonical_bytes(manifest)+b"\n"); print(json.dumps({"evaluation_id":report["evaluation_id"],"rankings":report["coverage"]["observed_rankings"],"output":str(a.output_root)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
