#!/usr/bin/env python3
"""Congela fusión multivista estructurada antes de evaluar development."""
from __future__ import annotations
import argparse,collections,hashlib,json,re,unicodedata
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def normalize(text):return " ".join("".join(c for c in unicodedata.normalize("NFKD",text.casefold()) if not unicodedata.combining(c)).split())
def main():
 p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--plan",type=Path,required=True);p.add_argument("--ct2l",type=Path,required=True);p.add_argument("--historical",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();run=json.load(open(a.run));plan=json.load(open(a.plan));ct2l=json.load(open(a.ct2l));historical=json.load(open(a.historical));claims={q["query_id"]:{c["claim_id"]:c for c in q["claims"]} for q in json.load(open(Path("results/generated/mapillary/h26-h37-calibration-v1/visual-plan-top100.filtered.json")))["queries"]};rank_by={q["query_id"]:r for q,r in zip(ct2l["queries"],ct2l["rankings"],strict=True)};history={qid:q for qid,q in historical["queries"].items()};grouped=collections.defaultdict(list)
 for row in run["records"]:grouped[(row["query_id"],row["candidate_id"],row["atomic_claim_id"])].append(row)
 queries={};variants_spec=(("multiview_beta_0.05",.05,0.0),("multiview_beta_0.1",.1,0.0),("multiview_beta_0.2",.2,0.0),("historical01_multiview_0.05",.05,.1),("historical01_multiview_0.1",.1,.1),("historical01_multiview_0.2",.2,.1))
 for qid,ranking in rank_by.items():
  baseline=ranking["results"][:100];scores=[r["cosine_similarity"] for r in baseline];low,high=min(scores),max(scores);historical_positive={r["candidate_id"]:r["positive_evidence"] for r in history[qid]["original_aggregate"]["candidates"]};candidate_evidence={}
  for row in baseline:
   cid=row["candidate_id"];positive=negative=total=0.0;details=[]
   for claim_id,claim in claims[qid].items():
    records=grouped.get((qid,cid,claim_id),[]);valid=[r for r in records if r["status"]=="valid"];support=[];contradict=[]
    for record in valid:
     verdict=record["verdict"]
     if claim.get("requires_ocr") and verdict=="supported":
      ocr=normalize(record.get("ocr_text") or "");tokens=[token for token in re.findall(r"[a-z0-9]+",normalize(claim["value"].get("text_es",""))) if len(token)>=4]
      if tokens and not any(token in ocr for token in tokens):verdict="unverifiable"
     if verdict=="supported":support.append(record)
     if verdict=="contradicted":contradict.append(record)
    role_weight=2.0 if claim.get("requires_ocr") else 1.5 if claim["kind"] in {"spatial_relation","egocentric_relation"} else .5 if claim["specificity"]=="generic" else 1.0;total+=role_weight
    state="conflict" if support and contradict else "supported" if len(support)>=2 else "contradicted" if len(contradict)>=2 else "unverifiable"
    if state=="supported":positive+=role_weight
    if state=="contradicted":negative+=role_weight
    details.append({"claim_id":claim_id,"state":state,"valid_views":len(valid),"supporting_views":len(support),"contradicting_views":len(contradict),"weight":role_weight})
   candidate_evidence[cid]={"positive":positive/total if total else 0.0,"negative":negative/total if total else 0.0,"details":details}
  variants={"baseline":[r["candidate_id"] for r in baseline]};decisions={}
  for name,multi_beta,history_beta in variants_spec:
   ordered=[]
   for row in baseline:
    cid=row["candidate_id"];ct=.5 if high==low else (row["cosine_similarity"]-low)/(high-low);ev=candidate_evidence[cid];score=ct+history_beta*historical_positive[cid]+multi_beta*(ev["positive"]-ev["negative"]);ordered.append((-score,row["rank"],cid,score))
   ordered.sort();variants[name]=[r[2] for r in ordered];decisions[name]=[{"candidate_id":r[2],"final_rank":i+1,"score":r[3]} for i,r in enumerate(ordered)]
  queries[qid]={"baseline_results":baseline,"multiview_evidence":[{"candidate_id":cid,**ev} for cid,ev in candidate_evidence.items()],"variants":variants,"decisions":decisions}
 document={"schema_version":"1.0","contract_version":"h26-h37-multiview-rankings-v3","ranking_set_id":"","status":"exploratory_development_frozen_before_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"minimum_independent_views_for_claim_state":2,"ocr_literal_token_required":True,"contradiction_penalty_enabled":True,"variants":[{"name":n,"multiview_beta":m,"historical_beta":h} for n,m,h in variants_spec]},"inputs":{"run_sha256":digest(a.run),"plan_sha256":digest(a.plan),"ct2l_sha256":digest(a.ct2l),"historical_sha256":digest(a.historical)},"queries":queries};document["ranking_set_id"]="h26-h37-multiview-v3-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"ranking_set_id":document["ranking_set_id"],"queries":len(queries),"variants":len(variants_spec)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
