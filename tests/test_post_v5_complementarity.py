import json
import unittest
from pathlib import Path

from src.tfg_phase0.post_v5_complementarity import validate_ablation_plan,validate_alternative_matrix,validate_complementarity_audit,validate_independent_protocol

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'results/generated/post-v5-complementarity-audit'

class PostV5ComplementarityTests(unittest.TestCase):
    def test_generated_contracts(self):
        if not AUDIT.exists():self.skipTest('auditoría no materializada')
        cases=(("complementarity-audit.json",validate_complementarity_audit),("aligned-ablation-plan.json",validate_ablation_plan),("independent-transfer-protocol.json",validate_independent_protocol),("alternative-matrix.json",validate_alternative_matrix))
        for name,validator in cases:
            with self.subTest(name=name):validator(json.loads((AUDIT/name).read_text()))

    def test_manifest_keeps_experiments_blocked_and_heldout_closed(self):
        if not (AUDIT/'manifest.json').exists():self.skipTest('auditoría no materializada')
        document=json.loads((AUDIT/'manifest.json').read_text())
        self.assertEqual(document['status'],'completed_audit_experiments_blocked')
        self.assertFalse(document['execution']['gpu_used'])
        self.assertFalse(document['execution']['network_used'])
        self.assertFalse(document['execution']['heldout_opened'])
        self.assertEqual(document['decision']['confirmed_eligible_local_observations'],0)
        self.assertFalse(document['decision']['currently_executable'])

if __name__=='__main__':unittest.main()
