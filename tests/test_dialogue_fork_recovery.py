import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from src.tfg_phase0.dialogue_phased_runtime import PhasedRunStore,PhasedRuntimeError,file_sha
from src.tfg_phase0.ct2l_isolated_environment import validate_ct2l_environment

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/generated/dialogue-v3-madrid-prueba-visual-01-phased-v3'
REASON='second_turn_child_import_failure_fixed'

class ForkRecoveryTests(unittest.TestCase):
    def roots(self,temporary):
        parent=Path(temporary);source=parent/'source';target=parent/'target';shutil.copytree(SOURCE,source);return source,target
    def test_valid_fork_preserves_session_checkpoint_snapshot_and_answer(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);source_hash=file_sha(source/'state.json');store,created=PhasedRunStore.fork_recovery(source,target,REASON);self.assertTrue(created);value=store.validate_recovery_fork();state=value['state'];lineage=value['lineage'];self.assertEqual(state['phase'],'retrieved');self.assertEqual(state['next_action'],'retrieve');self.assertEqual(state['pending_answer']['literal'],'Sí');self.assertEqual(state['session_id'],value['snapshot']['session_id']);self.assertEqual(value['checkpoint']['checkpoint_id'],lineage['parent_checkpoint_id']);self.assertEqual(file_sha(source/'state.json'),source_hash);self.assertFalse(lineage['authorizations_reused']);self.assertEqual(list((target/'attempts').iterdir()),[]);self.assertEqual(list(target.glob('*authorization*.json')),[])
    def test_idempotent_same_fork(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);first,created=PhasedRunStore.fork_recovery(source,target,REASON);second,created_again=PhasedRunStore.fork_recovery(source,target,REASON);self.assertTrue(created);self.assertFalse(created_again);self.assertEqual(first.load_state(),second.load_state())
    def test_nonterminal_source_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);state=json.loads((source/'state.json').read_text());state['phase']='retrieved';state['next_action']='retrieve';(source/'state.json').write_text(json.dumps(state))
            with self.assertRaises(PhasedRuntimeError):PhasedRunStore.fork_recovery(source,target,REASON)
            self.assertFalse(target.exists())
    def test_corrupt_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);state=json.loads((source/'state.json').read_text());(source/state['retrieval_checkpoint']).write_text('{}')
            with self.assertRaises(Exception):PhasedRunStore.fork_recovery(source,target,REASON)
            self.assertFalse(target.exists())
    def test_corrupt_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);state=json.loads((source/'state.json').read_text());(source/state['session_snapshot']).write_text('{')
            with self.assertRaises(PhasedRuntimeError):PhasedRunStore.fork_recovery(source,target,REASON)
    def test_corrupt_pending_answer_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);state=json.loads((source/'state.json').read_text());state['pending_answer']['sha256']='0'*64;(source/'state.json').write_text(json.dumps(state))
            with self.assertRaises(PhasedRuntimeError):PhasedRunStore.fork_recovery(source,target,REASON)
    def test_existing_incompatible_destination_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);target.mkdir();(target/'lineage.json').write_text('{}')
            with self.assertRaises(Exception):PhasedRunStore.fork_recovery(source,target,REASON)
    def test_publication_failure_leaves_no_target_or_stage(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t)
            with patch('src.tfg_phase0.dialogue_phased_runtime.rename_noreplace',side_effect=OSError('publish failed')):
                with self.assertRaises(OSError):PhasedRunStore.fork_recovery(source,target,REASON)
            self.assertFalse(target.exists());self.assertEqual(list(target.parent.glob('.target.fork-*')),[])
    def test_recovered_run_second_turn_startup_passes(self):
        with tempfile.TemporaryDirectory() as t:
            source,target=self.roots(t);store,_=PhasedRunStore.fork_recovery(source,target,REASON);report=validate_ct2l_environment(ROOT/'config/ct2l_isolated_runtime_cvgtext.json',ROOT,session_config=target/'configuration.json');self.assertEqual(report['second_turn_child_startup']['status'],'SECOND_TURN_CHILD_STARTUP_CPU_PASS');self.assertEqual(report['second_turn_child_startup']['answer_literal'],'Sí')

if __name__=='__main__':unittest.main()
