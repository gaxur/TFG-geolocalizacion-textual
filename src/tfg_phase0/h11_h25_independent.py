"""Campaña independiente H11-H25: español frente a Qwen en_cartographic."""
from __future__ import annotations
from collections import Counter
import hashlib,json,math,re,statistics,time
from html import escape
from pathlib import Path
from typing import Any,Mapping,Sequence
from .f4_evaluation import assign_reference,haversine_m,normalize_description,token_jaccard
from .f5_text_transform import GenerationConfig,prepare_prompt,transformation_elements,validate_transformation
from .f57_experimental_evaluation import COORD_RE,INTERNAL_RE,canonical_bytes
from .f59_human_streetview import _validate_results
from .f59_oriented_extension import _relations
from .f510_metric_consolidation import _rate,_summary

GALLERIES=("madrid-25m","madrid-50m"); KINDS=("es_original","en_cartographic")
DATASET_PREFIX="h11-h25-dataset-sha256-"; RUN_PREFIX="h11-h25-qwen-sha256-"; RANK_PREFIX="h11-h25-rankings-sha256-"; EVAL_PREFIX="h11-h25-evaluation-sha256-"
class H11H25Error(ValueError): pass
def _id(doc,prefix,exclude): return prefix+hashlib.sha256(canonical_bytes({k:v for k,v in doc.items() if k not in exclude})).hexdigest()
def _sha(text): return hashlib.sha256(text.encode()).hexdigest()

def build_dataset(spec,catalogs,historical):
 expected=[f"H{i}" for i in range(11,26)]
 if spec.get("contract_version")!="h11-h25-independent-input-v1" or [x.get("query_id") for x in spec.get("observations",[])]!=expected or set(catalogs)!=set(GALLERIES): raise H11H25Error("spec incompatible")
 counts=Counter(x["category"] for x in spec["observations"])
 if counts!={"simple":5,"intermediate":5,"complex":5}: raise H11H25Error("categorías no son 5/5/5")
 old=list(historical); rows=[]
 for source in spec["observations"]:
  qid,text=source["query_id"],source["text"]
  if COORD_RE.search(text) or source["panorama_id"] in text or INTERNAL_RE.search(text): raise H11H25Error("fuga textual")
  lat,lon=float(source["latitude"]),float(source["longitude"]); bbox=next(iter(catalogs.values())).region_bbox_wgs84
  inside=bbox["south"]<=lat<=bbox["north"] and bbox["west"]<=lon<=bbox["east"]
  names=[]
  for mention in source["proper_toponyms"]:
   matches=list(re.finditer(re.escape(mention),text))
   if len(matches)!=1: raise H11H25Error("nombre propio ausente o duplicado")
   names.append({"mention":mention,"span":{"start":matches[0].start(),"end":matches[0].end()}})
  overlaps=[]
  for prior in old:
   distance=haversine_m(lat,lon,prior["latitude"],prior["longitude"])
   if source["panorama_id"]==prior.get("panorama_id") or distance<=25: overlaps.append({"prior_id":prior["id"],"same_panorama":source["panorama_id"]==prior.get("panorama_id"),"distance_m":distance})
  rows.append({"query_id":qid,"category":source["category"],"scene_type":source["scene_type"],"text":{"es_original":text,"sha256":_sha(text),"human_authored":True,"frozen_before_models":True},"proper_toponyms":names,"reference":{"latitude":lat,"longitude":lon,"crs":"EPSG:4326","kind":"google_link_coordinate_unknown_uncertainty","inside_d004":inside,"assignments":{g:assign_reference(lat,lon,c) for g,c in catalogs.items()}},"source":{"provider":"Google Street View","panorama_or_photo_id":source["panorama_id"],"heading_degrees":source["heading_degrees"],"pitch_degrees":source["pitch_degrees"],"url":None,"description_provenance":"human_tfg_owner"},"quality":{"visual_correspondence":"pending_no_local_image","direction_consistency":"not_verified","coordinates_in_text":False,"historical_overlaps":overlaps,"warnings":["link_coordinate_not_centimetric_ground_truth"]+(["interior_user_photo_not_exterior_panorama","heading_not_comparable"] if qid=="H16" else [])}})
 for i,left in enumerate(rows):
  for right in rows[i+1:]:
   distance=haversine_m(left["reference"]["latitude"],left["reference"]["longitude"],right["reference"]["latitude"],right["reference"]["longitude"]); similarity=token_jaccard(left["text"]["es_original"],right["text"]["es_original"])
   if distance<=25 or similarity>=.8: left["quality"].setdefault("internal_near_duplicates",[]).append({"query_id":right["query_id"],"distance_m":distance,"token_jaccard":similarity}); right["quality"].setdefault("internal_near_duplicates",[]).append({"query_id":left["query_id"],"distance_m":distance,"token_jaccard":similarity})
 if len({normalize_description(x["text"]["es_original"]) for x in rows})!=15: raise H11H25Error("descripción exacta duplicada")
 doc={"schema_version":"1.0","contract_version":"h11-h25-independent-dataset-v1","dataset_id":"","protocol":{"category_assignment":spec["category_assignment"],"real_ground_truth":False,"official_f54":False,"reference_kind":"google_link_coordinate_unknown_uncertainty","h16_separate_interior":True},"catalogs":{g:{"manifest_id":c.manifest_id,"sha256":c.sha256,"count":len(c.candidates)} for g,c in catalogs.items()},"observations":rows,"limitations":["no_local_images_for_visual_review","urls_not_supplied","pitch_missing_except_not_applicable_h16","independent_from_rankings_not_verified_ground_truth"]}; doc["dataset_id"]=_id(doc,DATASET_PREFIX,{"dataset_id"}); return doc

def transform_dataset(dataset,transformer,config=GenerationConfig()):
 records=[]
 for row in dataset["observations"]:
  text=row["text"]["es_original"]; names=[x["mention"] for x in row["proper_toponyms"]]; prompt,_=prepare_prompt(text,"translate_en_cartographic",names); result=transformer.transform(text,"translate_en_cartographic",names,config); validation=validate_transformation(text,result.text,"translate_en_cartographic",names,config)
  if not validation["structurally_valid"]: records.append({"query_id":row["query_id"],"status":"rejected","issues":validation["issues"]}); continue
  if _relations(text)-_relations(result.text): records.append({"query_id":row["query_id"],"status":"rejected","issues":[{"code":"relation_lost"}]}); continue
  records.append({"query_id":row["query_id"],"status":"generated","variant_id":f"{row['query_id']}-en-cartographic-h11h25-v1","text":result.text,"text_sha256":_sha(result.text),"language":"en","duration_ms":result.duration_ms,"prompt_sha256":_sha(prompt),"protected_toponyms":names,"validation":validation,"elements":dict(zip(("preserved","removed","modified"),transformation_elements(text,result.text,"en_cartographic",names)))})
 doc={"schema_version":"1.0","contract_version":"h11-h25-qwen-run-v1","run_id":"","dataset_id":dataset["dataset_id"],"transformer":transformer.metadata.__dict__,"generation":{"task":"translate_en_cartographic","prompt_version":"f53b-text-transform-v2","seed":0,"do_sample":False,"temperature":0,"enable_thinking":False},"records":records,"limitations":["automatic_checks_not_human_semantic_review","no_fallback"]}; doc["run_id"]=_id(doc,RUN_PREFIX,{"run_id"}); return doc

def build_plan(dataset,run):
 generated={x["query_id"]:x for x in run["records"] if x["status"]=="generated"}; controls=[]; excluded=[]
 for row in dataset["observations"]:
  controls.append({"query_id":row["query_id"],"category":row["category"],"scene_type":row["scene_type"],"kind":"es_original","control_id":f"{row['query_id']}-es-original-h11h25-v1","text":row["text"]["es_original"],"text_sha256":row["text"]["sha256"],"language":"es","transformation_run_id":None})
  if row["query_id"] in generated:
   x=generated[row["query_id"]]; controls.append({"query_id":row["query_id"],"category":row["category"],"scene_type":row["scene_type"],"kind":"en_cartographic","control_id":x["variant_id"],"text":x["text"],"text_sha256":x["text_sha256"],"language":"en","transformation_run_id":run["run_id"]})
  else: excluded.append({"query_id":row["query_id"],"reason":"qwen_failed_no_fallback"})
 return {"contract_version":"h11-h25-two-control-plan-v1","dataset_id":dataset["dataset_id"],"qwen_run_id":run["run_id"],"controls":controls,"excluded":excluded}

def run_rankings(plan,retriever):
 rows=[]; checkpoint=None
 for control in plan["controls"]:
  start=time.perf_counter(); response=retriever.retrieve_many(gallery_ids=GALLERIES,query_id=control["control_id"],text=control["text"],language=control["language"],k=10); elapsed=(time.perf_counter()-start)*1000; current=response["model"]["checkpoint_sha256"]; checkpoint=current if checkpoint is None else checkpoint
  if checkpoint!=current: raise H11H25Error("checkpoint cambió")
  for retrieval in response["retrievals"]:
   _validate_results(retrieval["results"]); rows.append({**{k:control[k] for k in ("query_id","category","scene_type","kind","control_id","text_sha256","transformation_run_id")},"gallery_id":retrieval["gallery_id"],"results":retrieval["results"],"retrieval_ms":response["timings_ms"]["total"],"pipeline_elapsed_ms":elapsed})
 doc={"contract_version":"h11-h25-rankings-v1","ranking_id":"","checkpoint_sha256":checkpoint,"rows":rows,"limitations":["one_text_encoding_reused_for_two_galleries","no_fallback","no_fusion"]}; doc["ranking_id"]=_id(doc,RANK_PREFIX,{"ranking_id"}); return doc

def evaluate(dataset,rankings,run):
 refs={x["query_id"]:x for x in dataset["observations"]}; rows=[]
 for ranking in rankings["rows"]:
  ref=refs[ranking["query_id"]]; coord=ref["reference"]; assignment=coord["assignments"][ranking["gallery_id"]]; candidates=[]
  for c in ranking["results"]:
   d=haversine_m(coord["latitude"],coord["longitude"],c["latitude"],c["longitude"]); candidates.append({**c,"distance_m":d})
  nearest=min(candidates,key=lambda x:x["distance_m"]); available=assignment["status"]=="assigned"; exact=next((x["rank"] for x in candidates if x["candidate_id"]==assignment.get("candidate_id")),None) if available else None
  rows.append({"query_id":ranking["query_id"],"category":ranking["category"],"scene_type":ranking["scene_type"],"kind":ranking["kind"],"gallery_id":ranking["gallery_id"],"assignment_status":assignment["status"],"exact_available":available,"exact_rank":exact,"recall10":exact is not None if available else None,"recall1":exact==1 if available else None,"geo10_50":nearest["distance_m"]<=50,"geo10_100":nearest["distance_m"]<=100,"geo1_50":candidates[0]["distance_m"]<=50,"geo1_100":candidates[0]["distance_m"]<=100,"minimum_top10_m":nearest["distance_m"],"nearest_rank":nearest["rank"],"top1_m":candidates[0]["distance_m"],"retrieval_ms":ranking["retrieval_ms"],"candidates":candidates})
 groups={"all":lambda r:True,"exterior":lambda r:r["scene_type"]=="exterior_panorama","interior_h16":lambda r:r["query_id"]=="H16"}
 for cat in ("simple","intermediate","complex"): groups[f"category_{cat}"]=lambda r,c=cat:r["category"]==c
 metrics=[]
 for name,pred in groups.items():
  for gallery in GALLERIES:
   for kind in KINDS:
    selected=[r for r in rows if pred(r) and r["gallery_id"]==gallery and r["kind"]==kind]; exact=[r for r in selected if r["exact_available"]]
    if selected: metrics.append({"group":name,"gallery_id":gallery,"kind":kind,"count":len(selected),"geo10_50":_rate(selected,"geo10_50"),"geo10_100":_rate(selected,"geo10_100"),"recall10":_rate(exact,"recall10"),"minimum_top10_m":_summary([r["minimum_top10_m"] for r in selected]),"geo1_50":_rate(selected,"geo1_50"),"geo1_100":_rate(selected,"geo1_100"),"recall1":_rate(exact,"recall1"),"top1_m":_summary([r["top1_m"] for r in selected]),"retrieval_ms":_summary([r["retrieval_ms"] for r in selected])})
 paired=[]
 index={(r["query_id"],r["gallery_id"],r["kind"]):r for r in rows}
 for gallery in GALLERIES:
  cases=[]
  for qid in sorted(refs):
   a=index.get((qid,gallery,"es_original")); b=index.get((qid,gallery,"en_cartographic"))
   if a and b: cases.append({"query_id":qid,"geo50_change":int(b["geo10_50"])-int(a["geo10_50"]),"geo100_change":int(b["geo10_100"])-int(a["geo10_100"]),"minimum_delta_m":b["minimum_top10_m"]-a["minimum_top10_m"],"top1_delta_m":b["top1_m"]-a["top1_m"],"recall10_change":None if not a["exact_available"] else int(b["recall10"])-int(a["recall10"])})
  paired.append({"gallery_id":gallery,"count":len(cases),"geo50_improved":sum(x["geo50_change"]>0 for x in cases),"geo50_worsened":sum(x["geo50_change"]<0 for x in cases),"geo50_tied":sum(x["geo50_change"]==0 for x in cases),"geo100_improved":sum(x["geo100_change"]>0 for x in cases),"geo100_worsened":sum(x["geo100_change"]<0 for x in cases),"minimum_improved":sum(x["minimum_delta_m"]<0 for x in cases),"minimum_worsened":sum(x["minimum_delta_m"]>0 for x in cases),"cases":cases})
 durations={x["query_id"]:x.get("duration_ms") for x in run["records"] if x["status"]=="generated"}
 doc={"contract_version":"h11-h25-evaluation-v1","evaluation_id":"","dataset_id":dataset["dataset_id"],"ranking_id":rankings["ranking_id"],"coverage":{"observations":15,"qwen_generated":len(durations),"rankings":len(rows),"exterior":14,"interior":1},"metrics":metrics,"paired":paired,"per_observation":rows,"qwen_latency_ms":_summary(list(durations.values())) if durations else None,"limitations":["link_coordinates_unknown_uncertainty","h16_interior_separate","categories_random_not_measured_difficulty","visual_direction_review_pending","small_sample"]}; doc["evaluation_id"]=_id(doc,EVAL_PREFIX,{"evaluation_id"}); return doc

def historical_rows(*datasets):
 output=[]
 for doc in datasets:
  for row in doc["observations"]:
   if "panorama_coordinate" in row: output.append({"id":row["observation_id"],"panorama_id":row["panorama"]["panorama_id"],"latitude":row["panorama_coordinate"]["latitude"],"longitude":row["panorama_coordinate"]["longitude"]})
   else: output.append({"id":row["observation_id"],"panorama_id":row["provenance"]["panorama_id"],"latitude":row["link_coordinate"]["latitude"],"longitude":row["link_coordinate"]["longitude"]})
 return output

def render_html(dataset,run,evaluation,output):
 qwen={x["query_id"]:x for x in run["records"]}; qc=[]; individual=[]; candidates=[]
 for row in dataset["observations"]:
  assignments=row["reference"]["assignments"]; qc.append(f"<tr><td>{row['query_id']}</td><td>{row['category']}</td><td>{row['scene_type']}</td><td>{row['reference']['inside_d004']}</td><td>{assignments['madrid-25m']['status']}</td><td>{assignments['madrid-50m']['status']}</td><td>{len(row['quality']['historical_overlaps'])}</td><td>{escape(', '.join(row['quality']['warnings']))}</td></tr>")
 for row in evaluation["per_observation"]:
  individual.append(f"<tr><td>{row['query_id']}</td><td>{row['category']}</td><td>{row['scene_type']}</td><td>{row['gallery_id']}</td><td>{row['kind']}</td><td>{row['exact_rank']}</td><td>{row['geo10_50']}</td><td>{row['geo10_100']}</td><td>{row['minimum_top10_m']:.2f}</td><td>{row['nearest_rank']}</td><td>{row['top1_m']:.2f}</td><td>{row['retrieval_ms']:.2f}</td></tr>")
  for c in row["candidates"]: candidates.append(f"<tr><td>{row['query_id']}</td><td>{row['gallery_id']}</td><td>{row['kind']}</td><td>{c['rank']}</td><td><code>{escape(c['candidate_id'])}</code></td><td>{c['cosine_similarity']:.6f}</td><td>{c['distance_m']:.2f}</td></tr>")
 texts=[]
 for row in dataset["observations"]:
  texts.append(f"<article><h3>{row['query_id']} · {row['category']}</h3><p><strong>Original:</strong> {escape(row['text']['es_original'])}</p><p><strong>Qwen:</strong> {escape(qwen[row['query_id']].get('text','RECHAZADA'))}</p></article>")
 output.write_text(f"<!doctype html><html lang='es'><meta charset='utf-8'><title>H11-H25</title><style>body{{font:15px system-ui;max-width:1500px;margin:auto;padding:2rem}}table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}th,td{{border:1px solid #aaa;padding:.3rem}}article{{border-left:4px solid #555;padding:.3rem 1rem;margin:1rem 0}}code{{overflow-wrap:anywhere}}</style><h1>Evaluación independiente H11–H25</h1><p>Referencias de enlace con incertidumbre desconocida; H16 interior se informa separado.</p><h2>Control de calidad</h2><table><tr><th>ID</th><th>Categoría</th><th>Tipo</th><th>D004</th><th>25 m</th><th>50 m</th><th>Solapamientos</th><th>Advertencias</th></tr>{''.join(qc)}</table><h2>Textos</h2>{''.join(texts)}<h2>Resultados individuales</h2><table><tr><th>ID</th><th>Categoría</th><th>Tipo</th><th>Galería</th><th>Modo</th><th>Rango exacto</th><th>Geo50</th><th>Geo100</th><th>Mín10</th><th>Rango cercano</th><th>Top1</th><th>Retrieval ms</th></tr>{''.join(individual)}</table><h2>600 candidatos</h2><table><tr><th>ID</th><th>Galería</th><th>Modo</th><th>Rank</th><th>Candidato</th><th>Coseno</th><th>Distancia m</th></tr>{''.join(candidates)}</table></html>",encoding="utf-8")
