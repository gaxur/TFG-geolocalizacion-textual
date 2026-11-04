#!/usr/bin/env python3
"""Congela variantes contrastivas globales usando solo evidencia 8B existente."""
from __future__ import annotations
import argparse,hashlib,json,math,re
from pathlib import Path

GENERIC=re.compile(r"\b(?:calle|edificios?|fachadas?|balcones?|vehículos?|personas?|árboles?|bolardos?|aceras?|locales? comerciales?)\b",re.I)
IDENTITY=re.compile(r"\b(?:cartel|letrero|placa|nombre|logotipo|reloj|cruz luminosa|museo|farmacia)\b",re.I)
LANDMARK=re.compile(r"\b(?:arco|torre|monumental|soportales|pasaje|plaza|columnas? de piedra)\b",re.I)
VARIANTS=(("idf_beta_0.1",.1,0.0),("idf_beta_0.2",.2,0.0),("idf_beta_0.35",.35,0.0),("idf_contra_0.1",.2,.1),("idf_contra_0.2",.2,.2),("idf_conservative",.1,.1))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def claim_weight(claim):
 text=claim["value"].get("text_es","");kind=claim["value"].get("human_kind",claim["kind"])
 if IDENTITY.search(text):return 2.0,"identity_or_text_anchor"
 if LANDMARK.search(text):return 1.5,"landmark_anchor"
 if kind=="attribute":return 1.0,"attribute"
 if kind=="relation":return 1.0,"relation"
 if GENERIC.search(text):return .35,"generic_streetscape"
 return 1.0,"other_object"
def main():
 p=argparse.ArgumentParser();p.add_argument("--rankings",type=Path,required=True);p.add_argument("--plan",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();frozen=json.load(open(a.rankings));plan=json.load(open(a.plan));claims={q["query_id"]:{c["claim_id"]:c for c in q["claims"]} for q in plan["queries"]};queries={}
 for qid,query in frozen["queries"].items():
  baseline=query["baseline_results"];aggregate=query["original_aggregate"];rows=aggregate["candidates"];n=len(rows);df={claim_id:sum(any(c["claim_id"]==claim_id and c["state"]=="supported" for c in row["claims"]) for row in rows) for claim_id in claims[qid]};scores=[float(r["cosine_similarity"]) for r in baseline];low,high=min(scores),max(scores);candidate_scores={};evidence=[]
  for row in rows:
   positive=negative=total=0.0;details=[]
   for state in row["claims"]:
    claim=claims[qid][state["claim_id"]];base_weight,role=claim_weight(claim);idf=math.log((n+1)/(df[state["claim_id"]]+1))+1.0;weight=base_weight*idf;total+=weight
    if state["state"]=="supported":positive+=weight
    if state["state"]=="contradicted":negative+=weight
    details.append({"claim_id":state["claim_id"],"state":state["state"],"role":role,"base_weight":base_weight,"support_document_frequency":df[state["claim_id"]],"idf":idf,"effective_weight":weight})
   candidate_scores[row["candidate_id"]]={"positive":positive/total if total else 0.0,"negative":negative/total if total else 0.0,"details":details};evidence.append({"candidate_id":row["candidate_id"],**candidate_scores[row["candidate_id"]]})
  variants={"baseline":[r["candidate_id"] for r in baseline]};decisions={}
  for name,beta,lamb in VARIANTS:
   ordered=[]
   for row in baseline:
    normalized=.5 if high==low else (float(row["cosine_similarity"])-low)/(high-low);visual=candidate_scores[row["candidate_id"]];score=normalized+beta*visual["positive"]-lamb*visual["negative"];ordered.append((-score,row["rank"],row["candidate_id"],score))
   ordered.sort();variants[name]=[r[2] for r in ordered];decisions[name]=[{"candidate_id":r[2],"final_rank":i+1,"score":r[3]} for i,r in enumerate(ordered)]
  queries[qid]={"baseline_results":baseline,"contrastive_evidence":evidence,"variants":variants,"decisions":decisions}
 document={"schema_version":"1.0","contract_version":"h26-h37-contrastive-reranking-v2","ranking_set_id":"","status":"exploratory_development_frozen_before_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"input_top_n":100,"output_top_k":10,"normalization":"full_top100_minmax","global_claim_weight_taxonomy":True,"support_idf_across_candidates":True,"variants":[{"name":n,"beta":b,"lambda":l} for n,b,l in VARIANTS]},"inputs":{"rankings_sha256":digest(a.rankings),"plan_sha256":digest(a.plan)},"queries":queries};document["ranking_set_id"]="h26-h37-contrastive-v2-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"ranking_set_id":document["ranking_set_id"],"variants":len(VARIANTS),"queries":len(queries)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
