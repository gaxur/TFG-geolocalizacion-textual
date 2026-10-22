#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.h11_h25_independent import build_dataset,canonical_bytes,historical_rows
def main():
 p=argparse.ArgumentParser(); p.add_argument("--spec",type=Path,default=ROOT/"config/madrid_h11_h25_independent.json"); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); cfg=load_region_config(ROOT/"config/madrid.yaml"); cats={g:load_verified_f1_catalog(ROOT/f"data/processed/catalog/manifest-{n}m.json",cfg) for g,n in (("madrid-25m",25),("madrid-50m",50))}; paths=[ROOT/"results/generated/f5/f56/f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a/dataset.json",ROOT/"results/generated/f5/f59-h01-h02/inputs/dataset.json",ROOT/"results/generated/f5/f59-h03-h10/inputs/dataset.json"]; docs=[json.loads(x.read_text()) for x in paths]; dataset=build_dataset(json.loads(a.spec.read_text()),cats,historical_rows(*docs)); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(canonical_bytes(dataset)+b"\n"); print(json.dumps({"dataset_id":dataset["dataset_id"],"observations":len(dataset["observations"]),"inside":sum(x["reference"]["inside_d004"] for x in dataset["observations"]),"assigned_25":sum(x["reference"]["assignments"]["madrid-25m"]["status"]=="assigned" for x in dataset["observations"]),"assigned_50":sum(x["reference"]["assignments"]["madrid-50m"]["status"]=="assigned" for x in dataset["observations"])},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
