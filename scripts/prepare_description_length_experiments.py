#!/usr/bin/env python3
"""Materializa variantes de longitud y 48 condiciones sin ejecutar modelos."""
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path

VARIANTS={
"H26":{
"short":"Estoy en una intersección de calles estrechas, rodeada de edificios residenciales de varias plantas, balcones y vehículos estacionados junto a las aceras.",
"medium":"Me encuentro en una intersección de calles estrechas rodeada de edificios residenciales de tonos rojizos, amarillos y claros. Delante destaca un edificio de esquina con fachada curva y balcones negros. A mi derecha hay otro edificio anaranjado con un local cerrado y un cartel negro que dice «La Concha».",},
"H27":{
"short":"Estoy en la acera de una calle de varios carriles, junto a una fachada de piedra gris con carteles de Sportium y Sport Bar.",
"medium":"Me encuentro en la acera de una calle urbana con varios carriles. A mi derecha hay una fachada de piedra gris con carteles de «Bazar 4 Sinos Sport Bar» y «Sportium». La acera continúa junto a bolardos metálicos; al fondo veo edificios rojizos, árboles y un edificio monumental claro.",},
"H28":{
"short":"Estoy junto a una calle asfaltada que asciende y gira a la derecha, frente a un paso de peatones y una farmacia.",
"medium":"Me encuentro junto a una calle asfaltada que asciende y se curva a la derecha. Delante hay un paso de peatones. Al otro lado observo una fachada con carteles y una farmacia con dos letreros. Hay personas en la acera, bolardos metálicos y una doble línea blanca en la calzada.",},
"H29":{
"short":"Estoy bajo un gran arco de piedra en un edificio amarillo; delante veo una plaza, soportales y un edificio rojizo con balcones.",
"medium":"Me encuentro bajo un gran arco de piedra que atraviesa un edificio amarillo. A través del arco veo una plaza y un edificio rojizo con ventanas blancas y balcones. A ambos lados se extienden soportales con columnas robustas. Varias personas caminan por el pasaje peatonal y hay un cartel informativo.",},
"H31":{
"short":"Estoy ante un edificio beige con piedra gris, balcones negros, una cafetería Starbucks y un gran pasaje cubierto enmarcado por columnas.",
"medium":"Me encuentro delante de un edificio beige de varias plantas con piedra gris en la planta baja. A mi derecha hay un «Starbucks Coffee» bajo balcones negros. Delante, ligeramente a la izquierda, destaca un pasaje cubierto con columnas de piedra y un logotipo verde de Starbucks. Algunos balcones muestran banderas rojas y amarillas.",},
"H33":{
"short":"Estoy en una plaza amplia de piedra clara, entre edificios monumentales con soportales, balcones y una torre rojiza con reloj al fondo.",
"medium":"Me encuentro en una plaza amplia pavimentada con piedra clara. A la izquierda hay un edificio blanco con balcones y soportales. A la derecha destaca un edificio histórico rojizo con ventanas altas y adornos claros, junto a una fachada monumental gris con esculturas y banderas. Al fondo sobresale una torre rojiza con reloj.",},
"H36":{
"short":"Estoy en una calle estrecha y ascendente, entre edificios con balcones, comercios, vehículos estacionados y un pequeño local llamado «Mini Supermarket».",
"medium":"Me encuentro en una calle estrecha y asfaltada con edificios a ambos lados. A mi derecha hay un «Mini Supermarket» con anuncios de alimentos y bebidas. A la izquierda veo comercios, incluido «El Escarpín», y vehículos estacionados. La calle asciende hacia una zona con árboles y varias personas caminan por las aceras.",},
"H37":{
"short":"Estoy en una calle peatonal adoquinada entre edificios históricos, junto a la entrada de «OXO Museo del Videojuego» y varios comercios.",
"medium":"Me encuentro en una calle peatonal de adoquines claros rodeada de edificios históricos. A la derecha está «OXO Museo del Videojuego» en una fachada gris ornamentada. A la izquierda hay balcones y comercios. Delante veo una zona abierta con un gran mural publicitario, mientras letras decorativas blancas cuelgan sobre la calle.",},
}

def words(text:str)->int:return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b",text,flags=re.UNICODE))
def digest(text:str)->str:return hashlib.sha256(text.encode()).hexdigest()
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();cohort=json.loads(a.cohort.read_text());queries={q['query_id']:q for q in cohort['queries']};expected=('H26','H27','H28','H29','H31','H33','H36','H37')
 if tuple(cohort['query_order'])!=expected:raise ValueError('cohorte inesperada')
 rows=[]
 for qid in expected:
  source=queries[qid]
  for length,text in [('short',VARIANTS[qid]['short']),('medium',VARIANTS[qid]['medium']),('long',source['description_es'])]:
   count=words(text);limits={'short':(15,30),'medium':(45,70),'long':(85,120)}[length]
   if not limits[0]<=count<=limits[1]:raise ValueError(f'{qid}-{length}: {count} palabras')
   rows.append({'variant_id':f'{qid}-{length}','source_query_id':qid,'length':length,'text_es':text,'text_sha256':digest(text),'word_count':count,'token_count':None,'token_count_method':'pending_ct2l_tokenizer_no_model_execution','source_description_sha256':source['description_sha256'],'reference_image':source['reference_image'],'provenance':{'method':'human_curated_subset_of_official_description','official_text_unchanged':True,'image_consulted_for_generation':False,'rankings_consulted':False,'ground_truth_consulted':False},'information_policy':{'short':'rasgos estructurales principales','medium':'rasgos estructurales y discriminativos seleccionados','long':'descripción oficial íntegra'}[length]})
 conditions=[]
 for row in rows:
  for strategy in ('literal_concatenation','en_cartographic'):
   conditions.append({'condition_id':f"{row['variant_id']}-{strategy}",'variant_id':row['variant_id'],'source_query_id':row['source_query_id'],'length':row['length'],'strategy':strategy,'input_text_sha256':row['text_sha256'],'gallery_id':'madrid-50m','candidate_count':253,'retrieval_method':'exhaustive_cosine','tie_break':'candidate_id_ascending','status':'prepared_not_authorized'})
  document={'schema_version':'1.0','contract_version':'description-length-experiments-v1','status':'prepared_not_authorized','cohort_id':cohort['cohort_id'],'cohort_sha256':hashlib.sha256(a.cohort.read_bytes()).hexdigest(),'generation_version':'human-curated-official-subsets-v1','scope_query_ids':list(expected),'length_intervals_words':{'short':[15,30],'medium':[45,70],'long':[85,120]},'variant_count':len(rows),'condition_count':len(conditions),'variants':rows,'conditions':conditions,'controls':{'official_descriptions_modified':False,'h38_h61_opened':False,'ground_truth_used':False,'rankings_used':False,'models_executed':False,'automatic_retries':0},'strategy_contracts':{'literal_concatenation':{'implementation':'src/tfg_phase0/interactive_dialogue_multiturn.py:build_canonical_query','policy_version':'literal-clarifications-newest-first-300-v1','initial_round_behavior':'Spanish variant text unchanged; deterministic clarification concatenation only after answers'},'en_cartographic':{'implementation':'src/tfg_phase0/f5_text_transform.py:translate_en_cartographic','prompt_version':'f53b-text-transform-v2','human_review_required':True}}}
 a.output.mkdir(parents=True,exist_ok=True);payload=json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n';(a.output/'manifest.json').write_bytes(payload);(a.output/'manifest.sha256').write_text(hashlib.sha256(payload).hexdigest()+'  manifest.json\n');return 0
if __name__=='__main__':raise SystemExit(main())
