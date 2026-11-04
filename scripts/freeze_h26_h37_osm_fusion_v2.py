#!/usr/bin/env python3
"""Prior OSM/F3 lexical-cartográfico y fusión visual, congelados sin GT."""
from __future__ import annotations
import argparse,collections,hashlib,json,math,re,unicodedata
from pathlib import Path

CONCEPTS=(
 (r"farmacia",(("amenity","pharmacy"),("shop","chemist"))),
 (r"museo",(("tourism","museum"),)),
 (r"plaza",(("place","square"),("highway","pedestrian"))),
 (r"paso de peatones",(("highway","crossing"),)),
 (r"peatonal",(("highway","pedestrian"),)),
 (r"torre",(("man_made","tower"),("building","tower"))),
 (r"iglesia",(("amenity","place_of_worship"),("building","church"))),
 (r"supermercado",(("shop","supermarket"),)),
 (r"cafeter[ií]a|coffee",(("amenity","cafe"),)),
 (r"bar|sport bar",(("amenity","bar"),("amenity","pub"))),
 (r"restaurante",(("amenity","restaurant"),)),
 (r"hotel",(("tourism","hotel"),)),
 (r"monumental|monumento",(("historic","monument"),("historic","memorial"))),
 (r"árbol|arbol",(("natural","tree"),)),
 (r"autobús|autobus",(("highway","bus_stop"),("public_transport","platform"))),
)
GENERIC=re.compile(r"\b(?:calle|edificios?|fachadas?|balcones?|vehículos?|personas?|bolardos?|aceras?)\b",re.I)
GAMMAS=(.05,.1,.2,.35)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def norm(text):return " ".join("".join(c for c in unicodedata.normalize("NFKD",text.casefold()) if not unicodedata.combining(c)).split())
def main():
 p=argparse.ArgumentParser();p.add_argument("--rankings",type=Path,required=True);p.add_argument("--visual-rankings",type=Path,required=True);p.add_argument("--associations",type=Path,required=True);p.add_argument("--objects",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();ct2l=json.load(open(a.rankings));visual=json.load(open(a.visual_rankings));objects={row["osm_ref"]:row for row in map(json.loads,a.objects.read_text().splitlines())};by_candidate=collections.defaultdict(list)
 for row in map(json.loads,a.associations.read_text().splitlines()):
  obj=objects.get(row["osm_ref"])
  if obj:by_candidate[row["candidate_id"]].append({"association":row,"tags":obj.get("tags",{})})
 rank_by={q["query_id"]:r for q,r in zip(ct2l["queries"],ct2l["rankings"],strict=True)};queries={}
 for qid,vquery in visual["queries"].items():
  baseline=rank_by[qid]["results"][:100];claims=[]
  for row in vquery["original_aggregate"]["candidates"][0]["claims"]:pass
  # Los textos se recuperan de la evidencia contrastiva, que conserva roles y pesos globales.
  claim_details={detail["claim_id"]:detail for candidate in vquery.get("contrastive_evidence",[]) for detail in candidate.get("details",[])}
  # Fallback al plan visual asociado no está embebido aquí; se usa el texto normalizado de tags/nombres mediante query completa.
  query_text=next(q["text"] for q in ct2l["queries"] if q["query_id"]==qid);query_norm=norm(query_text);candidate_raw={};explanations={}
  for candidate in baseline:
   cid=candidate["candidate_id"];rows=by_candidate.get(cid,[]);matches=[];score=0.0
   tag_pairs={(str(k),norm(str(v))) for item in rows for k,v in item["tags"].items()}
   for pattern,expected in CONCEPTS:
    if not re.search(pattern,query_text,re.I):continue
    hit=any((key,value) in tag_pairs for key,value in expected)
    if hit:score+=1.5;matches.append({"kind":"concept","pattern":pattern,"weight":1.5})
   names={value for key,value in tag_pairs if key in {"name","name:es","brand","operator","official_name"} and len(value)>=4}
   for name in names:
    if name in query_norm:score+=2.0;matches.append({"kind":"exact_name","value":name,"weight":2.0})
   candidate_raw[cid]=score;explanations[cid]=matches
  values=list(candidate_raw.values());low,high=min(values),max(values);osm={cid:(0.0 if high==low else (value-low)/(high-low)) for cid,value in candidate_raw.items()};ct_scores=[r["cosine_similarity"] for r in baseline];ct_low,ct_high=min(ct_scores),max(ct_scores);ct_norm={r["candidate_id"]:(.5 if ct_high==ct_low else (r["cosine_similarity"]-ct_low)/(ct_high-ct_low)) for r in baseline};visual_order=vquery["variants"]["top100_original_beta_0.1"];visual_rank={cid:index for index,cid in enumerate(visual_order,1)};variants={"baseline":[r["candidate_id"] for r in baseline]};decisions={}
  for gamma in GAMMAS:
   for family in ("osm","visual_osm"):
    ordered=[]
    for r in baseline:
     cid=r["candidate_id"];base=ct_norm[cid] if family=="osm" else 1.0/(60+visual_rank[cid]);score=base+gamma*osm[cid];ordered.append((-score,r["rank"],cid,score))
    ordered.sort();name=f"{family}_gamma_{gamma}";variants[name]=[r[2] for r in ordered];decisions[name]=[{"candidate_id":r[2],"final_rank":i+1,"score":r[3],"osm_score":osm[r[2]],"matches":explanations[r[2]]} for i,r in enumerate(ordered)]
  queries[qid]={"baseline_results":baseline,"variants":variants,"decisions":decisions,"osm_evidence":[{"candidate_id":cid,"raw_score":candidate_raw[cid],"normalized_score":osm[cid],"matches":explanations[cid]} for cid in candidate_raw]}
 document={"schema_version":"1.0","contract_version":"h26-h37-osm-fusion-v2","ranking_set_id":"","status":"exploratory_development_frozen_before_evaluation","protocol":{"ground_truth_used":False,"all_variants_frozen_before_evaluation":True,"osm_is_cartographic_context_not_visibility":True,"global_lexicon":True,"gammas":list(GAMMAS),"normalization":"per_query_minmax_osm"},"inputs":{"ct2l_sha256":digest(a.rankings),"visual_rankings_sha256":digest(a.visual_rankings),"associations_sha256":digest(a.associations),"objects_sha256":digest(a.objects)},"queries":queries};document["ranking_set_id"]="h26-h37-osm-fusion-v2-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in document.items() if k!="ranking_set_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest();a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"ranking_set_id":document["ranking_set_id"],"queries":len(queries),"variants":len(next(iter(queries.values()))["variants"])},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
