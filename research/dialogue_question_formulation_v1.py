"""Non-operational, deterministic question wording study for D101 review."""
from __future__ import annotations
import hashlib

VARIANTS={
 'closed_observability':(
  '¿Puedes observar {label}? Si no puedes comprobarlo, dímelo.',
  '¿Ves {label}? También puedes indicar que no lo sabes.',
  'Desde donde estás, ¿distingues {label}? Si no es observable, indícalo.'),
 'open_spatial':(
  'Si ves {left} y {right}, ¿cómo están situados entre sí? Si no puedes comprobarlo, indícalo.',
  '¿Qué posición ocupa {left} respecto de {right}, si puedes observar ambos? Si no puedes comprobarlo, indícalo.',),
 'open_distinctive':(
  'Si ves {label}, ¿qué nombre, texto o rasgo permite reconocerlo? Si no puedes comprobarlo, indícalo.',
  '¿Hay algún detalle visible que distinga {label}? Si no puedes comprobarlo, indícalo.',),
 'open_qualitative_proximity':(
  'Si ves {label}, ¿está junto a ti, cerca o más al fondo? Si no puedes comprobarlo, indícalo.',),
 'open_observer_relative':(
  '¿Qué elemento identificable tienes {direction}? Si no puedes comprobarlo, indícalo.',),
}

def formulate_question(intent:dict,history_families=()):
 question_type=intent['question_type'];variants=VARIANTS[question_type];key=f"{intent['intent_key']}|{'|'.join(history_families)}";index=int(hashlib.sha256(key.encode()).hexdigest()[:8],16)%len(variants);template=variants[index];display=template.format(**intent)
 return{'contract_version':'dialogue-question-presentation-study-v1','question_id':intent['intent_key'],'semantic_intent':question_type,'target_attribute':intent['family'],'candidate_evidence':intent.get('evidence_refs',()),'grounding_kind':intent.get('grounding_kind'),'visibility_supported':intent.get('visibility_supported',False),'object_object_relation_supported':intent.get('object_object_relation_supported'),'observer_heading_available':intent.get('observer_heading_available'),'supported_hypothesis_ids':intent.get('supported_hypothesis_ids',()),'unknown_hypothesis_ids':intent.get('unknown_hypothesis_ids',()),'utility':intent.get('utility',()),'selection_reason':intent.get('selection_reason'),'canonical_question':intent['canonical_question'],'display_question':display,'paraphrase_id':f'{question_type}-v{index+1}','generation_method':'deterministic_controlled_variant','equivalence_status':'pending_human_review','history_context':list(history_families)}
