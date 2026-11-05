import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.tfg_phase0.ct2l_isolated_environment import CT2LEnvironmentError,validate_ct2l_environment

ROOT=Path(__file__).resolve().parents[1]

class CT2LIsolatedEnvironmentTests(unittest.TestCase):
    def manifest(self):return json.loads((ROOT/'config/ct2l_isolated_runtime_cvgtext.json').read_text())
    def probe(self,manifest=None):
        manifest=manifest or self.manifest();return {'executable':'/usr/bin/python3.12','python':manifest['python_version'],'prefix':str((ROOT/manifest['environment_root']).resolve()),'base_prefix':'/usr','distributions':{name:{'version':version,'direct_url':json.dumps({'url':manifest['openai_clip']['repository'],'vcs_info':{'commit_id':manifest['openai_clip']['commit']}}) if name=='clip' else None} for name,version in manifest['distributions'].items()},'specs':{'clip':True,'torch':True}}
    def runner(self,probe=None,head=None):
        probe=probe or self.probe();head=head or self.manifest()['cvg_text']['commit'];return lambda command,**kwargs:SimpleNamespace(returncode=0,stdout=(json.dumps(probe) if '-c' in command else head+'\n'),stderr='')
    def validate(self,manifest=None,probe=None,head=None):
        manifest=manifest or self.manifest()
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'manifest.json';path.write_text(json.dumps(manifest))
            with patch('src.tfg_phase0.ct2l_isolated_environment.subprocess.run',side_effect=self.runner(probe,head)):return validate_ct2l_environment(path,ROOT)
    def test_real_child_startup_cpu(self):
        report=validate_ct2l_environment(ROOT/'config/ct2l_isolated_runtime_cvgtext.json',ROOT,session_config=ROOT/'config/dialogue_v3_real_session_madrid_prueba_visual_01.json');startup=report['child_startup'];self.assertEqual(startup['status'],'CHILD_STARTUP_CPU_PASS');self.assertFalse(startup['torch_imported']);self.assertFalse(startup['clip_imported']);self.assertFalse(startup['cuda_initialized']);self.assertFalse(startup['models_loaded'])
    def test_real_second_turn_child_startup_cpu(self):
        report=validate_ct2l_environment(ROOT/'config/ct2l_isolated_runtime_cvgtext.json',ROOT,session_config=ROOT/'results/generated/dialogue-v3-madrid-prueba-visual-01-phased-v3/configuration.json');startup=report['second_turn_child_startup'];self.assertEqual(startup['status'],'SECOND_TURN_CHILD_STARTUP_CPU_PASS');self.assertEqual(startup['answer_literal'],'Sí');self.assertEqual(startup['interpretation']['kind'],'affirmation');self.assertEqual(startup['claim']['feature'],'monument');self.assertEqual(startup['claim']['polarity'],'positive');self.assertEqual(startup['retrieval_request']['text'],'[ACLARACIONES VALIDADAS]\nLa persona indica que puede ver un monumento o elemento histórico.\n[DESCRIPCIÓN ORIGINAL]\nEstoy en una plaza y estoy rodeado de edificios con balcones.');self.assertFalse(startup['torch_imported']);self.assertFalse(startup['clip_imported'])
    def test_valid_environment_metadata_only(self):
        report=self.validate();self.assertEqual(report['status'],'CT2L_ISOLATED_ENV_CPU_PASS');self.assertFalse(report['cuda_initialized']);self.assertFalse(report['models_loaded']);self.assertEqual(report['openai_clip_commit'],self.manifest()['openai_clip']['commit'])
    def test_clip_distribution_absent(self):
        probe=self.probe();probe['distributions']['clip']=None
        with self.assertRaises(CT2LEnvironmentError):self.validate(probe=probe)
    def test_clip_distribution_wrong_version(self):
        probe=self.probe();probe['distributions']['clip']['version']='other'
        with self.assertRaises(CT2LEnvironmentError):self.validate(probe=probe)
    def test_clip_commit_incompatible(self):
        probe=self.probe();probe['distributions']['clip']['direct_url']=json.dumps({'url':'https://github.com/openai/CLIP.git','vcs_info':{'commit_id':'0'*40}})
        with self.assertRaises(CT2LEnvironmentError):self.validate(probe=probe)
    def test_cvg_text_commit_incompatible(self):
        with self.assertRaises(CT2LEnvironmentError):self.validate(head='0'*40)
    def test_wrong_interpreter_prefix(self):
        probe=self.probe();probe['prefix']='/tmp/other'
        with self.assertRaises(CT2LEnvironmentError):self.validate(probe=probe)
    def test_dependency_absent(self):
        probe=self.probe();probe['distributions']['torchvision']=None
        with self.assertRaises(CT2LEnvironmentError):self.validate(probe=probe)
    def test_checkpoint_hash_incorrect(self):
        manifest=self.manifest();manifest['ct2l_checkpoint']['sha256']='0'*64
        with self.assertRaises(CT2LEnvironmentError):self.validate(manifest=manifest,probe=self.probe(manifest))
    def test_clip_weights_hash_incorrect(self):
        manifest=self.manifest();manifest['clip_weights']['sha256']='0'*64
        with self.assertRaises(CT2LEnvironmentError):self.validate(manifest=manifest,probe=self.probe(manifest))
    def test_embedding_identity_incompatible(self):
        manifest=self.manifest();manifest['gallery']['id']='other'
        with self.assertRaises(CT2LEnvironmentError):self.validate(manifest=manifest,probe=self.probe(manifest))
    def test_child_startup_import_failure_is_explicit(self):
        manifest=self.manifest();probe=self.probe(manifest);calls=[SimpleNamespace(returncode=0,stdout=json.dumps(probe),stderr=''),SimpleNamespace(returncode=0,stdout=manifest['cvg_text']['commit']+'\n',stderr=''),SimpleNamespace(returncode=1,stdout='',stderr='ModuleNotFoundError: missing_transitive')]
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'manifest.json';path.write_text(json.dumps(manifest))
            with patch('src.tfg_phase0.ct2l_isolated_environment.subprocess.run',side_effect=calls):
                with self.assertRaisesRegex(CT2LEnvironmentError,'missing_transitive'):validate_ct2l_environment(path,ROOT,session_config=ROOT/'config/dialogue_v3_real_session_madrid_prueba_visual_01.json')

if __name__=='__main__':unittest.main()
