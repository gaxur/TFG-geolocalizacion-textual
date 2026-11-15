import hashlib,json,tempfile
from pathlib import Path
import pytest
from backend.atlas_api.freetext_sessions import FreeTextConflict,FreeTextSessionService,FreeTextUnavailable
from src.tfg_phase0.dialogue_freetext_v1 import FreeTextDialogueExecutor,FreeTextQuestion

def ranking(offset=0):return {'gallery_id':'madrid-50m','gallery_count':253,'requested_k':253,'effective_k':253,'ranking_method':'exhaustive_cosine','tie_break':'candidate_id_ascending','results':[{'rank':i,'candidate_id':f'c{i:03d}','latitude':40+i/10000,'longitude':-3,'cosine_similarity':1-i/1000-offset/10000} for i in range(1,254)]}
class Questions:
 def __init__(self):self.n=0
 def select(self,**kwargs):self.n+=1;return FreeTextQuestion(f'q{self.n}',f'f{self.n}','closed_observability',f'Pregunta {self.n}','test',(),(),(),(1,),{}),{'selected_intent_key':f'q{self.n}'}
class Qwen:
 def __init__(self):self.calls=[]
 def transform(self,**kwargs):self.calls.append(kwargs['stage']);return {'text':f"EN {kwargs['stage']}",'text_sha256':hashlib.sha256(f"EN {kwargs['stage']}".encode()).hexdigest()}
class Retriever:
 def __init__(self):self.calls=[]
 def retrieve(self,**kwargs):self.calls.append(kwargs['stage']);return ranking(len(self.calls))
class Executor:
 identity={'executor_sha256':'e'*64,'worker_sha256':'w'*64,'answer_parser_sha256':'p'*64,'text_transform_sha256':'t'*64,'freetext_executor_sha256':'r'*64,'freetext_core_sha256':'c'*64,'freetext_worker_sha256':'q'*64,'freetext_policy_sha256':'f'*64}
 def __init__(self):self.q=Qwen();self.r=Retriever();self.core=FreeTextDialogueExecutor(qwen=self.q,retriever=self.r,questions=Questions())
 def start(self,*,query_id,description,session_root):return self.core.start(query_id=query_id,description=description)
 def answer(self,*,state,answer,answer_kind,session_root):return self.core.answer(state=state,answer_literal=answer)
def fixture(root,approved=False):
 auth=root/'auth';auth.mkdir();images=root/'images';images.mkdir();sessions=root/'sessions';(images/'h27.jpg').write_bytes(b'image');executor=Executor();description='Descripción H27';plan=auth/'plan.json';plan.write_text(json.dumps({'experimental_query_id':'X-DIALOGUE-FREETEXT-H27-01','description_es':description}));document={'contract_version':'atlas-dialogue-freetext-authorization-v1','authorization_id':'auth-freetext','status':'OPERATOR_AUTHORIZED' if approved else 'PENDING_OPERATOR_AUTHORIZATION','approved':approved,'experimental_query_id':'X-DIALOGUE-FREETEXT-H27-01','source_query_id':'H27','description_sha256':hashlib.sha256(description.encode()).hexdigest(),'reference_image_filename':'h27.jpg','reference_image_sha256':hashlib.sha256(b'image').hexdigest(),'plan_file':'plan.json','plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'policy_id':'dialogue-vpr-freetext-v1','maximum_questions':3,'maximum_qwen_loads':4,'maximum_qwen_calls':4,'maximum_ct2l_loads':4,'maximum_ct2l_calls':4,'automatic_retries':0,'memory_policy':'stable-swap-v2','network_permitted':False,'ground_truth_permitted':False,'references_permitted':False,'vlm_permitted':False,'h38_h61_permitted':False,'semantic_parser_permitted':False,'literal_transcript_required':True,'full_e0_e3_required':True,'reusable_for_other_session':False,'core_sha256':'c'*64,'runtime_executor_sha256':'r'*64,'qwen_worker_sha256':'q'*64,'policy_sha256':'f'*64,'executor_sha256':'e'*64,'worker_sha256':'w'*64,'answer_parser_sha256':'p'*64,'text_transform_sha256':'t'*64};(auth/'authorization.json').write_text(json.dumps(document));service=FreeTextSessionService(session_root=sessions,image_root=images,authorization_root=auth,authorization_file='authorization.json',executor=executor,enabled=True);return service,executor,sessions
def test_pending_blocks_before_session_or_calls():
 with tempfile.TemporaryDirectory() as tmp:
  service,executor,sessions=fixture(Path(tmp),False)
  with pytest.raises(FreeTextUnavailable):service.start('X-DIALOGUE-FREETEXT-H27-01','Descripción H27')
  assert not list(sessions.glob('dialogue-freetext-*'));assert executor.q.calls==executor.r.calls==[]
def test_persists_recovers_e0_e3_and_consumes_once():
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);service,executor,sessions=fixture(root,True);doc=service.start('X-DIALOGUE-FREETEXT-H27-01','Descripción H27');sid=doc['session_id'];assert service.load(sid)['session_sha256']==doc['session_sha256']
  for answer in ('Respuesta 1','No sé','A mi izquierda'):doc=service.answer(sid,answer)
  assert doc['status']=='completed';assert doc['state']['final_stage']=='E3';assert executor.q.calls==executor.r.calls==['E0','E1','E2','E3'];public=service.public(doc);assert [x['stage'] for x in public['stage_snapshots']]==['E0','E1','E2','E3'];assert all(len(x['results'])==10 for x in public['stage_snapshots']);assert public['turns'][1]['answer_literal']=='No sé'
  recreated=FreeTextSessionService(session_root=sessions,image_root=root/'images',authorization_root=root/'auth',authorization_file='authorization.json',executor=executor,enabled=True);assert recreated.pilot()['authorization_status']=='consumed'
  with pytest.raises(FreeTextConflict):recreated.start('X-DIALOGUE-FREETEXT-H27-01','Descripción H27')
def test_tampered_session_fails_closed():
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);service,executor,sessions=fixture(root,True);doc=service.start('X-DIALOGUE-FREETEXT-H27-01','Descripción H27');path=sessions/doc['session_id']/'session.json';value=json.loads(path.read_text());value['description_es']='alterada';path.write_text(json.dumps(value))
  with pytest.raises(FreeTextConflict):service.load(doc['session_id'])
