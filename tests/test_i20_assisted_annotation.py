import json
import hashlib
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import jsonschema

from src.tfg_phase0.i20_assisted_annotation import I20AssistedError,_record_schema,annotation_draft_schema,annotation_draft_schema_v2,annotation_prompt,cache_entry_id,content_id,normalize_annotation_draft,scene_draft_schema,scene_draft_schema_v2,scene_prompt,task_identity,validate_annotation_proposal_record,validate_annotation_proposals,validate_human_decisions,validate_plan,validate_scene_draft_contract,validate_scene_proposal_record,validate_scene_proposals
from src.tfg_phase0.i20_preparation import canonical_bytes

ROOT=Path(__file__).resolve().parents[1]
ASSIST=ROOT/'results/generated/i01-i20-assisted-annotation-v1'
ASSIST_V2=ROOT/'results/generated/i01-i20-assisted-annotation-v2'
WORK=ROOT/'results/generated/i01-i20-annotation-workflow-v1'

def load(path):return json.loads(path.read_text())

class I20AssistedAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.annotation=load(WORK/'annotation/fixture.json');self.scene=load(WORK/'scene-review/fixture.json');self.plan=load(ASSIST/'plan.json')

    def annotation_document(self):
        records=[]
        for fixture in self.annotation['observations']:
            description='Se observa una calle urbana.';start=description.index('una calle urbana');claim={'kind':'scene_structure','text_es':'una calle urbana','span':{'start':start,'end':start+len('una calle urbana')},'observability':'direct','certainty':'certain','requires_ocr':False,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]};draft=normalize_annotation_draft({'description_es':description,'claims':[claim],'visible_text':[],'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None},'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False},'human_review_required':True});row={'proposal_id':'','observation_id':fixture['observation_id'],'reference_asset_id':fixture['reference_asset_id'],'reference_asset_sha256':fixture['reference_asset_sha256'],'proposal_status':'proposed','ai_draft':draft,'generation':{'input_identity_sha256':'a'*64,'cache_entry_id':'i20-assist-cache-sha256-'+'b'*64,'raw_output_sha256':'c'*64,'generated_at_utc':'2026-11-03T00:00:00Z','model_id':'fixture-vlm','model_revision':'d'*40}};row['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',row,'proposal_id');records.append(row)
        doc={'schema_version':'1.0','contract_version':'i20-assisted-annotation-proposals-v1','artifact_id':'','plan_id':self.plan['plan_id'],'annotation_fixture_id':self.annotation['fixture_id'],'records':records};doc['artifact_id']=content_id('i20-assist-annotation-proposals-sha256-',doc,'artifact_id');return doc

    def scene_document(self):
        assets={row['observation_id']:row['reference_asset_sha256'] for row in self.annotation['observations']};records=[]
        for fixture in self.scene['records']:
            row={'proposal_id':'','pair_id':fixture['pair_id'],'left_observation_id':fixture['left_observation_id'],'right_observation_id':fixture['right_observation_id'],'left_reference_asset_sha256':assets[fixture['left_observation_id']],'right_reference_asset_sha256':assets[fixture['right_observation_id']],'proposal_status':'proposed','ai_draft':{'same_scene':'uncertain','distinctive_objects_shared':'uncertain','field_of_view_overlap':'uncertain','same_place_different_frame':'uncertain','decision':'REVIEW','justification_es':'La comparación requiere revisión humana.','uncertainties':['Perspectiva ambigua.'],'human_review_required':True},'generation':{'input_identity_sha256':'a'*64,'cache_entry_id':'i20-assist-cache-sha256-'+'b'*64,'raw_output_sha256':'c'*64,'generated_at_utc':'2026-11-03T00:00:00Z','model_id':'fixture-vlm','model_revision':'d'*40}};row['proposal_id']=content_id('i20-assist-scene-proposal-sha256-',row,'proposal_id');records.append(row)
        doc={'schema_version':'1.0','contract_version':'i20-assisted-scene-proposals-v1','artifact_id':'','plan_id':self.plan['plan_id'],'scene_fixture_sha256':self.scene['fixture_sha256'],'records':records};doc['artifact_id']=content_id('i20-assist-scene-proposals-sha256-',doc,'artifact_id');return doc

    def test_schemas_and_plan(self):
        for name in ('i20_assisted_scene_proposals.schema.json','i20_assisted_annotation_proposals.schema.json','i20_assisted_human_decisions.schema.json'):
            jsonschema.Draft202012Validator.check_schema(load(ROOT/'schemas'/name))
        validate_plan(self.plan,annotation_fixture=self.annotation,scene_fixture=self.scene)

    def test_guided_schemas_complete_with_real_lmfe_parser(self):
        try:
            from lmformatenforcer import JsonSchemaParser
        except ImportError:
            self.skipTest('lm-format-enforcer no instalado')
        scene={'same_scene':'uncertain','distinctive_objects_shared':'uncertain','field_of_view_overlap':'uncertain','same_place_different_frame':'uncertain','decision':'REVIEW','justification_es':'Revisión humana.','uncertainties':[], 'human_review_required':True}
        annotation={'description_es':'Se observa una calle urbana.','claims':[{'kind':'scene_structure','text_es':'una calle urbana','span':{'start':12,'end':28},'observability':'direct','certainty':'certain','requires_ocr':False,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]}], 'visible_text':[], 'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None}, 'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False}, 'human_review_required':True}
        for schema,example in ((scene_draft_schema(),scene),(annotation_draft_schema(),annotation)):
            self.assertNotIn('"const": true',json.dumps(schema))
            self.assertNotIn('"const": false',json.dumps(schema))
            parser=JsonSchemaParser(schema)
            for character in json.dumps(example,ensure_ascii=True,separators=(',',':')):
                self.assertIn(character,parser.get_allowed_characters())
                parser=parser.add_character(character)
            self.assertTrue(parser.can_end())

    def test_lmfe_boolean_enum_regression_is_detected(self):
        try:
            from lmformatenforcer import JsonSchemaParser
        except ImportError:
            self.skipTest('lm-format-enforcer no instalado')
        for schema in (scene_draft_schema_v2(),annotation_draft_schema_v2()):
            self.assertIn('"enum": [true]',json.dumps(schema))
        parser=JsonSchemaParser({'type':'object','required':['x'],'properties':{'x':{'enum':[True]}}})
        for character in '{"x":':
            self.assertIn(character,parser.get_allowed_characters())
            parser=parser.add_character(character)
        self.assertIn('T',parser.get_allowed_characters())
        self.assertNotIn('t',parser.get_allowed_characters())

    def test_contract_validation_rejects_invalid_generated_semantics(self):
        annotations=self.annotation_document();annotations['records'][0]['ai_draft']['human_review_required']=False
        with self.assertRaises(I20AssistedError):
            validate_annotation_proposals(annotations,plan=self.plan,fixture=self.annotation)
        scenes=self.scene_document();scenes['records'][0]['ai_draft'].pop('decision')
        with self.assertRaises(I20AssistedError):
            validate_scene_proposals(scenes,plan=self.plan,fixture=self.scene,annotation_fixture=self.annotation)
        with self.assertRaises(I20AssistedError):
            validate_scene_draft_contract(scenes['records'][0]['ai_draft'])

    def test_revised_plan_binds_runner_effective_schemas_and_prompts(self):
        plan=load(ASSIST_V2/'plan.json');generator=plan['generator']
        self.assertEqual(generator['scene_schema_sha256'],hashlib.sha256(canonical_bytes(scene_draft_schema_v2())).hexdigest())
        self.assertEqual(generator['annotation_schema_sha256'],hashlib.sha256(canonical_bytes(annotation_draft_schema_v2())).hexdigest())
        self.assertEqual(generator['scene_prompt_sha256'],hashlib.sha256(scene_prompt().encode()).hexdigest())
        self.assertEqual(generator['annotation_prompt_sha256'],hashlib.sha256(annotation_prompt().encode()).hexdigest())
        self.assertEqual(hashlib.sha256((ASSIST_V2/'scene-generation.schema.json').read_bytes()).hexdigest(),generator['scene_schema_sha256'])
        self.assertEqual(hashlib.sha256((ASSIST_V2/'annotation-generation.schema.json').read_bytes()).hexdigest(),generator['annotation_schema_sha256'])

    def test_valid_synthetic_proposals_and_human_pending(self):
        annotations=self.annotation_document();scenes=self.scene_document();validate_annotation_proposals(annotations,plan=self.plan,fixture=self.annotation);validate_scene_proposals(scenes,plan=self.plan,fixture=self.scene,annotation_fixture=self.annotation)
        proposal=annotations['records'][0];decision={'decision_id':'','target_kind':'annotation','target_id':proposal['observation_id'],'proposal_id':proposal['proposal_id'],'status':'pending','reviewer_pseudonym':'human-a','reviewed_at_utc':None,'human_revision':None,'reason_codes':[],'notes_es':None};decision['decision_id']=content_id('i20-assist-human-decision-sha256-',decision,'decision_id');doc={'schema_version':'1.0','contract_version':'i20-assisted-human-decisions-v1','artifact_id':'','plan_id':self.plan['plan_id'],'decisions':[decision]};doc['artifact_id']=content_id('i20-assist-human-decisions-sha256-',doc,'artifact_id');counts=validate_human_decisions(doc,scene_proposals=scenes,annotation_proposals=annotations);self.assertEqual(counts['pending'],1)

    def test_individual_record_validators_resolve_defs_and_nested_objects(self):
        annotations=self.annotation_document();scenes=self.scene_document();assets={row['observation_id']:row['reference_asset_sha256'] for row in self.annotation['observations']}
        validate_annotation_proposal_record(annotations['records'][0],fixture_row=self.annotation['observations'][0])
        validate_scene_proposal_record(scenes['records'][0],fixture_row=self.scene['records'][0],asset_sha256=assets)

    def test_individual_record_rejects_forbidden_identity_and_semantics(self):
        scenes=self.scene_document();assets={row['observation_id']:row['reference_asset_sha256'] for row in self.annotation['observations']};fixture=self.scene['records'][0]
        forbidden=json.loads(json.dumps(scenes['records'][0]));forbidden['ai_draft']['osm']='forbidden'
        with self.assertRaises(I20AssistedError):validate_scene_proposal_record(forbidden,fixture_row=fixture,asset_sha256=assets)
        identity=json.loads(json.dumps(scenes['records'][0]));identity['proposal_id']='i20-assist-scene-proposal-sha256-'+'0'*64
        with self.assertRaises(I20AssistedError):validate_scene_proposal_record(identity,fixture_row=fixture,asset_sha256=assets)
        semantic=json.loads(json.dumps(scenes['records'][0]));semantic['ai_draft'].update({'decision':'CLEAR','same_scene':'yes'});semantic['proposal_id']=content_id('i20-assist-scene-proposal-sha256-',semantic,'proposal_id')
        with self.assertRaises(I20AssistedError):validate_scene_proposal_record(semantic,fixture_row=fixture,asset_sha256=assets)

    def test_record_schema_rejects_missing_reference(self):
        schema=load(ROOT/'schemas/i20_assisted_scene_proposals.schema.json');broken=_record_schema(schema);broken['properties']['generation']={'$ref':'#/$defs/missing'}
        with self.assertRaises(jsonschema.exceptions._WrappedReferencingError):jsonschema.Draft202012Validator(broken).validate(self.scene_document()['records'][0])

    def test_unreadable_text_cannot_have_transcription(self):
        doc=self.annotation_document();draft=doc['records'][0]['ai_draft'];draft['visible_text']=[{'transcription_es':'Inventado','span':{'start':0,'end':2},'legibility':'unreadable','certainty':'certain'}];doc['records'][0]['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',doc['records'][0],'proposal_id');doc['artifact_id']=content_id('i20-assist-annotation-proposals-sha256-',doc,'artifact_id')
        with self.assertRaises(I20AssistedError):validate_annotation_proposals(doc,plan=self.plan,fixture=self.annotation)

    def test_cache_identity_changes_with_effective_inputs(self):
        model={'model_id':'m','revision':'a'*40,'weight_sha256':'b'*64,'decoding':{'do_sample':False,'temperature':0,'top_p':1,'max_new_tokens':20}}
        base=task_identity(kind='annotation',target_id='I01',image_sha256=['c'*64],model=model,prompt_sha256='d'*64,schema_sha256='e'*64,instructions_sha256='f'*64)
        changed=task_identity(kind='annotation',target_id='I01',image_sha256=['0'*64],model=model,prompt_sha256='d'*64,schema_sha256='e'*64,instructions_sha256='f'*64)
        self.assertNotEqual(cache_entry_id(base),cache_entry_id(changed))

    def test_pending_decision_is_not_acceptance(self):
        annotations=self.annotation_document();scenes=self.scene_document();proposal=annotations['records'][0];decision={'decision_id':'','target_kind':'annotation','target_id':proposal['observation_id'],'proposal_id':proposal['proposal_id'],'status':'pending','reviewer_pseudonym':'human-a','reviewed_at_utc':None,'human_revision':None,'reason_codes':[],'notes_es':None};decision['decision_id']=content_id('i20-assist-human-decision-sha256-',decision,'decision_id');doc={'schema_version':'1.0','contract_version':'i20-assisted-human-decisions-v1','artifact_id':'','plan_id':self.plan['plan_id'],'decisions':[decision]};doc['artifact_id']=content_id('i20-assist-human-decisions-sha256-',doc,'artifact_id');counts=validate_human_decisions(doc,scene_proposals=scenes,annotation_proposals=annotations);self.assertEqual(counts['reviewed'],0);self.assertEqual(counts['corrected'],0);self.assertEqual(counts['pending'],1)

    def test_assisted_interfaces_are_parallel_and_pending(self):
        manifest=load(ASSIST/'interfaces/interfaces-manifest.json');self.assertFalse(manifest['protocol']['original_human_workflow_modified']);self.assertEqual(manifest['protocol']['default_human_status'],'pending');self.assertFalse(manifest['protocol']['no_change_is_acceptance'])
        for relative,count in (('interfaces/scene-review/review-assisted.html',12),('interfaces/annotation/review-assisted.html',20)):
            html=(ASSIST/relative).read_text();self.assertIn('<option value="pending">pending</option>',html);self.assertIn('PROPUESTA ORIGINAL',html);self.assertNotIn('latitude',html);self.assertNotIn('longitude',html)
            blocks=[body for attrs,body in re.findall(r'<script([^>]*)>(.*?)</script>',html,flags=re.S|re.I) if 'application/json' not in attrs]
            for body in blocks:
                with tempfile.NamedTemporaryFile('w',suffix='.js') as stream:stream.write(body);stream.flush();result=subprocess.run(['node','--check',stream.name],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            fixture=load((ASSIST/relative).parent/'fixture.json');self.assertEqual(len(fixture['records'] if 'records' in fixture else fixture['observations']),count)

if __name__=='__main__':unittest.main()
