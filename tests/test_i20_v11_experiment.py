import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from src.tfg_phase0.i20_assisted_annotation import annotation_evidence_draft_schema_v10,annotation_prompt_v10,content_id,materialize_annotation_evidence_draft
from src.tfg_phase0.i20_v11_experiment import DEVELOPMENT_TARGETS,annotation_prompt_v11,build_semantic_sidecar,select_blind_development_targets,semantic_sidecar_schema,validate_v11_ocr_policy


ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'results/generated/i01-i20-annotation-workflow-v1'


def raw_claim(requires_ocr=True):
    return {'description_es':'Se observa una fachada curva con balcones y el rótulo TIGER junto a una calle urbana.','claims':[{'kind':'visible_text','semantic_text_es':'El rótulo comercial legible es TIGER.','evidence_quote':'TIGER','observability':'direct','certainty':'certain','requires_ocr':requires_ocr,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]}],'visible_text':[{'transcription_es':'TIGER','evidence_quote':'TIGER','legibility':'readable','certainty':'certain'}],'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None},'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False},'human_review_required':True}


class I20V11ExperimentTests(unittest.TestCase):
    def test_prompt_is_minimal_variant_and_schema_is_unchanged(self):
        p10=annotation_prompt_v10();p11=annotation_prompt_v11();self.assertNotEqual(hashlib.sha256(p10.encode()).hexdigest(),hashlib.sha256(p11.encode()).hexdigest());self.assertIn('evidencias no textuales',p11);self.assertIn('No fuerces tipos ausentes',p11);self.assertIn('visible_text debe usar requires_ocr=true',p11);self.assertEqual(annotation_evidence_draft_schema_v10(),annotation_evidence_draft_schema_v10())

    def test_blind_selection_is_deterministic_and_metadata_only(self):
        annotation=json.loads((WORK/'annotation/fixture.json').read_text());scene=json.loads((WORK/'scene-review/fixture.json').read_text());self.assertEqual(select_blind_development_targets(annotation,scene),DEVELOPMENT_TARGETS);self.assertEqual(DEVELOPMENT_TARGETS,('I10','I12','I16'))

    def test_ocr_policy_detects_but_sidecar_records_incoherence(self):
        with self.assertRaisesRegex(Exception,'requires_ocr'):validate_v11_ocr_policy(raw_claim(False))
        source=raw_claim(False);draft=materialize_annotation_evidence_draft(source);proposal={'proposal_id':'','observation_id':'I10','reference_asset_sha256':'a'*64,'ai_draft':draft};proposal['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',proposal,'proposal_id');identity={'model_id':'m','model_revision':'b'*40,'weight_sha256':['c'*64],'prompt_sha256':'d'*64,'schema_sha256':'e'*64,'decoding_sha256':'f'*64,'input_identity_sha256':'1'*64,'raw_output_sha256':'2'*64};sidecar=build_semantic_sidecar(raw=source,proposal=proposal,generator_identity=identity);self.assertEqual(sidecar['claims'][0]['ocr_policy_status'],'incoherent_pending_review');jsonschema.Draft202012Validator(semantic_sidecar_schema()).validate(sidecar)

    def test_sidecar_links_semantic_literal_span_and_claim_id(self):
        source=raw_claim(True);draft=materialize_annotation_evidence_draft(source);proposal={'proposal_id':'','observation_id':'I10','reference_asset_sha256':'a'*64,'ai_draft':draft};proposal['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',proposal,'proposal_id');identity={'model_id':'m','model_revision':'b'*40,'weight_sha256':['c'*64],'prompt_sha256':'d'*64,'schema_sha256':'e'*64,'decoding_sha256':'f'*64,'input_identity_sha256':'1'*64,'raw_output_sha256':'2'*64};sidecar=build_semantic_sidecar(raw=source,proposal=proposal,generator_identity=identity);claim=sidecar['claims'][0];self.assertEqual(claim['semantic_text_es'],source['claims'][0]['semantic_text_es']);self.assertEqual(claim['evidence_quote'],'TIGER');self.assertEqual(source['description_es'][claim['span']['start']:claim['span']['end']],'TIGER');self.assertEqual(claim['claim_id'],draft['claims'][0]['claim_id']);self.assertEqual(claim['ocr_policy_status'],'coherent');self.assertTrue(sidecar['sidecar_id'].startswith('i20-semantic-sidecar-sha256-'))

    def test_sidecar_rejects_cardinality_or_literal_mismatch(self):
        source=raw_claim(True);draft=materialize_annotation_evidence_draft(source);identity={'model_id':'m','model_revision':'b'*40,'weight_sha256':['c'*64],'prompt_sha256':'d'*64,'schema_sha256':'e'*64,'decoding_sha256':'f'*64,'input_identity_sha256':'1'*64,'raw_output_sha256':'2'*64};proposal={'proposal_id':'i20-assist-annotation-proposal-sha256-'+'3'*64,'observation_id':'I10','reference_asset_sha256':'a'*64,'ai_draft':{**draft,'claims':[]}}
        with self.assertRaises(Exception):build_semantic_sidecar(raw=source,proposal=proposal,generator_identity=identity)

    def test_preparation_plan_budget_authorization_and_no_runtime(self):
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as temporary:
            output=Path(temporary)/'v11';result=__import__('subprocess').run(['python',str(ROOT/'scripts/prepare_i20_v11_experiment.py'),'--v10-plan',str(ROOT/'results/generated/i01-i20-assisted-annotation-v10/plan.json'),'--annotation-fixture',str(WORK/'annotation/fixture.json'),'--scene-fixture',str(WORK/'scene-review/fixture.json'),'--instructions',str(WORK/'annotation/INSTRUCTIONS_ES.md'),'--output-root',str(output)],capture_output=True,text=True,check=True);plan=json.loads((output/'plan.json').read_text());auth=json.loads((output/'authorization.request.json').read_text());self.assertEqual(plan['selection']['target_ids'],['I10','I12','I16']);self.assertEqual(plan['execution']['maximum_total_calls'],6);self.assertEqual(plan['execution']['maximum_generated_tokens_total'],12288);self.assertFalse(plan['execution']['retry_permitted']);self.assertFalse(auth['approved']);self.assertFalse(auth['gpu_authorized']);self.assertFalse(any(path.is_dir() and 'runtime' in path.name for path in output.iterdir()));self.assertEqual(len(json.loads((output/'human-review-template.json').read_text())['records']),3)


if __name__=='__main__':unittest.main()
