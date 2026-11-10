from __future__ import annotations
import hashlib,json,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.atlas_api.main import create_app
from backend.atlas_api.settings import Settings

class Retriever:
 gallery_ids=("madrid-50m",)
 def gallery_count(self,_):return 253
 def close(self):pass
class Executor:
 identity={"executor_sha256":"e"*64,"worker_sha256":"w"*64,"answer_parser_sha256":"p"*64,"text_transform_sha256":"t"*64}
 def __init__(self):self.starts=0;self.answers=0
 def start(self,*,query_id,description,session_root):
  self.starts+=1;return {"status":"awaiting_answer","turns":[{"index":1,"question":{"question":"¿Ves una plaza?","question_sha256":hashlib.sha256("¿Ves una plaza?".encode()).hexdigest(),"feature":"square"},"answer":None}],"rounds":[{"round":0,"ranking_sha256":"a"*64,"ranking":{"results":[]}}],"answers":[],"claims":[]}
 def answer(self,*,state,answer,answer_kind,session_root):
  self.answers+=1;value=json.loads(json.dumps(state));value["turns"][0]["answer"]={"literal":answer,"kind":answer_kind};value["answers"].append({"literal":answer});value["status"]="completed";value["stop_reason"]="max_questions_reached";return value
class FailingExecutor(Executor):
 def start(self,**kwargs):self.starts+=1;raise RuntimeError('test-only failure')

class DialogueApiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);images=root/'images';images.mkdir();image=images/'H27.jpg';image.write_bytes(b'jpeg');description='Descripción humana exacta.';cohort={"contract_version":"dialogue-development-cohort-v1","cohort_id":"cohort","queries":[{"query_id":"H27","description_es":description,"description_sha256":hashlib.sha256(description.encode()).hexdigest(),"reference_image":{"logical_path":"data/cache/mapillary/images/H27.jpg","sha256":hashlib.sha256(b'jpeg').hexdigest()}}]};cohort_path=root/'cohort.json';cohort_path.write_text(json.dumps(cohort));authorization=root/'authorization.json';authorization.write_text(json.dumps({"contract_version":"atlas-dialogue-session-authorization-v1","authorization_id":"auth-h27","status":"OPERATOR_AUTHORIZED","approved":True,"query_id":"H27","maximum_questions":3,"maximum_qwen_loads":3,"maximum_qwen_calls":3,"maximum_ct2l_loads":3,"maximum_ct2l_calls":3,"automatic_retries":0,"memory_policy":"stable-swap-v2","network_permitted":False,"ground_truth_permitted":False,"references_permitted":False,"vlm_permitted":False,"h38_h61_permitted":False,"cohort_sha256":hashlib.sha256(cohort_path.read_bytes()).hexdigest(),"description_sha256":hashlib.sha256(description.encode()).hexdigest(),"reference_image_sha256":hashlib.sha256(b'jpeg').hexdigest(),**Executor.identity}));settings=Settings(Path('runtime'),Path('config/madrid.yaml'),'a'*64,'clip',(),True,None,"Qwen/Qwen3-8B","b968826d9c46dd6066d109eabc6255188de91218",False,False,None,None,'baseline',False,cohort_path,root/'sessions',images,True,("H26",),authorization);self.executor=Executor();self.app=create_app(settings=settings,retriever_factory=lambda _:Retriever(),transformer_factory=lambda _:None,dialogue_executor=self.executor);self.client=TestClient(self.app);self.client.__enter__();self.description=description
 def tearDown(self):self.client.__exit__(None,None,None);self.tmp.cleanup()
 def test_official_description_image_persistence_and_resume(self):
  catalogue=self.client.get('/api/v1/dialogue/queries').json();self.assertTrue(catalogue['available']);self.assertTrue(catalogue['queries'][0]['image_available']);self.assertEqual(self.client.get('/api/v1/dialogue/queries/H27/image').content,b'jpeg')
  payload={"schema_version":"1.0","contract_version":"atlas-dialogue-start-request-v1","mode":"official","query_id":"H27","description_es":self.description};started=self.client.post('/api/v1/dialogue/sessions',json=payload);self.assertEqual(started.status_code,200);session=started.json();self.assertEqual(session['current_question']['turn_index'],1);self.assertEqual(self.executor.starts,1);self.assertEqual(self.client.get('/api/v1/dialogue/sessions/'+session['session_id']).json()['session_sha256'],session['session_sha256']);self.assertEqual(self.executor.starts,1)
  answer={"schema_version":"1.0","contract_version":"atlas-dialogue-answer-request-v1","answer_literal":"No","answer_kind":"negation","human_attested":True,"external_context_used":False};finished=self.client.post('/api/v1/dialogue/sessions/'+session['session_id']+'/answers',json=answer).json();self.assertEqual(finished['status'],'completed');self.assertEqual(self.executor.answers,1);stored=list((Path(self.tmp.name)/'sessions').glob('*/session.json'));self.assertEqual(len(stored),1);doc=json.loads(stored[0].read_text());self.assertEqual(doc['answers'][0]['literal'],'No');self.assertEqual(doc['image']['sha256'],hashlib.sha256(b'jpeg').hexdigest())
  self.assertEqual(self.client.post('/api/v1/dialogue/sessions',json=payload).status_code,503,'la autorización no puede crear una segunda sesión')
 def test_official_mismatch_completed_and_exploratory_separation(self):
  base={"schema_version":"1.0","contract_version":"atlas-dialogue-start-request-v1","mode":"official","query_id":"H27","description_es":"Cambiada"};self.assertEqual(self.client.post('/api/v1/dialogue/sessions',json=base).status_code,409);completed={**base,"query_id":"H26","description_es":"texto"};self.assertEqual(self.client.post('/api/v1/dialogue/sessions',json=completed).status_code,409);explore={**base,"mode":"exploratory","query_id":"X-prueba","description_es":"Texto libre"};response=self.client.post('/api/v1/dialogue/sessions',json=explore);self.assertEqual(response.status_code,503,'una autorización H27 no se reutiliza para una sesión exploratoria')
 def test_runtime_failure_is_persisted_and_never_retried(self):
  self.app.state.dialogue_service.executor=FailingExecutor();payload={"schema_version":"1.0","contract_version":"atlas-dialogue-start-request-v1","mode":"official","query_id":"H27","description_es":self.description}
  with self.assertRaises(RuntimeError):self.client.post('/api/v1/dialogue/sessions',json=payload)
  stored=list((Path(self.tmp.name)/'sessions').glob('*/session.json'));self.assertEqual(len(stored),1);document=json.loads(stored[0].read_text());self.assertEqual(document['status'],'failed');self.assertEqual(document['stop_reason'],'runtime_error_no_retry');self.assertEqual(document['failure']['stage'],'start');self.assertEqual(self.client.get('/api/v1/dialogue/sessions/'+document['session_id']).json()['status'],'failed');self.assertEqual(self.client.post('/api/v1/dialogue/sessions',json=payload).status_code,503)
