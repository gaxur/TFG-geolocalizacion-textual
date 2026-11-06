#!/usr/bin/env python3
"""Prepara la evaluación E0-E3/R0-R3; solo abre Mapillary tras freeze E completo."""

from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.dialogue_en_cartographic import evaluate_e_vs_r

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--e-rankings",type=Path,required=True);p.add_argument("--literal-run",type=Path,required=True);p.add_argument("--reference",type=Path,required=True);p.add_argument("--authorization",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();e=json.loads(a.e_rankings.read_text())
    # La referencia se abre deliberadamente después de validar freeze E básico.
    if e.get("status")!="COMMITTED" or e.get("real_model_inference") is not True or len(e.get("rankings",[]))!=4:raise ValueError("E0-E3 no congelados")
    authorization=json.loads(a.authorization.read_text());required={"schema_version","contract_version","status","stage","approved","cpu_only","e_rankings_sha256","literal_state_sha256","reference_sha256","output","authorization_source"}
    import hashlib
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if set(authorization)!=required or authorization["contract_version"]!="dialogue-v3-en-cartographic-evaluation-authorization-v1" or authorization["status"]!="OPERATOR_AUTHORIZED" or authorization["stage"]!="cpu_evaluation" or authorization["approved"] is not True or authorization["cpu_only"] is not True or authorization["e_rankings_sha256"]!=digest(a.e_rankings) or authorization["literal_state_sha256"]!=digest(a.literal_run/"state.json") or authorization["reference_sha256"]!=digest(a.reference) or Path(authorization["output"]).resolve()!=a.output.resolve():raise ValueError("autorización de evaluación incompatible")
    state=json.loads((a.literal_run/"state.json").read_text());snapshot=json.loads((a.literal_run/state["session_snapshot"]).read_text());r=[snapshot["initial_ranking"]]+[turn["posterior_ranking"] for turn in snapshot["turns"]];reference=json.loads(a.reference.read_text());report=evaluate_e_vs_r(e,r,reference);finalize_json_atomic(output_path=a.output,document=report);print(json.dumps({"status":report["status"],"output":str(a.output)}));return 0
if __name__=="__main__":raise SystemExit(main())
