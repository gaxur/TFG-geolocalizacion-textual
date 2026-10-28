#!/usr/bin/env python3
"""Analiza cobertura, abstenciones y sesgo de evidencia del subconjunto parcial."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics


def pearson(left, right):
    if len(left) < 2 or len(set(left)) < 2 or len(set(right)) < 2:return None
    lm,rm=statistics.fmean(left),statistics.fmean(right);num=sum((a-lm)*(b-rm) for a,b in zip(left,right));den=(sum((a-lm)**2 for a in left)*sum((b-rm)**2 for b in right))**.5
    return num/den if den else None


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",type=Path,required=True);parser.add_argument("--assets",type=Path,required=True);parser.add_argument("--promotions",type=Path,required=True);parser.add_argument("--run-2b",type=Path,required=True);parser.add_argument("--run-8b",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    fixture=json.loads(args.fixture.read_text());assets=json.loads(args.assets.read_text());promotions=json.loads(args.promotions.read_text());runs={"qwen3-vl-2b":json.loads(args.run_2b.read_text()),"qwen3-vl-8b":json.loads(args.run_8b.read_text())};claims={q["query_id"]:{c["claim_id"]:c for c in q["claims"]["claims"]} for q in fixture["queries"]}
    image_counts={}
    sequence_counts={}
    for q in fixture["queries"]:
        for candidate in q["baseline_results"]:
            rows=[a for a in assets["associations"] if a["query_id"]==q["query_id"] and a["candidate_id"]==candidate["candidate_id"]];key=(q["query_id"],candidate["candidate_id"]);image_counts[key]=len(rows);sequence_counts[key]=len({a.get("sequence_id") or f"image:{a['image_id']}" for a in rows})
    model_reports={}
    for model,run in runs.items():
        policy=[r for r in run["records"] if r["status"]=="policy_unverifiable"];evaluated=[r for r in run["records"] if r["status"]=="valid"];model_unverifiable=[r for r in evaluated if r["verdict"]=="unverifiable"]
        per_claim=[]
        for query_id,query_claims in claims.items():
            for claim_id,claim in query_claims.items():
                rows=[r for r in run["records"] if r["query_id"]==query_id and r["claim_id"]==claim_id];counts={v:sum(r["verdict"]==v for r in rows) for v in ("supported","contradicted","unverifiable")};per_claim.append({"query_id":query_id,"claim_id":claim_id,"kind":claim["kind"],"source_span":claim["evidence"]["text"],"requires_orientation":claim["requires_orientation"],"jobs":len(rows),"policy_unverifiable":sum(r["status"]=="policy_unverifiable" for r in rows),"model_unverifiable":sum(r["status"]=="valid" and r["verdict"]=="unverifiable" for r in rows),"verdicts":counts})
        candidate_rows=[]
        query_documents={q["query_id"]:q for q in promotions["models"][model]["queries"]}
        for query_id,document in query_documents.items():
            for candidate in document["aggregate"]["candidates"]:
                key=(query_id,candidate["candidate_id"]);candidate_rows.append({"query_id":query_id,"candidate_id":candidate["candidate_id"],"image_count":image_counts[key],"independent_sequence_count":sequence_counts[key],"positive_evidence":candidate["positive_evidence"],"negative_evidence":candidate["negative_evidence"],"valid_verdicts":candidate["valid_verdicts"],"coverage_status":candidate["coverage_status"]})
        covered=[r for r in candidate_rows if r["image_count"]>0]
        model_reports[model]={"summary":{"jobs":len(run["records"]),"policy_orientation_abstentions":len(policy),"model_evaluated":len(evaluated),"model_unverifiable":len(model_unverifiable),"model_unverifiable_fraction":len(model_unverifiable)/len(evaluated),"supported":sum(r["verdict"]=="supported" for r in run["records"]),"contradicted":sum(r["verdict"]=="contradicted" for r in run["records"])},"all_unverifiable_claims":[r for r in per_claim if r["verdicts"]["unverifiable"]==r["jobs"]],"per_claim":per_claim,"per_candidate":candidate_rows,"coverage_bias":{"covered_candidates":len(covered),"image_count_distribution":{str(n):sum(r["image_count"]==n for r in candidate_rows) for n in sorted({r["image_count"] for r in candidate_rows})},"pearson_images_positive_evidence":pearson([r["image_count"] for r in covered],[r["positive_evidence"] for r in covered]),"pearson_sequences_positive_evidence":pearson([r["independent_sequence_count"] for r in covered],[r["positive_evidence"] for r in covered])}}
    document={"schema_version":"1.0","contract_version":"h16-h23-v2-partial-evidence-analysis-v1","inputs":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.fixture,args.assets,args.promotions,args.run_2b,args.run_8b)},"coverage":{"unique_images":len(assets["assets"]),"associations":len(assets["associations"]),"planned_unique_images":len(fixture["assets"]),"coverage_is_historical_availability_subset":True},"aggregation_audit":{"generic_weight":0.5,"distinctive_weight":1.0,"normalization":"sum_supported_claim_weights / total_claim_weight","sequence_deduplication":True,"more_images_do_not_directly_add_score":True,"valid_verdicts_depends_on_volume":True,"negative_evidence_used_for_promotion":False},"models":model_reports,"limitations":["no_human_claim_image_labels","cannot_separate_out_of_frame_occlusion_resolution_from_single_verdict_only_output","h16_interior_exterior_domain_mismatch","availability_bias"]}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({m:r["summary"] for m,r in model_reports.items()},sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
