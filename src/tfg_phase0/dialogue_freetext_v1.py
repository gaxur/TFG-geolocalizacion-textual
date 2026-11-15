"""Núcleo aislado DialogueVPR-FreeText-v1 sin parser semántico de respuestas."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,math,re,unicodedata
from pathlib import Path
from typing import Any,Mapping,Protocol,Sequence
from src.tfg_phase0.interactive_dialogue import DialoguePolicyConfig,F3EvidenceIndex,SpatialHypothesis,cluster_ranked_candidates

POLICY_ID='dialogue-vpr-freetext-v1';STATE_CONTRACT='atlas-dialogue-freetext-state-v1';PROMPT_VERSION='dialogue-vpr-freetext-qwen-v1'
FEATURE_LABELS={'monument':'un monumento o elemento histórico','church':'una iglesia o lugar de culto','square':'una plaza o espacio peatonal amplio','park':'un parque o jardín','commercial':'un comercio o equipamiento identificable'}
FEATURE_TERMS={'monument':('monumento','monumental','estatua','memorial'),'church':('iglesia','templo','parroquia','culto'),'square':('plaza','plazoleta','espacio peatonal'),'park':('parque','jardin'),'commercial':('comercio','tienda','restaurante','farmacia','banco','cafeteria','bar')}
SPECIFICITY={'monument':5,'church':4,'square':3,'park':2,'commercial':1}

def canonical(value:Any)->bytes:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest_text(text:str)->str:return hashlib.sha256(text.encode()).hexdigest()
def _fold(text:str)->str:
 text=unicodedata.normalize('NFKD',text.casefold());return ' '.join(''.join(x for x in text if not unicodedata.combining(x)).split())
def mentioned_features(text:str)->set[str]:
 folded=_fold(text);return {feature for feature,terms in FEATURE_TERMS.items() if any(re.search(rf'\b{re.escape(term)}\b',folded) for term in terms)}

def render_literal_transcript(description:str,turns:Sequence[Mapping[str,Any]])->str:
 parts=['[DESCRIPCIÓN ORIGINAL]',description]
 for turn in turns:
  parts.extend([f"[TURNO {turn['index']} — PREGUNTA]",turn['question']['literal'],f"[TURNO {turn['index']} — RESPUESTA LITERAL]",turn['answer']['literal']])
 return '\n'.join(parts)

def build_freetext_prompt(transcript:str)->str:
 return f'''You convert a literal Spanish geolocation dialogue into one English cartographic description for CrossText2Loc.

The input contains one original human description and zero to three chronological question/answer pairs.

Rules:
1. Treat only the original description and human answers as observations. Questions provide context only and never assert an object.
2. Preserve explicit affirmations, negations, uncertainty, inability to observe, spatial relations, observer-relative directions, numbers, distances and proper names.
3. Preserve chronology when a later answer qualifies or explicitly corrects an earlier statement.
4. Do not resolve contradictions, merge entities, infer omitted facts, infer cardinal directions, add geographic knowledge or invent visibility.
5. Produce one concise English cartographic description suitable for text-to-map retrieval.
6. Return only the description, without commentary, labels, JSON or markdown.

Literal chronological dialogue:
{transcript}'''

@dataclass(frozen=True)
class FreeTextQuestion:
 intent_key:str;family:str;question_type:str;literal:str;grounding_kind:str;evidence_refs:tuple[str,...];supported_hypothesis_ids:tuple[str,...];unknown_hypothesis_ids:tuple[str,...];utility:tuple[float,...];audit:Mapping[str,Any]

def select_freetext_question(*,ranking:Mapping[str,Any],evidence:F3EvidenceIndex,policy:DialoguePolicyConfig,description:str,turns:Sequence[Mapping[str,Any]])->tuple[FreeTextQuestion|None,dict[str,Any]]:
 hypotheses=cluster_ranked_candidates(ranking,evidence,reserve_size=policy.reserve_size,radius_m=policy.cluster_radius_m);used={turn['question']['family'] for turn in turns};human_text=' '.join([description,*[turn['answer']['literal'] for turn in turns]])
 mentioned=mentioned_features(human_text);by_feature={}
 for hypothesis in hypotheses:
  for feature in hypothesis.features:
   if feature.feature in FEATURE_LABELS and not feature.ambiguous:by_feature.setdefault(feature.feature,[]).append(hypothesis)
 options=[]
 for feature,supported in sorted(by_feature.items()):
  key=f'closed_observability:{feature}';supported_ids=tuple(x.hypothesis_id for x in supported);unknown=tuple(x.hypothesis_id for x in hypotheses if x.hypothesis_id not in supported_ids);fraction=len(supported_ids)/len(hypotheses) if hypotheses else 1;reasons=[]
  if feature in used:reasons.append('already_used')
  if len(hypotheses)<policy.minimum_hypotheses:reasons.append('insufficient_hypotheses')
  if len(supported_ids)<policy.minimum_supported_hypotheses:reasons.append('insufficient_supported_hypotheses')
  if not unknown:reasons.append('no_unknown_hypotheses')
  if fraction>policy.maximum_supported_fraction:reasons.append('supported_fraction_exceeded')
  if feature in mentioned:reasons.append('already_present_in_human_text')
  refs=tuple(sorted({ref for x in supported for value in x.features if value.feature==feature for ref in value.source_refs}));balance=min(len(supported_ids),len(unknown))/len(hypotheses) if hypotheses else 0;rank_mass=sum(1/x.best_rank for x in supported);utility=(2.0,balance,rank_mass,float(SPECIFICITY[feature]),-float(len(refs)))
  options.append({'intent_key':key,'family':feature,'question_type':'closed_observability','eligible':not reasons,'discard_reasons':reasons,'grounding_kind':'positive_cartographic_existence_only','visibility_supported':False,'supported_hypothesis_ids':supported_ids,'unknown_hypothesis_ids':unknown,'evidence_refs':refs,'utility':utility})
 # Relación abierta: solo entidades ya mencionadas por humanos y soporte individual; F3 no soporta la relación.
 pairs=[];named=sorted(mentioned & set(by_feature))
 for i,left in enumerate(named):
  for right in named[i+1:]:pairs.append((left,right))
 for left,right in pairs:
  family=f'spatial:{left}|{right}';key=f'open_human_relation:{left}|{right}';reasons=['already_used'] if family in used else [];refs=tuple(sorted({ref for feature in (left,right) for x in by_feature[feature] for value in x.features if value.feature==feature for ref in value.source_refs}));utility=(3.0,2.0,0.0,float(SPECIFICITY[left]+SPECIFICITY[right]),-float(len(refs)));options.append({'intent_key':key,'family':family,'question_type':'open_spatial','eligible':not reasons,'discard_reasons':reasons,'grounding_kind':'human_requested_cartographic_relation_none','visibility_supported':False,'object_object_relation_supported':False,'supported_hypothesis_ids':(), 'unknown_hypothesis_ids':(), 'evidence_refs':refs,'utility':utility})
 # Atributos/proximidad son preguntas humanas abiertas, solo para entidades ya mencionadas.
 for feature in named:
  refs=tuple(sorted({ref for x in by_feature[feature] for value in x.features if value.feature==feature for ref in value.source_refs}))
  for kind,priority in (('open_distinctive',1.5),('open_qualitative_proximity',1.25)):
   family=f'{kind}:{feature}';reasons=['already_used'] if family in used else [];options.append({'intent_key':family,'family':family,'question_type':kind,'eligible':not reasons,'discard_reasons':reasons,'grounding_kind':'explicit_human_entity_plus_positive_cartographic_existence','visibility_supported':False,'supported_hypothesis_ids':(),'unknown_hypothesis_ids':(),'evidence_refs':refs,'utility':(priority,1.0,0.0,float(SPECIFICITY[feature]),-float(len(refs)))})
 # Orientación: solo si el humano ya usó marco egocéntrico; no se infiere heading.
 folded=_fold(human_text)
 for direction,term in (('left','izquierda'),('right','derecha'),('front','delante'),('back','detras')):
  if term in folded:
   family=f'observer_relative:{direction}';options.append({'intent_key':family,'family':family,'question_type':'open_observer_relative','eligible':family not in used,'discard_reasons':['already_used'] if family in used else [],'grounding_kind':'explicit_human_egocentric_span','visibility_supported':False,'observer_heading_available':False,'supported_hypothesis_ids':(),'unknown_hypothesis_ids':(),'evidence_refs':(),'utility':(1.0,1.0,0.0,0.0,0.0)})
 eligible=[x for x in options if x['eligible']];selected=sorted(eligible,key=lambda x:(tuple(-n for n in x['utility']),x['intent_key']))[0] if eligible else None
 if selected:
  if selected['question_type']=='closed_observability':literal=f"Sin asumir que sea visible, ¿puedes observar {FEATURE_LABELS[selected['family']]}? Responde libremente o indica que no puedes comprobarlo."
  elif selected['question_type']=='open_spatial':
   left,right=selected['family'].split(':',1)[1].split('|');literal=f"Si puedes observar {FEATURE_LABELS[left]} y {FEATURE_LABELS[right]}, describe cómo están situados uno respecto del otro. Si no puedes comprobarlo, indícalo."
  elif selected['question_type']=='open_distinctive':feature=selected['family'].split(':')[1];literal=f"Si puedes observar {FEATURE_LABELS[feature]}, ¿qué rasgo, texto o nombre lo distingue? Si no puedes comprobarlo, indícalo."
  elif selected['question_type']=='open_qualitative_proximity':feature=selected['family'].split(':')[1];literal=f"Si puedes observar {FEATURE_LABELS[feature]}, ¿está próximo, donde te encuentras, o más al fondo? Si no puedes comprobarlo, indícalo."
  else:direction=selected['family'].split(':')[1];label={'left':'a tu izquierda','right':'a tu derecha','front':'delante de ti','back':'detrás de ti'}[direction];literal=f"Según lo que observas, ¿qué elemento identificable tienes {label}? Si no puedes comprobarlo, indícalo."
  question=FreeTextQuestion(selected['intent_key'],selected['family'],selected['question_type'],literal,selected['grounding_kind'],tuple(selected['evidence_refs']),tuple(selected['supported_hypothesis_ids']),tuple(selected['unknown_hypothesis_ids']),tuple(selected['utility']),selected)
 else:question=None
 # Se auditan, pero nunca se eligen, las familias de calle no soportadas por F3 actual.
 options.extend([{'intent_key':'street:confluence_count','family':'street_intersection','question_type':'open_street','eligible':False,'discard_reasons':['intersection_requires_explicit_topology'],'grounding_kind':'unsupported_f3_semantics','utility':()}, {'intent_key':'street:curvature','family':'street_curvature','question_type':'open_street','eligible':False,'discard_reasons':['relation_not_present_in_source_geometry'],'grounding_kind':'unsupported_f3_semantics','utility':()}, {'intent_key':'street:end_view','family':'street_end','question_type':'open_street','eligible':False,'discard_reasons':['line_of_sight_not_available'],'grounding_kind':'unsupported_f3_semantics','utility':()}])
 audit={'schema_version':'1.0','contract_version':'dialogue-freetext-question-selection-v1','hypothesis_count':len(hypotheses),'reserve_size':policy.reserve_size,'cluster_radius_m':policy.cluster_radius_m,'used_families':sorted(used),'human_mentioned_features':sorted(mentioned),'options':options,'selected_intent_key':selected['intent_key'] if selected else None,'no_selection_reason':None if selected else 'no_valid_question'};return question,audit

class QwenPort(Protocol):
 def transform(self,*,stage:str,transcript:str,prompt:str)->Mapping[str,Any]:...
class RetrievalPort(Protocol):
 def retrieve(self,*,stage:str,query_id:str,text:str)->Mapping[str,Any]:...
class QuestionPort(Protocol):
 def select(self,*,ranking:Mapping[str,Any],description:str,turns:Sequence[Mapping[str,Any]])->tuple[FreeTextQuestion|None,Mapping[str,Any]]:...

def validate_full_ranking(ranking:Mapping[str,Any],expected_universe:set[str]|None=None)->set[str]:
 rows=ranking.get('results',[]);ids=[x.get('candidate_id') for x in rows];scores=[x.get('cosine_similarity') for x in rows]
 if len(rows)!=253 or len(set(ids))!=253 or [x.get('rank') for x in rows]!=list(range(1,254)) or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in scores) or any(scores[i]<scores[i+1] for i in range(252)):raise ValueError('ranking FreeText inválido')
 universe=set(ids)
 if expected_universe is not None and universe!=expected_universe:raise ValueError('universo FreeText divergente')
 return universe

class FreeTextDialogueExecutor:
 policy_id=POLICY_ID;maximum_questions=3;maximum_qwen_calls=4;maximum_ct2l_calls=4
 def __init__(self,*,qwen:QwenPort,retriever:RetrievalPort,questions:QuestionPort):self.qwen=qwen;self.retriever=retriever;self.questions=questions
 def _stage(self,state:dict[str,Any],stage:str)->None:
  transcript=render_literal_transcript(state['description']['literal'],state['turns']);prompt=build_freetext_prompt(transcript);qwen=self.qwen.transform(stage=stage,transcript=transcript,prompt=prompt);ranking=self.retriever.retrieve(stage=stage,query_id=state['query_id'],text=qwen['text']);universe=validate_full_ranking(ranking,set(state['candidate_universe']) if state.get('candidate_universe') else None);state['candidate_universe']=sorted(universe);state['stages'].append({'stage':stage,'source_turn_count':len(state['turns']),'transcript':transcript,'transcript_sha256':digest_text(transcript),'prompt_version':PROMPT_VERSION,'prompt_sha256':digest_text(prompt),'qwen':qwen,'ranking':ranking,'ranking_sha256':hashlib.sha256(canonical(ranking)).hexdigest()})
 def start(self,*,query_id:str,description:str)->dict[str,Any]:
  state={'schema_version':'1.0','contract_version':STATE_CONTRACT,'policy_id':POLICY_ID,'query_id':query_id,'description':{'literal':description,'sha256':digest_text(description)},'turns':[],'stages':[],'question_selections':[],'candidate_universe':[],'status':'running','stop_reason':None,'final_stage':None};self._stage(state,'E0');question,audit=self.questions.select(ranking=state['stages'][-1]['ranking'],description=description,turns=state['turns']);state['question_selections'].append(audit)
  if question is None:state['status']='completed';state['stop_reason']='no_valid_question';state['final_stage']='E0'
  else:state['turns'].append({'index':1,'question':{'literal':question.literal,'sha256':digest_text(question.literal),'intent_key':question.intent_key,'family':question.family,'question_type':question.question_type,'grounding_kind':question.grounding_kind,'evidence_refs':question.evidence_refs},'answer':None});state['status']='awaiting_answer'
  return state
 def answer(self,*,state:Mapping[str,Any],answer_literal:str)->dict[str,Any]:
  value=json.loads(json.dumps(state));turn=value['turns'][-1]
  if value['status']!='awaiting_answer' or turn['answer'] is not None:raise ValueError('estado FreeText no espera respuesta')
  if not answer_literal or len(answer_literal)>1200:raise ValueError('respuesta literal inválida')
  turn['answer']={'literal':answer_literal,'sha256':digest_text(answer_literal),'human_attested':True,'external_context_used':False};stage=f"E{turn['index']}";self._stage(value,stage)
  if turn['index']>=self.maximum_questions:value['status']='completed';value['stop_reason']='max_questions_reached_after_e3';value['final_stage']=stage;return value
  question,audit=self.questions.select(ranking=value['stages'][-1]['ranking'],description=value['description']['literal'],turns=value['turns']);value['question_selections'].append(audit)
  if question is None:value['status']='completed';value['stop_reason']='no_valid_question';value['final_stage']=stage;return value
  value['turns'].append({'index':turn['index']+1,'question':{'literal':question.literal,'sha256':digest_text(question.literal),'intent_key':question.intent_key,'family':question.family,'question_type':question.question_type,'grounding_kind':question.grounding_kind,'evidence_refs':question.evidence_refs},'answer':None});value['status']='awaiting_answer';return value
