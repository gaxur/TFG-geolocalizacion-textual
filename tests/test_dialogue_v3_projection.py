import json,subprocess,sys,unittest
from pathlib import Path

from src.tfg_phase0.interactive_dialogue_multiturn import project_visual_session_to_v2,validate_multiturn_session

ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT=ROOT/'results/generated/dialogue-v3-madrid-prueba-visual-01-phased-v3/snapshots/003-4a606abb8f120b1193806ac6544abbe90f86d6a0dde85447c5ccd68cdb86567f.json'

class DialogueProjectionTests(unittest.TestCase):
    def test_projection_preserves_base_contract_without_visual_imports(self):
        session=json.loads(SNAPSHOT.read_text());before=json.loads(json.dumps(session));projected=project_visual_session_to_v2(session);validate_multiturn_session(projected);self.assertEqual(session,before);self.assertEqual(projected['contract_version'],'interactive-dialogue-session-v2');self.assertNotIn('visual_evidence',projected);self.assertNotIn('source_conflicts',projected);self.assertNotIn('visual_policy',projected);self.assertNotIn('visual_evidence_id',projected['turns'][0]);self.assertFalse(projected['models']['vlm']['enabled']);self.assertEqual(projected['session_id'],session['session_id']);self.assertEqual(projected['initial_ranking'],session['initial_ranking'])
    def test_basic_projection_module_has_no_visual_or_jsonschema_dependency(self):
        code=f"import sys;sys.path.insert(0,{str(ROOT)!r});from src.tfg_phase0.interactive_dialogue_multiturn import project_visual_session_to_v2;assert 'src.tfg_phase0.interactive_dialogue_visual' not in sys.modules;assert 'src.tfg_phase0.dialogue_visual_evidence' not in sys.modules;assert 'jsonschema' not in sys.modules;assert 'torch' not in sys.modules;assert 'clip' not in sys.modules"
        completed=subprocess.run([sys.executable,'-I','-c',code],cwd=ROOT,capture_output=True,text=True);self.assertEqual(completed.returncode,0,completed.stderr)

if __name__=='__main__':unittest.main()
