#!/usr/bin/env python3
"""Congela rerankings Top-100 antes de abrir GT development."""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.discriminative_visual_reranking import aggregate_discriminative_evidence
from src.tfg_phase0.selector_e2e import project_results
from src.tfg_phase0.visual_reranking import aggregate_candidate_evidence
BETAS=(0.1,0.2,0.35,0.5)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def order(baseline,aggregate,beta):
 evidence={r["candidate_id"]:r for r in aggregate["candidates"]};scores=[float(r["cosine_similarity"]) for r in baseline];low,high=min(scores),max(scores);rows=[]
 for row in baseline:
  visual=evidence[row["candidate_id"]];normalized=.5 if high==low else (float(row["cosine_similarity"])-low)/(high-low);positive=float(visual["positive_evidence"]) if visual["coverage_status"]=="available" and visual["valid_verdicts"]>0 else 0.0;rows.append((-(normalized+beta*positive),row["rank"],row["candidate_id"]))
 return [value[2] for value in sorted(rows)]
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--physical-plan",type=Path,required=True);p.add_argument("--results",type=Path,required=True);p.add_argument("--ct2l",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();source=json.load(open(a.plan));physical=json.load(open(a.physical_plan))["physical_plan"];run=json.load(open(a.results));ct2l=json.load(open(a.ct2l));result_index={r["physical_task_id"]:r for r in run["records"]};projected=project_results(physical,result_index,arm="top100",model_key="qwen3-vl-8b");claims={q["query_id"]:q["claims"] for q in source["queries"]};rank_by={q["query_id"]:r for q,r in zip(ct2l["queries"],ct2l["rankings"],strict=True)};queries={}
 for query in source["queries"]:
  qid=query["query_id"];baseline=rank_by[qid]["results"][:100];candidate_ids=[r["candidate_id"] for r in baseline];associations=[r for r in source["associations"] if r["query_id"]==qid];verdicts=[r for r in projected if r["query_id"]==qid];original=aggregate_candidate_evidence(claims[qid],associations,verdicts,candidate_ids=candidate_ids);disc=aggregate_discriminative_evidence(claims[qid],associations,verdicts,candidate_ids=candidate_ids);variants={"baseline":[r["candidate_id"] for r in baseline]}
  for beta in BETAS:variants[f"top100_original_beta_{beta}"]=order(baseline,original,beta);variants[f"top100_discriminative_beta_{beta}"]=order(baseline,disc,beta)
  queries[qid]={"baseline_results":baseline,"original_aggregate":original,"discriminative_aggregate":disc,"variants":variants}
 document={"schema_version":"1.0","contract_version":"h26-h37-top100-calibration-rankings-v1","ranking_set_id":"","protocol":{"ground_truth_used":False,"input_top_n":100,"output_top_k":10,"normalization":"full_top100_minmax","weights_predefined":list(BETAS),"all_variants_frozen_before_evaluation":True,"separate_from_top50_policy":True},"inputs":{"plan_sha256":digest(a.plan),"physical_results_sha256":digest(a.results),"ct2l_sha256":digest(a.ct2l)},"queries":queries};document["ranking_set_id"]="h26-h37-top100-calibration-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();finalize_json_atomic(output_path=a.output,document=document);print(json.dumps({"ranking_set_id":document["ranking_set_id"],"queries":len(queries)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
