#!/usr/bin/env python3
"""Materializa H01/H02 y entradas F5.2 sin referencias geográficas."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_textual_variants import validate_textual_variant_dataset
from src.tfg_phase0.f59_human_streetview import build_dataset,canonical_bytes,prepare_variant_inputs
from src.tfg_phase0.validation import validate_document
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--spec",type=Path,default=ROOT/"config/madrid_f59_human_streetview.json"); p.add_argument("--output-root",type=Path,required=True); a=p.parse_args(); cfg=load_region_config(ROOT/"config/madrid.yaml"); catalogs={g:load_verified_f1_catalog(ROOT/f"data/processed/catalog/manifest-{size}m.json",cfg) for g,size in (("madrid-25m",25),("madrid-50m",50))}; dataset=build_dataset(json.loads(a.spec.read_text()),catalogs); queries,sidecar=prepare_variant_inputs(dataset,catalogs["madrid-50m"]); validate_document(queries,"f4_query_dataset"); validate_document(sidecar,"f5_textual_variant_dataset"); validate_textual_variant_dataset(sidecar,queries,source_sha256=hashlib.sha256(canonical_bytes(queries)+b"\n").hexdigest(),catalog=catalogs["madrid-50m"]); a.output_root.mkdir(parents=True,exist_ok=True)
 for name,value in (("dataset.json",dataset),("query-dataset.json",queries),("variant-template.json",sidecar)): (a.output_root/name).write_bytes(canonical_bytes(value)+b"\n")
 print(json.dumps({"dataset_id":dataset["dataset_id"],"observations":2,"inside_d004":all(x["geography"]["panorama_coordinate_inside_d004"] for x in dataset["observations"]),"output":str(a.output_root)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
