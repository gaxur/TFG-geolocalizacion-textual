import tempfile,unittest
from pathlib import Path
from backend.atlas_api.dialogue_executor import SequentialDialogueExecutor
from src.tfg_phase0.interactive_dialogue import CandidateFeature,F3EvidenceIndex

class FakeSequential(SequentialDialogueExecutor):
 def __init__(self):
  self.max_questions=3;self.policy=__import__('src.tfg_phase0.interactive_dialogue',fromlist=['DialoguePolicyConfig']).DialoguePolicyConfig(reserve_size=6,cluster_radius_m=75,maximum_supported_fraction=.75);labels={'monument':'un monumento','church':'una iglesia','park':'un parque'};self.evidence=F3EvidenceIndex(dataset_id='fake',features_by_candidate={f'c{i}':(CandidateFeature(feature,labels[feature],(f'n/{i}',),False),) for i,feature in enumerate(labels,1)},source_hashes={});self.qwen=[];self.ct2l=[]
 def _qwen(self,*,query_id,round_index,spanish_text,root):self.qwen.append((round_index,spanish_text));return {'text':f'EN-{round_index}','text_sha256':str(round_index)*64,'duration_ms':1}
 def _ct2l(self,*,query_id,round_index,english,root):
  self.ct2l.append(round_index);return {'gallery_id':'madrid-50m','gallery_count':6,'requested_k':6,'effective_k':6,'ranking_method':'exhaustive_cosine','tie_break':'candidate_id_ascending','results':[{'rank':i,'candidate_id':f'c{i}','latitude':40+i/1000,'longitude':-3,'cosine_similarity':1-i/10} for i in range(1,7)]}
class ExecutorTests(unittest.TestCase):
 def test_three_answers_persist_rounds_and_close_without_fourth_inference(self):
  with tempfile.TemporaryDirectory() as tmp:
   executor=FakeSequential();state=executor.start(query_id='H27',description='Una calle',session_root=Path(tmp));self.assertEqual((len(executor.qwen),len(executor.ct2l)),(1,1))
   state=executor.answer(state=state,answer='No',answer_kind='negation',session_root=Path(tmp));state=executor.answer(state=state,answer='No',answer_kind='negation',session_root=Path(tmp));self.assertEqual((len(executor.qwen),len(executor.ct2l)),(3,3));state=executor.answer(state=state,answer='No',answer_kind='negation',session_root=Path(tmp));self.assertEqual(state['status'],'completed');self.assertEqual(state['stop_reason'],'max_questions_reached');self.assertEqual((len(executor.qwen),len(executor.ct2l)),(3,3));self.assertEqual(len(state['rounds']),3);self.assertEqual(len(state['rounds'][0]['ranking']['results']),6);self.assertIn('terminal_es_sha256',state)
if __name__=='__main__':unittest.main()
