#!/usr/bin/env python3
"""Materializa benchmark synthetic_osm F5.5c sin ejecutar modelos ni rankings."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_synthetic_osm_benchmark import build_synthetic_benchmark, render_benchmark_html, synthetic_evaluation_adapter, validate_benchmark_against_f3, validate_synthetic_benchmark
from src.tfg_phase0.validation import validate_document


DEFAULT_F3 = ROOT / "data/processed/osm/osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141/f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453"


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--f3-bundle",type=Path,default=DEFAULT_F3); parser.add_argument("--catalog-25m",type=Path,default=ROOT/"data/processed/catalog/manifest-25m.json"); parser.add_argument("--catalog-50m",type=Path,default=ROOT/"data/processed/catalog/manifest-50m.json"); parser.add_argument("--count",type=int,default=40); parser.add_argument("--seed",type=int,default=55); parser.add_argument("--minimum-spacing-m",type=float,default=80.0); parser.add_argument("--output-root",required=True,type=Path); args=parser.parse_args()
    config=load_region_config(ROOT/"config/madrid.yaml"); catalog25=load_verified_f1_catalog(args.catalog_25m,config); catalog50=load_verified_f1_catalog(args.catalog_50m,config)
    document=build_synthetic_benchmark(catalog_50=catalog50,catalog_25=catalog25,f3_bundle=args.f3_bundle,count=args.count,seed=args.seed,minimum_spacing_m=args.minimum_spacing_m)
    validate_document(document,"f5_synthetic_osm_benchmark"); validate_benchmark_against_f3(document,catalog_50=catalog50,catalog_25=catalog25,f3_bundle=args.f3_bundle); summary=validate_synthetic_benchmark(document); final=args.output_root/document["benchmark_id"]
    raw=(json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    if final.exists():
        if (final/"benchmark.json").read_bytes()!=raw: raise RuntimeError("benchmark synthetic_osm existente incompatible")
    else:
        args.output_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".f55c-synthetic-",dir=args.output_root) as temporary:
            path=Path(temporary); (path/"benchmark.json").write_bytes(raw); (path/"evaluation-input.json").write_text(json.dumps(synthetic_evaluation_adapter(document),ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); render_benchmark_html(document,path/"review.html"); os.replace(path,final)
    print(json.dumps({**summary,"benchmark_id":document["benchmark_id"],"output":str(final)},sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
