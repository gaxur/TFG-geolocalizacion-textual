#!/usr/bin/env python3
"""Congela cinco capturas Street View locales como dataset documental pendiente."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f56_streetview_documentary import build_dataset,execution_gate,exploratory_reference_adapter,render_review_html,validate_dataset
from src.tfg_phase0.validation import validate_document
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--spec",type=Path,default=ROOT/"config/madrid_f56_streetview_documentary.json"); p.add_argument("--image-root",type=Path,default=ROOT/"data/streetview"); p.add_argument("--catalog-25m",type=Path,default=ROOT/"data/processed/catalog/manifest-25m.json"); p.add_argument("--catalog-50m",type=Path,default=ROOT/"data/processed/catalog/manifest-50m.json"); p.add_argument("--output-root",required=True,type=Path); a=p.parse_args(); cfg=load_region_config(ROOT/"config/madrid.yaml"); cats={f"madrid-{n}m":load_verified_f1_catalog(getattr(a,f"catalog_{n}m"),cfg) for n in (25,50)}; document=build_dataset(json.loads(a.spec.read_text()),image_root=a.image_root,catalogs=cats); validate_document(document,"f56_streetview_documentary"); summary=validate_dataset(document,catalogs=cats,image_root=a.image_root); final=a.output_root/document["dataset_id"]; raw=(json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
 if not final.exists():
  a.output_root.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".f56-streetview-",dir=a.output_root) as t:
   path=Path(t); (path/"dataset.json").write_bytes(raw); (path/"exploratory-reference.json").write_text(json.dumps(exploratory_reference_adapter(document),ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n"); (path/"execution-gate.json").write_text(json.dumps(execution_gate(document),ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n"); render_review_html(document,path/"review.html",image_prefix=Path(os.path.relpath(a.image_root,final)).as_posix()); os.replace(path,final)
 elif (final/"dataset.json").read_bytes()!=raw: raise RuntimeError("dataset F5.6 existente incompatible")
 print(json.dumps({**summary,"dataset_id":document["dataset_id"],"output":str(final)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
