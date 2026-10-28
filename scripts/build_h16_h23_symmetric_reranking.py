#!/usr/bin/env python3
"""Construye reranking simétrico desde agregados congelados, sin GT."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.symmetric_visual_reranking import apply_symmetric_reranking, canonical_bytes, freeze_symmetric_policy
from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth


def main():
    p=argparse.ArgumentParser();p.add_argument("--partial-promotions",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();source=json.loads(a.partial_promotions.read_text());reject_ground_truth(source,path="source")
    if source.get("contract_version")!="h16-h23-v2-partial-availability-conditioned-promotion-v1":raise ValueError("source parcial incompatible")
    policy=freeze_symmetric_policy();models={}
    for model,data in source["models"].items():
        queries=[]
        for row in data["queries"]:
            baseline=row["promotion"]["baseline_results"]
            artifact=apply_symmetric_reranking(baseline,row["aggregate"],policy)
            queries.append({"query_id":row["query_id"],"aggregate":row["aggregate"],"reranking":artifact})
        models[model]={"source_run_sha256":data["run_sha256"],"queries":queries}
    doc={"schema_version":"1.0","contract_version":"h16-h23-symmetric-visual-reranking-partial-v1","artifact_id":"","source_partial_promotions_sha256":hashlib.sha256(a.partial_promotions.read_bytes()).hexdigest(),"policy":policy,"protocol":{"ground_truth_used":False,"availability_conditioned_counterfactual":True,"official_frozen_experiment_result":False,"same_formula_all_top50_candidates":True,"negative_evidence_used":False},"models":models,"limitations":["partial_historical_availability","not_complete_top50","no_human_claim_image_ground_truth"]};doc["artifact_id"]="h16-h23-symmetric-partial-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in doc.items() if k!="artifact_id"})).hexdigest();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(doc)+b"\n");print(json.dumps({m:{q["query_id"]:q["reranking"]["operations"] for q in d["queries"]} for m,d in models.items()},sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
