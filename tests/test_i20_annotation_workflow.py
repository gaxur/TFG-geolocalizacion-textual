import base64
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import jsonschema

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
except ImportError:
    Ed25519PrivateKey = None

from src.tfg_phase0.i20_annotation_workflow import I20WorkflowError,build_annotation_fixture,canonical_bytes,validate_freeze_readiness,validate_scene_review,verify_custodian_response

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'results/generated/i01-i20-annotation-workflow-v1'

class I20AnnotationWorkflowTests(unittest.TestCase):
    def test_scene_schema_and_generated_fixture_are_private(self):
        schema=json.loads((ROOT/'schemas/i20_scene_review.schema.json').read_text());jsonschema.Draft202012Validator.check_schema(schema)
        if not (WORK/'manifest.json').exists():self.skipTest('interfaces no materializadas')
        manifest=json.loads((WORK/'manifest.json').read_text());self.assertEqual(manifest['status'],'interfaces_ready_no_human_outputs')
        self.assertTrue(all(value is False for value in manifest['privacy'].values()))
        for folder in ('annotation','scene-review','review-a','review-b','adjudication'):
            fixture=(WORK/folder/'fixture.json').read_text().casefold()
            for forbidden in ('latitude','longitude','provider_record_id','sequence_id','quality_score','candidate_id','cosine_similarity'):
                self.assertNotIn(forbidden,fixture)
        names=[path.name for path in (WORK/'annotation/references').iterdir()]
        self.assertEqual(len(names),20)
        self.assertTrue(all(name.startswith('ref-') and 'primary' not in name for name in names))

    def test_generated_javascript_parses_and_has_visible_error_panel(self):
        if not (WORK/'manifest.json').exists():self.skipTest('interfaces no materializadas')
        pages=('annotation/annotate.html','scene-review/review-scenes.html','review-a/review.html','review-b/review.html','adjudication/adjudicate.html')
        for relative in pages:
            with self.subTest(page=relative):
                html=(WORK/relative).read_text()
                self.assertIn('id="init-error"',html)
                self.assertNotIn('export.onclick',html)
                blocks=[body for attrs,body in re.findall(r'<script([^>]*)>(.*?)</script>',html,flags=re.S|re.I) if 'application/json' not in attrs]
                self.assertTrue(blocks)
                for body in blocks:
                    with tempfile.NamedTemporaryFile('w',suffix='.js') as stream:
                        stream.write(body);stream.flush();result=subprocess.run(['node','--check',stream.name],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)

    def test_scene_fixture_has_twelve_pairs_and_all_images(self):
        path=WORK/'scene-review/fixture.json'
        if not path.exists():self.skipTest('fixture de escenas no materializada')
        fixture=json.loads(path.read_text());self.assertEqual(len(fixture['records']),12)
        for row in fixture['records']:
            self.assertTrue((WORK/'scene-review'/row['left_reference_path']).is_file())
            self.assertTrue((WORK/'scene-review'/row['right_reference_path']).is_file())

    def test_scene_clear_rejects_uncertainty_or_overlap(self):
        fixture={'fixture_sha256':'a'*64,'records':[{'pair_id':'scene-pair-sha256-'+'b'*64,'left_observation_id':'I01','right_observation_id':'I02'}]}
        base={'schema_version':'1.0','contract_version':'i20-scene-review-v1','package_id':'i20-scene-review-sha256-'+'c'*64,'fixture_sha256':'a'*64,'status':'submitted','reviewer_pseudonym':'human-a','reviewed_at_utc':'2026-11-03T00:00:00Z','records':[{'pair_id':'scene-pair-sha256-'+'b'*64,'left_observation_id':'I01','right_observation_id':'I02','same_scene':'uncertain','distinctive_objects_shared':'no','field_of_view_overlap':'no','same_place_different_frame':'no','decision':'CLEAR','notes_es':''}]}
        with self.assertRaises(I20WorkflowError):validate_scene_review(base,fixture)
        base['records'][0]['same_scene']='no';base['records'][0]['field_of_view_overlap']='yes'
        with self.assertRaises(I20WorkflowError):validate_scene_review(base,fixture)

    def test_genuine_custodian_signature_is_required(self):
        if Ed25519PrivateKey is None: self.skipTest('cryptography no disponible en este entorno')
        private=Ed25519PrivateKey.generate();public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw);refs=['00000000-0000-4000-8000-%012d'%i for i in range(12)];submission={'submission_id':'00000000-0000-4000-8000-000000000999','manifest_commitment':'sha256:'+'a'*64,'candidate_count':12,'candidates':[{'candidate_ref':ref} for ref in refs]};response={'protocol':'blind-exclusion-ledger/v1','submission_id':submission['submission_id'],'manifest_commitment':submission['manifest_commitment'],'policy_id':'i20-exclusion-policy-v1','candidate_count':12,'decisions':[{'candidate_ref':ref,'state':'CLEAR'} for ref in refs],'custodian_key_id':'synthetic-test-key','response_commitment':''};response['response_commitment']='sha256:'+hashlib.sha256(canonical_bytes({k:v for k,v in response.items() if k!='response_commitment'})).hexdigest();signature=private.sign(canonical_bytes(response));response['custodian_signature']='ed25519:'+base64.b64encode(signature).decode();receipt=verify_custodian_response(submission,response,public);self.assertTrue(receipt['all_active_candidates_clear'])
        altered=json.loads(json.dumps(response));altered['decisions'][0]['state']='EXCLUDE'
        with self.assertRaises(I20WorkflowError):verify_custodian_response(submission,altered,public)

    def test_current_freeze_readiness_is_blocked(self):
        if not (WORK/'manifest.json').exists():self.skipTest('interfaces no materializadas')
        fixture=json.loads((WORK/'scene-review/fixture.json').read_text());geo=json.loads((ROOT/'results/generated/i01-i20-remote-acquisition-v1/geographic-package.json').read_text());result=validate_freeze_readiness(annotation={'status':'missing','observations':[]},scene_review={'status':'missing','records':[]},scene_fixture=fixture,review={'status':'missing','reviews':[]},ledger_receipt=None,geographic=geo)
        self.assertFalse(result['ready']);self.assertIn('authentic_blind_ledger_receipt_missing',result['blockers']);self.assertIn('annotation_not_complete_and_frozen',result['blockers'])

if __name__=='__main__':unittest.main()
