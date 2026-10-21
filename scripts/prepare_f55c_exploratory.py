#!/usr/bin/env python3
"""Audita F5.5c y prepara inputs sin referencias para Qwen/CrossText2Loc."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f55c_experimental_evaluation import audit_benchmark,canonical_bytes,human_review_template,prepare_variant_inputs
from src.tfg_phase0.f5_synthetic_osm_benchmark import validate_benchmark_against_f3
from src.tfg_phase0.f5_textual_variants import validate_textual_variant_dataset
from src.tfg_phase0.validation import validate_document
BENCH=ROOT/"results/generated/f5/f55c-final/f55c-synthetic-osm-sha256-bf7aea13116cda8e027343535f0a6d2de3bd6582aa09c6a65d1f14e9b24873c2/benchmark.json"
F3=ROOT/"data/processed/osm/osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141/f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453"
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--benchmark",type=Path,default=BENCH); p.add_argument("--output-root",type=Path,required=True); a=p.parse_args()
 benchmark=json.loads(a.benchmark.read_text()); validate_document(benchmark,"f5_synthetic_osm_benchmark"); cfg=load_region_config(ROOT/"config/madrid.yaml"); c25=load_verified_f1_catalog(ROOT/"data/processed/catalog/manifest-25m.json",cfg); c50=load_verified_f1_catalog(ROOT/"data/processed/catalog/manifest-50m.json",cfg); validate_benchmark_against_f3(benchmark,catalog_50=c50,catalog_25=c25,f3_bundle=F3)
 audit=audit_benchmark(benchmark); queries,sidecar=prepare_variant_inputs(benchmark,c50,audit); validate_document(queries,"f4_query_dataset"); validate_document(sidecar,"f5_textual_variant_dataset"); raw=canonical_bytes(queries)+b"\n"; validate_textual_variant_dataset(sidecar,queries,source_sha256=hashlib.sha256(raw).hexdigest(),catalog=c50)
 a.output_root.mkdir(parents=True,exist_ok=True)
 for name,value in (("benchmark-audit.json",audit),("human-review-decisions-template.json",human_review_template(benchmark)),("query-dataset.json",queries),("variant-template.json",sidecar)): (a.output_root/name).write_bytes(canonical_bytes(value)+b"\n")
 print(json.dumps({"audited":len(audit["observations"]),"passed":audit["summary"]["passed"],"pending_human_review":audit["summary"]["pending_human_review"],"prepared":len(queries["queries"]),"output":str(a.output_root)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
