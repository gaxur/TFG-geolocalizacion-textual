import json
import unittest
from pathlib import Path

import jsonschema

from src.tfg_phase0.i20_preparation import EXPECTED_IDS,I20PreparationError,build_empty_annotation_package,build_empty_gt_package,build_empty_review_package,validate_annotation_package,validate_gt_package,validate_ledger_pair,validate_policy_freeze,validate_review_package

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/generated/i01-i20-preparation-v1'


class I20PreparationTests(unittest.TestCase):
    def test_schemas_are_valid_and_templates_are_empty(self):
        names=('i20_blind_ledger_submission','i20_blind_ledger_response','i20_annotation_package','i20_review_package','i20_ground_truth_package')
        for name in names:
            with self.subTest(name=name):jsonschema.Draft202012Validator.check_schema(json.loads((ROOT/f'schemas/{name}.schema.json').read_text()))
        schemas={name:json.loads((ROOT/f'schemas/{name}.schema.json').read_text()) for name in names}
        annotation=build_empty_annotation_package('a'*64);review=build_empty_review_package();gt=build_empty_gt_package()
        jsonschema.validate(annotation,schemas['i20_annotation_package'])
        jsonschema.validate(review,schemas['i20_review_package'])
        jsonschema.validate(gt,schemas['i20_ground_truth_package'])
        self.assertEqual(annotation['expected_observation_ids'],list(EXPECTED_IDS));self.assertEqual(annotation['observations'],[])
        validate_annotation_package(annotation);validate_review_package(review,annotation);validate_gt_package(gt,annotation)

    def test_ledger_rejects_reason_and_incomplete_decisions(self):
        candidates=[{'candidate_ref':f'00000000-0000-4000-8000-{i:012d}'} for i in range(12)]
        submission={'candidate_count':12,'candidates':candidates,'submission_id':'s','manifest_commitment':'sha256:'+'a'*64}
        decisions=[{'candidate_ref':row['candidate_ref'],'state':'CLEAR'} for row in candidates]
        response={'candidate_count':12,'decisions':sorted(decisions,key=lambda row:row['candidate_ref']),'submission_id':'s','manifest_commitment':submission['manifest_commitment']}
        self.assertEqual(validate_ledger_pair(submission,response)['CLEAR'],12)
        leaked=json.loads(json.dumps(response));leaked['decisions'][0]['reason']='same scene'
        with self.assertRaises(I20PreparationError):validate_ledger_pair(submission,leaked)
        incomplete=json.loads(json.dumps(response));incomplete['decisions'].pop();incomplete['candidate_count']=11
        with self.assertRaises(I20PreparationError):validate_ledger_pair(submission,incomplete)

    def test_generated_lineage_is_blocked_and_policy_roles_are_explicit(self):
        if not OUT.exists():self.skipTest('lineage I20 no materializado')
        annotation=json.loads((OUT/'annotation-template.json').read_text());review=json.loads((OUT/'review-template.json').read_text());gt=json.loads((OUT/'ground-truth-template.json').read_text());freeze=json.loads((OUT/'policy-freeze.json').read_text());manifest=json.loads((OUT/'manifest.json').read_text())
        validate_annotation_package(annotation);validate_review_package(review,annotation);validate_gt_package(gt,annotation);validate_policy_freeze(freeze)
        self.assertEqual(manifest['execution']['observations_created'],0)
        self.assertFalse(manifest['execution']['holdout_opened'])
        self.assertFalse(manifest['execution']['gpu_used'])
        self.assertFalse(manifest['decision']['acquisition_authorized'])
        atlas=next(row for row in freeze['policies'] if row['id']=='atlas_v3')
        self.assertFalse(atlas['fallback_counts_as_atlas_result'])
        self.assertFalse(atlas['historical_bundle_reusable_for_i20'])

if __name__=='__main__':unittest.main()
