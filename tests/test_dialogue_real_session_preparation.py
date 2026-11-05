import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_interactive_dialogue import load_multiturn_policy
from src.tfg_phase0.interactive_dialogue_multiturn import multiturn_session_id

ROOT=Path(__file__).resolve().parents[1]

class SessionPreparationTests(unittest.TestCase):
    def test_session_id_matches_orchestrator_formula(self):
        gallery,config=load_multiturn_policy(ROOT/'config/interactive_dialogue_multiturn.json');first=multiturn_session_id(session_label='operator-session',description='Descripción aportada por operador',language='es',gallery_id=gallery,config=config);second=multiturn_session_id(session_label='operator-session',description='Descripción aportada por operador',language='es',gallery_id=gallery,config=config);self.assertEqual(first,second);self.assertTrue(first.startswith('dialogue-session-v2-sha256-'))
    def test_pending_template_reports_operator_fields_without_worker(self):
        completed=subprocess.run([sys.executable,str(ROOT/'scripts/validate_dialogue_v3_real_session.py'),'--config',str(ROOT/'config/dialogue_v3_real_session.template.json')],capture_output=True,text=True);self.assertEqual(completed.returncode,2);report=json.loads(completed.stdout);self.assertEqual(report['status'],'SESSION_PREPARATION_PENDING');self.assertEqual(set(report['missing_operator_fields']),{'session_label','initial_description','intent_family','observer_manifest','clip_weights','visual_model_dir'});self.assertFalse(report['gpu_used']);self.assertFalse(report['worker_executed'])
    def test_session_id_can_be_derived_before_manifest_exists(self):
        with tempfile.TemporaryDirectory() as t:
            doc=json.loads((ROOT/'config/dialogue_v3_real_session.template.json').read_text());doc['session_label']='operator-session';doc['initial_description']='Descripción literal del operador';path=Path(t)/'session.json';path.write_text(json.dumps(doc));completed=subprocess.run([sys.executable,str(ROOT/'scripts/validate_dialogue_v3_real_session.py'),'--config',str(path)],capture_output=True,text=True);self.assertEqual(completed.returncode,2);report=json.loads(completed.stdout);self.assertTrue(report['derived_session_id'].startswith('dialogue-session-v2-sha256-'));self.assertIn('observer_manifest',report['missing_operator_fields'])
    def test_manifest_preparer_requires_complete_metadata_and_writes_hash(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);image=root/'observer.png';
            from PIL import Image
            Image.new('RGB',(4,4),'white').save(image);output=root/'manifest.json';session='dialogue-session-v2-sha256-'+'a'*64;command=[sys.executable,str(ROOT/'scripts/prepare_observer_view_manifest.py'),'--image',str(image),'--output',str(output),'--image-id','own-1','--source','operator-owned','--author','operator','--license-or-authorization','authorized for local TFG inference','--observer-relation-evidence','captured by observer at described viewpoint','--usage-restriction','local-only','--session-id',session,'--intent-family','square','--authorization-id','operator-auth-1'];completed=subprocess.run(command,capture_output=True,text=True);self.assertEqual(completed.returncode,0,completed.stderr);doc=json.loads(output.read_text());self.assertEqual(doc['sha256'],hashlib.sha256(image.read_bytes()).hexdigest());self.assertTrue(doc['authorized']);self.assertEqual(doc['observer_relation'],'observer_view')
    def test_manifest_preparer_does_not_create_partial_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);image=root/'observer.jpg';image.write_bytes(b'not-an-image');output=root/'manifest.json';completed=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_observer_view_manifest.py'),'--image',str(image),'--output',str(output)],capture_output=True,text=True);self.assertNotEqual(completed.returncode,0);self.assertFalse(output.exists())

if __name__=='__main__':unittest.main()
