#!/usr/bin/env python3
"""Explica la promoción H23 sin GT y añade geografía solo desde evaluación posterior."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",type=Path,required=True);parser.add_argument("--assets",type=Path,required=True);parser.add_argument("--promotions",type=Path,required=True);parser.add_argument("--geography",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    fixture=json.loads(args.fixture.read_text());assets=json.loads(args.assets.read_text());promotions=json.loads(args.promotions.read_text());geography=json.loads(args.geography.read_text());claims={q["query_id"]:{c["claim_id"]:c for c in q["claims"]["claims"]} for q in fixture["queries"]}["H23"]
    model_reports={}
    for model,document in promotions["models"].items():
        query=next(row for row in document["queries"] if row["query_id"]=="H23");artifact=query["promotion"];operation=artifact["operations"][0];decisions={row["candidate_id"]:row for row in artifact["candidate_decisions"]};aggregate={row["candidate_id"]:row for row in query["aggregate"]["candidates"]};candidate_reports={}
        for role,candidate_id in (("promoted",operation["promoted_candidate_id"]),("displaced",operation["displaced_candidate_id"])):
            candidate=aggregate[candidate_id];supported=[]
            for row in candidate["claims"]:
                if row["state"]=="supported":
                    claim=claims[row["claim_id"]];supported.append({"claim_id":row["claim_id"],"kind":claim["kind"],"source_span":claim["evidence"]["text"],"specificity":claim["specificity"],"weight":row["weight"],"supporting_image_ids":row["supporting_image_ids"],"independent_sequences":row["independent_sequences"]})
            associations=[row for row in assets["associations"] if row["query_id"]=="H23" and row["candidate_id"]==candidate_id]
            candidate_reports[role]={"candidate_id":candidate_id,"baseline_rank":decisions[candidate_id]["baseline_rank"],"baseline_normalized":decisions[candidate_id]["baseline_normalized"],"positive_evidence":decisions[candidate_id]["positive_evidence"],"visual_modifier":decisions[candidate_id]["visual_modifier"],"experimental_score":decisions[candidate_id]["experimental_score"],"valid_verdicts":decisions[candidate_id]["valid_verdicts"],"image_ids":sorted({row["image_id"] for row in associations}),"sequence_ids":sorted({row.get("sequence_id") or f"image:{row['image_id']}" for row in associations}),"supported_claims":supported,"generic_supported_weight":sum(row["weight"] for row in supported if row["specificity"]=="generic"),"distinctive_supported_weight":sum(row["weight"] for row in supported if row["specificity"]=="distinctive")}
        geo_query=next(row for row in geography["models"][model]["rows"] if row["query_id"]=="H23");geo_operation=geo_query["operations"][0]
        model_reports[model]={"decision_without_gt":{"rule":operation["rule"],"promoted":candidate_reports["promoted"],"displaced":candidate_reports["displaced"],"score_margin":candidate_reports["promoted"]["experimental_score"]-candidate_reports["displaced"]["experimental_score"]},"posthoc_geography":geo_operation}
    document={"schema_version":"1.0","contract_version":"h23-v2-partial-promotion-audit-v1","inputs":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.fixture,args.assets,args.promotions,args.geography)},"protocol":{"gt_used_in_decision_audit":False,"geography_loaded_only_for_posthoc_section":True,"partial_availability_conditioned":True},"models":model_reports,"limitations":["partial_unbalanced_coverage","no_human_claim_image_labels","same_h23_operation_for_models","generic_support_may_be_nondiscriminative","distance_did_not_affect_promotion"]}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({m:{"score_margin":r["decision_without_gt"]["score_margin"],"replacement_geography":r["posthoc_geography"]["replacement_geography"]} for m,r in model_reports.items()},sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
