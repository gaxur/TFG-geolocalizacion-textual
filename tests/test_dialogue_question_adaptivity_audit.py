from src.tfg_phase0.dialogue_freetext_v1 import select_freetext_question
from src.tfg_phase0.interactive_dialogue import CandidateFeature,DialoguePolicyConfig,F3EvidenceIndex

def ranking(order=None,score_scale=1.0):
 ids=order or [f'c{i:03d}' for i in range(1,254)];return{'results':[{'rank':i,'candidate_id':cid,'latitude':40+i/1000,'longitude':-3,'cosine_similarity':score_scale*(1-i/1000)} for i,cid in enumerate(ids,1)]}
def policy(max_fraction=.75):return DialoguePolicyConfig(reserve_size=20,cluster_radius_m=1,minimum_hypotheses=2,minimum_supported_hypotheses=1,maximum_supported_fraction=max_fraction)
def evidence():
 features={f'c{i:03d}':() for i in range(1,254)}
 for i in range(1,11):features[f'c{i:03d}']=(CandidateFeature('church','iglesia',(f'node/church/{i}',),False),)
 for i in range(101,111):features[f'c{i:03d}']=(CandidateFeature('monument','monumento',(f'node/monument/{i}',),False),)
 return F3EvidenceIndex(dataset_id='audit',features_by_candidate=features,source_hashes={})

def test_ranking_membership_changes_question_for_grounded_reason():
 church_order=[f'c{i:03d}' for i in range(1,21)]+[f'c{i:03d}' for i in range(21,254)]
 monument_order=[f'c{i:03d}' for i in range(101,121)]+[f'c{i:03d}' for i in list(range(1,101))+list(range(121,254))]
 q_church,a_church=select_freetext_question(ranking=ranking(church_order),evidence=evidence(),policy=policy(),description='Una calle cualquiera',turns=[])
 q_monument,a_monument=select_freetext_question(ranking=ranking(monument_order),evidence=evidence(),policy=policy(),description='Una calle cualquiera',turns=[])
 assert (q_church.family,q_monument.family)==('church','monument')
 assert a_church['selected_intent_key']=='closed_observability:church' and a_monument['selected_intent_key']=='closed_observability:monument'

def test_score_magnitude_without_order_does_not_change_question():
 first=select_freetext_question(ranking=ranking(score_scale=1),evidence=evidence(),policy=policy(),description='Una calle cualquiera',turns=[])[0]
 second=select_freetext_question(ranking=ranking(score_scale=.2),evidence=evidence(),policy=policy(),description='Una calle cualquiera',turns=[])[0]
 assert first.intent_key==second.intent_key

def test_unknown_answer_blocks_used_family_but_allows_another():
 features=evidence().features_by_candidate
 for i in range(11,16):features[f'c{i:03d}']=(CandidateFeature('monument','monumento',(f'node/monument/{i}',),False),)
 index=F3EvidenceIndex(dataset_id='audit',features_by_candidate=features,source_hashes={});used=[{'question':{'family':'church'},'answer':{'literal':'No lo sé'}}]
 question,audit=select_freetext_question(ranking=ranking(),evidence=index,policy=policy(),description='Una calle cualquiera',turns=used)
 assert question.family=='monument';assert 'already_used' in next(row for row in audit['options'] if row['family']=='church')['discard_reasons']

def test_shared_feature_abstains_when_no_unknown_hypotheses():
 features={f'c{i:03d}':(CandidateFeature('church','iglesia',(f'node/{i}',),False),) for i in range(1,254)};index=F3EvidenceIndex(dataset_id='audit',features_by_candidate=features,source_hashes={})
 question,audit=select_freetext_question(ranking=ranking(),evidence=index,policy=policy(),description='Una calle cualquiera',turns=[])
 assert question is None;option=next(row for row in audit['options'] if row['family']=='church');assert 'no_unknown_hypotheses' in option['discard_reasons']
