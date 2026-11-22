import hashlib,inspect,json
import pytest
from src.tfg_phase0.dialogue_freetext_v1 import FreeTextDialogueExecutor,FreeTextQuestion,build_freetext_prompt,render_literal_transcript,select_freetext_question,validate_full_ranking
from src.tfg_phase0.interactive_dialogue import CandidateFeature,DialoguePolicyConfig,F3EvidenceIndex

def ranking(offset=0,count=253):return {'gallery_id':'madrid-50m','gallery_count':253,'requested_k':253,'effective_k':253,'ranking_method':'exhaustive_cosine','tie_break':'candidate_id_ascending','results':[{'rank':i,'candidate_id':f'c{i:03d}','latitude':40+i/10000,'longitude':-3,'cosine_similarity':1-i/1000-offset/10000} for i in range(1,count+1)]}
class ScriptedQuestions:
 def __init__(self):self.calls=0
 def select(self,**kwargs):
  self.calls+=1;i=self.calls;return FreeTextQuestion(f'q{i}',f'family{i}','closed_observability',f'Pregunta libre {i}','test',(),(),(),(1,),{}),{'selected_intent_key':f'q{i}'}
class FakeQwen:
 def __init__(self,fail=None):self.calls=[];self.fail=fail
 def transform(self,*,stage,transcript,prompt):
  self.calls.append((stage,transcript,prompt))
  if stage==self.fail:raise RuntimeError('qwen fail')
  return {'text':f'English {stage}','text_sha256':hashlib.sha256(f'English {stage}'.encode()).hexdigest(),'duration_ms':1,'real_model_inference':False}
class FakeRetriever:
 def __init__(self):self.calls=[]
 def retrieve(self,*,stage,query_id,text):self.calls.append((stage,query_id,text));return ranking(len(self.calls))

def test_literal_transcript_is_chronological_and_byte_sensitive():
 turns=[{'index':1,'question':{'literal':'¿Pregunta 1?'},'answer':{'literal':'No, quizá.'}},{'index':2,'question':{'literal':'¿Pregunta 2?'},'answer':{'literal':'A mi izquierda.'}}];text=render_literal_transcript('Descripción exacta.',turns);assert text.index('Pregunta 1')<text.index('No, quizá')<text.index('Pregunta 2')<text.index('A mi izquierda');assert 'No, quizá.' in text
 other=render_literal_transcript('Descripción exacta.',[{**turns[0],'answer':{'literal':'No, quizá. '}},turns[1]]);assert hashlib.sha256(build_freetext_prompt(text).encode()).hexdigest()!=hashlib.sha256(build_freetext_prompt(other).encode()).hexdigest()

def test_e0_to_e3_always_processes_literal_answers_without_parser():
 qwen=FakeQwen();retriever=FakeRetriever();executor=FreeTextDialogueExecutor(qwen=qwen,retriever=retriever,questions=ScriptedQuestions());state=executor.start(query_id='X-H27-FreeText-v1',description='Descripción H27')
 for answer in ('No puedo comprobarlo','No, pero delante veo una farmacia','Me corrijo: a la izquierda'):state=executor.answer(state=state,answer_literal=answer)
 assert state['status']=='completed';assert state['stop_reason']=='max_questions_reached_after_e3';assert state['final_stage']=='E3';assert [x['stage'] for x in state['stages']]==['E0','E1','E2','E3'];assert len(qwen.calls)==len(retriever.calls)==4;assert qwen.calls[-1][1].endswith('Me corrijo: a la izquierda')
 for forbidden in ('claims','observations','relations','corrections','merge_decisions'):assert forbidden not in state
 assert 'dialogue_answer_parser' not in inspect.getsource(__import__('src.tfg_phase0.dialogue_freetext_v1',fromlist=['x']))

def test_qwen_failure_prevents_retrieval_and_no_retry():
 qwen=FakeQwen(fail='E1');retriever=FakeRetriever();executor=FreeTextDialogueExecutor(qwen=qwen,retriever=retriever,questions=ScriptedQuestions());state=executor.start(query_id='X',description='Texto')
 with pytest.raises(RuntimeError):executor.answer(state=state,answer_literal='Respuesta')
 assert [x[0] for x in qwen.calls]==['E0','E1'];assert [x[0] for x in retriever.calls]==['E0']

def test_full_ranking_contract_rejects_incomplete_or_changed_universe():
 universe=validate_full_ranking(ranking());
 with pytest.raises(ValueError):validate_full_ranking(ranking(count=252))
 other=ranking();other['results'][-1]['candidate_id']='different'
 with pytest.raises(ValueError):validate_full_ranking(other,universe)

def test_grounded_selector_avoids_intersection_and_can_request_human_relation():
 features={f'c{i:03d}':() for i in range(1,254)}
 for i in (1,2,3):features[f'c{i:03d}']=(CandidateFeature('church','iglesia',(f'node/{i}',),False),)
 for i in (4,5,6):features[f'c{i:03d}']=(CandidateFeature('square','plaza',(f'way/{i}',),False),)
 for i in (7,8):features[f'c{i:03d}']=(CandidateFeature('intersection','intersección',(f'way/a{i}',f'way/b{i}'),False),)
 evidence=F3EvidenceIndex(dataset_id='fake',features_by_candidate=features,source_hashes={});policy=DialoguePolicyConfig(reserve_size=20,cluster_radius_m=1,minimum_hypotheses=2,minimum_supported_hypotheses=1,maximum_supported_fraction=.75)
 question,audit=select_freetext_question(ranking=ranking(),evidence=evidence,policy=policy,description='Veo una iglesia y una plaza.',turns=[]);assert question.question_type=='open_spatial';assert question.grounding_kind=='human_requested_cartographic_relation_none';assert question.family=='spatial:church|square';assert all(x['family']!='intersection' for x in audit['options'])
 assert next(x for x in audit['options'] if x['family']=='street_intersection')['discard_reasons']==['intersection_requires_explicit_topology']

def test_used_family_is_not_repeated():
 features={f'c{i:03d}':() for i in range(1,254)}
 for i in (1,2):features[f'c{i:03d}']=(CandidateFeature('monument','monumento',(f'node/{i}',),False),CandidateFeature('church','iglesia',(f'node/c{i}',),False))
 evidence=F3EvidenceIndex(dataset_id='fake',features_by_candidate=features,source_hashes={});policy=DialoguePolicyConfig(reserve_size=20,cluster_radius_m=1,minimum_hypotheses=2,minimum_supported_hypotheses=1,maximum_supported_fraction=.75);turns=[{'question':{'family':'monument'},'answer':{'literal':'Respuesta'}}];question,audit=select_freetext_question(ranking=ranking(),evidence=evidence,policy=policy,description='Una calle',turns=turns);assert question is not None and question.family!='monument';assert next(x for x in audit['options'] if x['family']=='monument')['discard_reasons']==['already_used']
