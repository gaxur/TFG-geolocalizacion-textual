#!/usr/bin/env python3
"""Congela el shortlist Mapillary I01-I20 desde inventario local y H01-H37 seguros."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.i20_remote_acquisition import safe_prior_index,select_shortlist,validate_shortlist
from src.tfg_phase0.mapillary_coverage import canonical_bytes
def load(path):return json.loads(path.read_text(encoding="utf-8"))
def main():
 p=argparse.ArgumentParser();p.add_argument("--inventory",type=Path,required=True);p.add_argument("--h01-h02",type=Path,required=True);p.add_argument("--h03-h10",type=Path,required=True);p.add_argument("--h11-h25",type=Path,required=True);p.add_argument("--h26-h37-selection",type=Path,required=True);p.add_argument("--h26-h37-assets",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();prior=safe_prior_index(h01_h02=load(a.h01_h02),h03_h10=load(a.h03_h10),h11_h25=load(a.h11_h25),h26_h37_selection=load(a.h26_h37_selection),h26_h37_assets=load(a.h26_h37_assets));doc=select_shortlist(load(a.inventory),prior);validate_shortlist(doc);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b"\n");summary={"selection_id":doc["selection_id"],"slots":len(doc["slots"]),"images":sum(len(row["ordered_candidates"]) for row in doc["slots"]),"blocks":len({row["block_id"] for row in doc["slots"]}),"preflight":doc["preflight"]};print(json.dumps(summary,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
