import json
import tempfile
import unittest
from pathlib import Path

from scripts.replay_i20_scene_probe_cpu import replay


ROOT=Path(__file__).resolve().parents[1]
V4=ROOT/'results/generated/i01-i20-assisted-annotation-v4'
WORK=ROOT/'results/generated/i01-i20-annotation-workflow-v1'
ATTEMPT_ROOT=V4/'diagnostics/attempts/scene-scene-pair-sha256-491542572c527bd93789931b88ae736a7c96dd82564605aa41ce7ff1d2b5f8dd/attempt-001'


class I20V4CpuReplayTests(unittest.TestCase):
    def test_real_v4_raw_replays_complete_post_generation_pipeline(self):
        result=replay(plan_path=V4/'plan.json',annotation_fixture_path=WORK/'annotation/fixture.json',scene_fixture_path=WORK/'scene-review/fixture.json',attempt_path=ATTEMPT_ROOT/'attempt.json',raw_path=ATTEMPT_ROOT/'raw.json')
        self.assertEqual(result['source']['raw_output_sha256'],'a7f8f659a97bbcb0ccca047141c4989cc78bc9062ccce43cc64817d60ea55942')
        self.assertTrue(result['simulation']['result_exists']);self.assertFalse(result['simulation']['failure_exists']);self.assertEqual(result['simulation']['checkpoint_result_frames'],1);self.assertTrue(result['simulation']['recovered_without_callback']);self.assertEqual(result['simulation']['generation_calls'],0)
        self.assertEqual(result['ledger'],{'attempted':1,'completed':1,'failed':0,'raw_preserved':1,'unterminated':0})

    def test_replay_rejects_tampered_raw_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'raw.json';doc=json.loads((ATTEMPT_ROOT/'raw.json').read_text());doc['raw_output']+=' ';path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'hash de raw'):replay(plan_path=V4/'plan.json',annotation_fixture_path=WORK/'annotation/fixture.json',scene_fixture_path=WORK/'scene-review/fixture.json',attempt_path=ATTEMPT_ROOT/'attempt.json',raw_path=path)


if __name__=='__main__':unittest.main()
