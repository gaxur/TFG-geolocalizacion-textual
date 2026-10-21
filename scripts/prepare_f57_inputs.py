#!/usr/bin/env python3
"""Adapta el dataset F5.6 canónico a entradas F4.3 y F5 v2 para F5.7."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_textual_variants import validate_textual_variant_dataset
from src.tfg_phase0.f57_experimental_evaluation import canonical_bytes,prepare_variant_inputs
from src.tfg_phase0.validation import validate_document
CANONICAL=ROOT/"results/generated/f5/f56/f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a/dataset.json"
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--f56",type=Path,default=CANONICAL); p.add_argument("--output-root",type=Path,default=ROOT/"results/generated/f5/f57-final/inputs"); a=p.parse_args()
 raw=a.f56.read_bytes(); streetview=json.loads(raw); validate_document(streetview,"f56_streetview_documentary")
 cfg=load_region_config(ROOT/"config/madrid.yaml"); catalog=load_verified_f1_catalog(ROOT/"data/processed/catalog/manifest-50m.json",cfg)
 queries,sidecar=prepare_variant_inputs(streetview,catalog); validate_document(queries,"f4_query_dataset"); validate_document(sidecar,"f5_textual_variant_dataset")
 validate_textual_variant_dataset(sidecar,queries,source_sha256=hashlib.sha256(canonical_bytes(queries)+b"\n").hexdigest(),catalog=catalog)
 a.output_root.mkdir(parents=True,exist_ok=True)
 for name,value in (("query-dataset.json",queries),("variant-template.json",sidecar)): (a.output_root/name).write_bytes(canonical_bytes(value)+b"\n")
 manifest={"contract_version":"f57-input-manifest-v1","source":{"logical_path":str(a.f56.relative_to(ROOT)),"dataset_id":streetview["dataset_id"],"sha256":hashlib.sha256(raw).hexdigest()},"outputs":{name:{"sha256":hashlib.sha256((a.output_root/name).read_bytes()).hexdigest()} for name in ("query-dataset.json","variant-template.json")}}
 (a.output_root/"manifest.json").write_bytes(canonical_bytes(manifest)+b"\n"); print(json.dumps({"observations":4,"output":str(a.output_root),"source_dataset_id":streetview["dataset_id"]},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
