import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.run_i20_v10_bounded_pilot import prepare_preflight


ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/generated/i01-i20-assisted-annotation-v10/plan.json'
WORK=ROOT/'results/generated/i01-i20-annotation-workflow-v1'
MODEL=Path('/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8')


class BoundedPilotRealPreflightTests(unittest.TestCase):
    def setUp(self):
        if importlib.util.find_spec('xgrammar') is None:self.skipTest('xgrammar no instalado')
        self.temporary=tempfile.TemporaryDirectory(dir='/tmp/opencode');self.root=Path(self.temporary.name)/'pilot'
        subprocess.run(['python',str(ROOT/'scripts/prepare_i20_v10_bounded_pilot.py'),'--source-plan',str(SOURCE),'--annotation-fixture',str(WORK/'annotation/fixture.json'),'--scene-fixture',str(WORK/'scene-review/fixture.json'),'--instructions',str(WORK/'annotation/INSTRUCTIONS_ES.md'),'--output-root',str(self.root)],check=True,capture_output=True,text=True)
    def tearDown(self):self.temporary.cleanup()

    def preflight(self,**kwargs):
        return prepare_preflight(plan_path=self.root/'plan.json',authorization_path=self.root/'authorization.request.json',annotation_fixture_path=WORK/'annotation/fixture.json',scene_fixture_path=WORK/'scene-review/fixture.json',instructions_path=WORK/'annotation/INSTRUCTIONS_ES.md',model_path=MODEL,require_approval=False,verify_model_files=False,**kwargs)

    def test_real_serialized_plan_and_disabled_authorization_pass_preparation_mode(self):
        self.assertNotIn('torch',sys.modules);prepared=self.preflight();self.assertEqual([job.target_id for job in prepared['jobs']],['I02','I03','I04']);self.assertFalse(prepared['authorization']['approved']);self.assertFalse(prepared['runtime_root'].exists());self.assertNotIn('torch',sys.modules)

    def test_real_preflight_rejects_existing_empty_or_nonempty_runtime(self):
        runtime=self.root/json.loads((self.root/'plan.json').read_text())['runtime_relative_path'];runtime.mkdir()
        with self.assertRaisesRegex(ValueError,'runtime'):self.preflight()
        (runtime/'file').write_text('x')
        with self.assertRaisesRegex(ValueError,'runtime'):self.preflight()

    def test_real_preflight_rejects_tampered_targets_authorization_and_budget(self):
        for mutate in ('missing','wrong_type','reordered','duplicate','auth_targets','budget','scenes','retry','resume','continue'):
            with self.subTest(mutate=mutate):
                plan=json.loads((self.root/'plan.json').read_text());auth=json.loads((self.root/'authorization.request.json').read_text())
                if mutate=='missing':plan.pop('ordered_target_ids')
                elif mutate=='wrong_type':plan['ordered_target_ids']='I02'
                elif mutate=='reordered':plan['ordered_target_ids']=['I03','I02','I04']
                elif mutate=='duplicate':plan['ordered_target_ids']=['I02','I02','I04']
                elif mutate=='auth_targets':auth['target_ids']=['I02','I04','I03']
                elif mutate=='budget':plan['budget']['maximum_total_future_calls']=4
                elif mutate=='scenes':auth['maximum_scene_calls']=1
                elif mutate=='retry':auth['retry_permitted']=True
                elif mutate=='resume':auth['resume_permitted']=True
                else:auth['continue_after_failure']=True
                (self.root/'plan.bad.json').write_text(json.dumps(plan));(self.root/'auth.bad.json').write_text(json.dumps(auth))
                with self.assertRaises(Exception):prepare_preflight(plan_path=self.root/'plan.bad.json',authorization_path=self.root/'auth.bad.json',annotation_fixture_path=WORK/'annotation/fixture.json',scene_fixture_path=WORK/'scene-review/fixture.json',instructions_path=WORK/'annotation/INSTRUCTIONS_ES.md',model_path=MODEL,require_approval=False,verify_model_files=False)


if __name__=='__main__':unittest.main()
