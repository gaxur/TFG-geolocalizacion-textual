import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
V5=ROOT/'results/generated/mapillary/h26-h37-exploratory-v5'

class H26H37ExploratoryV5Tests(unittest.TestCase):
    def test_rankings_are_frozen_without_gt_and_preserve_top100(self):
        path=V5/'reliable-rankings.frozen.json'
        if not path.exists():self.skipTest('v5 no materializado')
        document=json.loads(path.read_text())
        self.assertFalse(document['protocol']['ground_truth_used'])
        self.assertTrue(document['protocol']['all_variants_frozen_before_evaluation'])
        for query in document['queries'].values():
            baseline=set(query['variants']['baseline'])
            self.assertEqual(len(baseline),100)
            for ranking in query['variants'].values():
                self.assertEqual(set(ranking),baseline)
                self.assertEqual(len(ranking),100)

    def test_top1_protected_never_changes_atlas_top1(self):
        path=V5/'reliable-rankings.frozen.json'
        if not path.exists():self.skipTest('v5 no materializado')
        document=json.loads(path.read_text())
        for query in document['queries'].values():
            self.assertEqual(query['variants']['top1_protected'][0],query['variants']['atlas_v3'][0])

    def test_manifest_does_not_replace_policy_or_use_external_resources(self):
        path=V5/'manifest.json'
        if not path.exists():self.skipTest('v5 no materializado')
        document=json.loads(path.read_text())
        self.assertEqual(document['status'],'completed_no_policy_replacement')
        self.assertFalse(document['protocol']['gpu_used'])
        self.assertFalse(document['protocol']['network_used'])
        self.assertFalse(document['decision']['policy_replacement'])

if __name__=='__main__':unittest.main()
