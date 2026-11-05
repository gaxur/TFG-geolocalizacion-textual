import json,subprocess,sys,tempfile,unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts.run_dialogue_v3_phased import resume,retrieve,status,visual
from src.tfg_phase0.dialogue_phased_runtime import PhasedRunStore,PhasedRuntimeError,RunLock,immutable_json,status_document
from src.tfg_phase0.interactive_dialogue import DialoguePolicyConfig,FakeTextDialogueAdapter
from src.tfg_phase0.interactive_dialogue_multiturn import MultiTurnConfig,MultiTurnDialogueOrchestrator
from src.tfg_phase0.interactive_dialogue_visual import VisualMultiTurnConfig,VisualMultiTurnDialogueOrchestrator,validate_visual_session
from src.tfg_phase0.dialogue_visual_evidence import FakeVisualEvidenceProvider,VisualEvidencePolicy
from tests.test_interactive_dialogue_multiturn import AdaptiveRetriever,adaptive_evidence
from tests.test_interactive_dialogue_visual import image

ROOT=Path(__file__).resolve().parents[1]

def configuration():
    value=json.loads((ROOT/'config/dialogue_v3_real_session_madrid_prueba_visual_01.json').read_text());value['gallery_id']='fake-adaptive';return value
def v2_session():
    policy=DialoguePolicyConfig(reserve_size=6,cluster_radius_m=75,maximum_supported_fraction=.75);engine=MultiTurnDialogueOrchestrator(retriever=AdaptiveRetriever(),evidence=adaptive_evidence(),config=MultiTurnConfig(max_questions=3,policy=policy),text_adapter=FakeTextDialogueAdapter());return engine.start(session_label='phase-test',description='Una plaza')
def checkpoint(store,session=None,intent='square'):
    session=json.loads(json.dumps(session or v2_session()));config=store.configuration();session['session_id']=config['session_id'];ranking=session['initial_ranking'];doc={'schema_version':'1.0','contract_version':'dialogue-v3-retrieval-checkpoint-v1','checkpoint_id':'','status':'completed','session_id':config['session_id'],'session_label':config['session_label'],'initial_description_sha256':__import__('hashlib').sha256(config['initial_description'].encode()).hexdigest(),'intent_family':intent,'gallery_id':config['gallery_id'],'identities':{'test':True},'dialogue_policy':session['policy'],'ranking_initial':ranking,'candidate_ids':[r['candidate_id'] for r in ranking['results']],'scores':[r['cosine_similarity'] for r in ranking['results']],'timings_ms':{'phase_total':1},'configuration_sha256':store.load_state()['configuration_sha256'],'provenance':{'ground_truth_used':False},'session_v2':session};return store.checkpoint(doc)
def raw_checkpoint(store,session=None,intent='square'):
    relative,document=checkpoint(store,session,intent);(store.root/relative).unlink();document['checkpoint_id']='';return document
def authorization(root,session_id):
    path=root/'authorization.json';path.write_text(json.dumps({'schema_version':'1.0','contract_version':'dialogue-v3-phased-ct2l-gpu-authorization-v1','status':'OPERATOR_AUTHORIZED','session_id':session_id,'authorized_actions':['isolated CT2L retrieval on NVIDIA GB10'],'stable_swap_required':True,'automatic_retries':0,'authorization_source':'test'}));return path

class PhasedRuntimeTests(unittest.TestCase):
    def store(self,root):return PhasedRunStore.prepare(root,configuration())
    def test_prepare_and_status_never_load_models(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');doc=status_document(store);self.assertEqual(doc['status'],'prepared');self.assertEqual(doc['next_action'],'retrieve');self.assertEqual(doc['own_active_processes'],[])
    def test_checkpoint_is_atomic_immutable_and_valid(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');relative,doc=checkpoint(store);self.assertEqual(store.load_checkpoint(relative),doc)
            altered={**doc,'scores':[0.0]}
            with self.assertRaises(PhasedRuntimeError):immutable_json(store.root/relative,altered)
    def test_corrupt_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');relative,_=checkpoint(store);(store.root/relative).write_text('{')
            with self.assertRaises(PhasedRuntimeError):store.load_checkpoint(relative)
    def test_checkpoint_from_other_session_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');relative,doc=checkpoint(store);path=store.root/relative;value=json.loads(path.read_text());value['session_id']='dialogue-session-v2-sha256-'+'0'*64;path.write_text(json.dumps(value))
            with self.assertRaises(PhasedRuntimeError):store.load_checkpoint(relative)
    def test_retrieval_reservation_timeout_is_uncertain_and_not_retryable(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');store.transition(expected={'prepared'},phase='retrieval_reserved',next_action='review');store.transition(expected={'retrieval_reserved'},phase='retrieval_uncertain',next_action='review')
            with self.assertRaises(PhasedRuntimeError):store.transition(expected={'prepared'},phase='retrieval_reserved',next_action='review')
    def test_retrieve_supervises_child_and_commits_after_process_exit(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');document=raw_checkpoint(store)
            commands=[]
            def supervised(command,timeout,root):
                commands.append(command)
                (root/'result.json').write_text(json.dumps(document));return {'returncode':0,'timed_out':False}
            auth=authorization(Path(t),store.configuration()['session_id'])
            environment={'python_entrypoint':'/validated/bin/python'}
            with patch('scripts.run_dialogue_v3_phased.validate_ct2l_environment',return_value=environment) as validate_env,patch('scripts.run_dialogue_v3_phased.run_supervised',side_effect=supervised),patch('scripts.run_dialogue_v3_phased.compute_processes',return_value=[]),patch('scripts.run_dialogue_v3_phased.collect_stable_swap_samples',return_value=[{'system':{'ram_available_bytes':50*1024**3,'swap_total_bytes':100,'swap_used_bytes':99},'memory_pressure':{'status':'VERIFIED','some':{'avg10':0},'full':{'avg10':0}},'vmstat':{'pswpin':0,'pswpout':0,'pgmajfault':0,'pgscan_direct':0,'pgsteal_direct':0,'oom_kill':0},'compute_processes':[]}]*5),patch('scripts.run_dialogue_v3_phased.subprocess.run',return_value=Namespace(returncode=0,stdout='NAME\n')):result=retrieve(Namespace(run_root=store.root,timeout=10,child_command=None,authorization=auth))
            self.assertIsNotNone(validate_env.call_args.kwargs['session_config'])
            self.assertEqual(result,0);self.assertEqual(commands[0][0],'/validated/bin/python');state=store.load_state();self.assertEqual(state['phase'],'retrieved');self.assertIsNone(state['session_snapshot']);self.assertIsNotNone(state['retrieval_checkpoint'])
    def test_foreign_gpu_after_child_blocks_transition(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');document=raw_checkpoint(store)
            def supervised(command,timeout,root):(root/'result.json').write_text(json.dumps(document));return {'returncode':0,'timed_out':False}
            auth=authorization(Path(t),store.configuration()['session_id'])
            safe=[{'system':{'ram_available_bytes':50*1024**3,'swap_total_bytes':100,'swap_used_bytes':99},'memory_pressure':{'status':'VERIFIED','some':{'avg10':0},'full':{'avg10':0}},'vmstat':{'pswpin':0,'pswpout':0,'pgmajfault':0,'pgscan_direct':0,'pgsteal_direct':0,'oom_kill':0},'compute_processes':[]}]*5
            with patch('scripts.run_dialogue_v3_phased.validate_ct2l_environment',return_value={'python_entrypoint':'/validated/bin/python'}),patch('scripts.run_dialogue_v3_phased.run_supervised',side_effect=supervised),patch('scripts.run_dialogue_v3_phased.compute_processes',side_effect=[[],[{'pid':999}]]),patch('scripts.run_dialogue_v3_phased.collect_stable_swap_samples',return_value=safe),patch('scripts.run_dialogue_v3_phased.subprocess.run',return_value=Namespace(returncode=0,stdout='NAME\n')):result=retrieve(Namespace(run_root=store.root,timeout=10,child_command=['fake-child'],authorization=auth))
            self.assertEqual(result,2);self.assertEqual(store.load_state()['phase'],'retrieval_uncertain')
    def test_ct2l_child_that_does_not_terminate_is_uncertain(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run')
            auth=authorization(Path(t),store.configuration()['session_id']);safe=[{'system':{'ram_available_bytes':50*1024**3,'swap_total_bytes':100,'swap_used_bytes':99},'memory_pressure':{'status':'VERIFIED','some':{'avg10':0},'full':{'avg10':0}},'vmstat':{'pswpin':0,'pswpout':0,'pgmajfault':0,'pgscan_direct':0,'pgsteal_direct':0,'oom_kill':0},'compute_processes':[]}]*5
            with patch('scripts.run_dialogue_v3_phased.validate_ct2l_environment',return_value={'python_entrypoint':'/validated/bin/python'}),patch('scripts.run_dialogue_v3_phased.run_supervised',return_value={'returncode':-15,'timed_out':True}),patch('scripts.run_dialogue_v3_phased.compute_processes',return_value=[]),patch('scripts.run_dialogue_v3_phased.collect_stable_swap_samples',return_value=safe),patch('scripts.run_dialogue_v3_phased.subprocess.run',return_value=Namespace(returncode=0,stdout='NAME\n')):result=retrieve(Namespace(run_root=store.root,timeout=1,child_command=['fake-child'],authorization=auth))
            self.assertEqual(result,2);self.assertEqual(store.load_state()['phase'],'retrieval_uncertain')
    def test_environment_failure_happens_before_reservation(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');auth=authorization(Path(t),store.configuration()['session_id'])
            with patch('scripts.run_dialogue_v3_phased.validate_ct2l_environment',side_effect=RuntimeError('clip missing')):
                with self.assertRaises(RuntimeError):retrieve(Namespace(run_root=store.root,timeout=10,child_command=['fake'],authorization=auth))
            self.assertEqual(store.load_state()['phase'],'prepared');self.assertFalse(any((store.root/'attempts').iterdir()))
    def test_explicit_retrieval_failure_is_terminal(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');store.transition(expected={'prepared'},phase='retrieval_reserved',next_action='review');store.transition(expected={'retrieval_reserved'},phase='retrieval_failed',next_action='review');self.assertEqual(store.load_state()['next_action'],'review')
    def test_snapshot_resume_does_not_require_ct2l(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');relative,_=checkpoint(store);snap=store.snapshot(v2_session());store.transition(expected={'prepared'},phase='retrieved',next_action='resume',retrieval_checkpoint=relative,session_snapshot=snap);self.assertEqual(store.load_snapshot(snap)['status'],'awaiting_answer')
    def test_intent_mismatch_routes_to_answer_without_visual(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);store=self.store(root/'run');relative,doc=checkpoint(store,intent='church');store.transition(expected={'prepared'},phase='retrieved',next_action='resume',retrieval_checkpoint=relative);manifest,ref=__import__('src.tfg_phase0.dialogue_visual_evidence',fromlist=['load_observer_image_manifest']).load_observer_image_manifest(ROOT/configuration()['observer_manifest'],ROOT/'schemas/dialogue_observer_image_manifest.schema.json');provider=FakeVisualEvidenceProvider(images={'square':ref});policy=DialoguePolicyConfig(reserve_size=6,cluster_radius_m=75,maximum_supported_fraction=.75);engine=VisualMultiTurnDialogueOrchestrator(retriever=AdaptiveRetriever(),evidence=adaptive_evidence(),config=VisualMultiTurnConfig(MultiTurnConfig(max_questions=3,policy=policy),VisualEvidencePolicy(enabled=True,maximum_calls=1)),text_adapter=FakeTextDialogueAdapter(),visual_provider=provider);session=engine.from_base_session(doc['session_v2']);self.assertNotEqual(session['turns'][-1]['question']['feature'],'square');self.assertEqual(session['visual_evidence'],[])
    def test_pending_human_answer_is_not_invented(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');relative,_=checkpoint(store);snap=store.snapshot(v2_session());store.transition(expected={'prepared'},phase='awaiting_answer',next_action='answer',retrieval_checkpoint=relative,session_snapshot=snap);self.assertIsNone(store.load_state()['pending_answer'])
    def test_visual_reservation_without_authorization_does_not_call_worker(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');relative,_=checkpoint(store);store.transition(expected={'prepared'},phase='awaiting_visual',next_action='visual',retrieval_checkpoint=relative)
            with self.assertRaises(PhasedRuntimeError):visual(Namespace(run_root=store.root,authorize_gpu=False))
            state=store.load_state();self.assertEqual(state['phase'],'awaiting_visual');self.assertIsNone(state['visual_attempt'])
    def test_visual_uncertain_blocks_duplicate(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');store.transition(expected={'prepared'},phase='awaiting_visual',next_action='visual');attempt={'attempt_id':'a','status':'uncertain','authorized':True};store.transition(expected={'awaiting_visual'},phase='visual_uncertain',next_action='review',visual_attempt=attempt)
            with self.assertRaises(PhasedRuntimeError):visual(Namespace(run_root=store.root,authorize_gpu=True))
    def test_visual_completed_budget_blocks_second_call(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');attempt={'attempt_id':'a','status':'completed','authorized':True};store.transition(expected={'prepared'},phase='awaiting_answer',next_action='answer',visual_attempt=attempt)
            with self.assertRaises(PhasedRuntimeError):visual(Namespace(run_root=store.root,authorize_gpu=True))
    def test_lock_prevents_concurrent_owner(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run')
            with RunLock(store.root):
                with self.assertRaises(BlockingIOError):
                    with RunLock(store.root):pass
    def test_fake_visual_mode_compatibility(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ref=image(root);provider=FakeVisualEvidenceProvider(images={'monument':ref},scenarios={'monument':{'state':'supported','observed_evidence':'visible'}});policy=DialoguePolicyConfig(reserve_size=6,cluster_radius_m=75,maximum_supported_fraction=.75);engine=VisualMultiTurnDialogueOrchestrator(retriever=AdaptiveRetriever(),evidence=adaptive_evidence(),config=VisualMultiTurnConfig(MultiTurnConfig(max_questions=1,policy=policy),VisualEvidencePolicy(enabled=True)),text_adapter=FakeTextDialogueAdapter(),visual_provider=provider);session=engine.start(session_label='fake',description='Una calle');validate_visual_session(session);self.assertEqual(len(session['visual_evidence']),1)
    def test_status_cli_is_cpu_only(self):
        with tempfile.TemporaryDirectory() as t:
            store=self.store(Path(t)/'run');completed=subprocess.run([sys.executable,str(ROOT/'scripts/run_dialogue_v3_phased.py'),'status','--run-root',str(store.root)],capture_output=True,text=True);self.assertEqual(completed.returncode,0);self.assertEqual(json.loads(completed.stdout)['status'],'prepared')

if __name__=='__main__':unittest.main()
