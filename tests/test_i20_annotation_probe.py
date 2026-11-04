import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.run_i20_assisted_annotation import selected_job_orders
from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob,finalize_json_atomic,run_resumable
from src.tfg_phase0.i20_assisted_annotation import annotation_draft_schema,cache_entry_id,canonical_bytes,content_id,normalize_annotation_draft,task_identity,validate_annotation_proposal_record
from src.tfg_phase0.immutable_attempt_ledger import ImmutableAttemptLedger,execute_immutable_attempt


ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'results/generated/i01-i20-annotation-workflow-v1'
V5=ROOT/'results/generated/i01-i20-assisted-annotation-v5'


class I20AnnotationProbeTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((V5/'plan.json').read_text());self.fixture=json.loads((WORK/'annotation/fixture.json').read_text());self.first=self.fixture['observations'][0]

    def test_selects_only_first_annotation_and_no_scene(self):
        scenes,annotations=selected_job_orders(self.plan,annotation_probe=True)
        self.assertEqual(scenes,[]);self.assertEqual(annotations,[self.plan['jobs']['annotation_order'][0]]);self.assertEqual(annotations,['I01'])

    def test_probe_flags_are_mutually_exclusive(self):
        result=subprocess.run(['python','scripts/run_i20_assisted_annotation.py','--probe-first-scene-only','--probe-first-annotation-only'],cwd=ROOT,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('not allowed with argument',result.stderr)

    def test_annotation_schema_contract_ledger_checkpoint_and_report_cpu(self):
        schema=annotation_draft_schema();self.assertEqual(schema['properties']['claims']['minItems'],1);self.assertEqual(schema['properties']['orientation']['properties']['bearing_degrees']['type'],'null')
        description='Se observa una calle urbana con edificios.';text='una calle urbana';start=description.index(text)
        raw=json.dumps({'description_es':description,'claims':[{'kind':'scene_structure','text_es':text,'span':{'start':start,'end':start+len(text)},'observability':'direct','certainty':'certain','requires_ocr':False,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]}],'visible_text':[],'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None},'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False},'human_review_required':True},ensure_ascii=False,separators=(',',':'))
        model={'model_id':self.plan['generator']['model_id'],'revision':self.plan['generator']['model_revision'],'weight_sha256':self.plan['generator']['weight_sha256'],'processor_policy':self.plan['generator']['processor_policy'],'decoding':self.plan['generator']['decoding']}
        identity=task_identity(kind='annotation',target_id='I01',image_sha256=[self.first['reference_asset_sha256']],model=model,prompt_sha256=self.plan['generator']['annotation_prompt_sha256'],schema_sha256=self.plan['generator']['annotation_schema_sha256'],instructions_sha256=self.plan['source']['instructions_sha256']);cache_id=cache_entry_id(identity)
        def build(raw_output,metadata):
            draft=normalize_annotation_draft(json.loads(raw_output));record={'proposal_id':'','observation_id':'I01','reference_asset_id':self.first['reference_asset_id'],'reference_asset_sha256':self.first['reference_asset_sha256'],'proposal_status':'proposed','ai_draft':draft,'generation':{'input_identity_sha256':hashlib.sha256(canonical_bytes(identity)).hexdigest(),'cache_entry_id':cache_id,'raw_output_sha256':hashlib.sha256(raw_output.encode()).hexdigest(),'generated_at_utc':'2026-11-03T00:00:00Z','model_id':model['model_id'],'model_revision':model['revision']}};record['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',record,'proposal_id');validate_annotation_proposal_record(record,fixture_row=self.first);return {'query_id':None,'candidate_id':'annotation','image_id':'I01','claim_id':cache_id,'proposal':record}
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as temporary:
            root=Path(temporary);ledger=ImmutableAttemptLedger(root/'diagnostics',plan_id=self.plan['plan_id'],maximum_attempts=1);calls=[]
            record=execute_immutable_attempt(ledger=ledger,kind='annotation',target_id='I01',cache_entry_id=cache_id,now=lambda:'now',generate_raw=lambda:(calls.append(True) or (raw,{'generated_token_count':100,'terminated_by_eos':True,'reached_max_new_tokens':False})),parse_and_build=build)
            job=PlannedJob((None,'annotation','I01',cache_id),identity,None,True);checkpoint=root/'checkpoints/annotation-proposals.jsonl';rows=run_resumable(checkpoint_path=checkpoint,provenance={'plan_id':self.plan['plan_id'],'kind':'annotation'},jobs=[job],execute=lambda unused:record,policy_result=lambda unused:record)
            report={'schema_version':'1.0','contract_version':'i20-assisted-annotation-probe-report-v1','plan_id':self.plan['plan_id'],'probe_kind':'annotation','target_id':'I01','calls':ledger.summary(),'valid_annotation_proposals':len(rows),'valid_scene_proposals':0,'full_campaign_executed':False};finalize_json_atomic(output_path=root/'annotation-probe-report.json',document=report)
            recovered=[];again=run_resumable(checkpoint_path=checkpoint,provenance={'plan_id':self.plan['plan_id'],'kind':'annotation'},jobs=[job],execute=lambda unused:(recovered.append(True) or record),policy_result=lambda unused:record)
            paths=ledger.paths(kind='annotation',target_id='I01');self.assertEqual(calls,[True]);self.assertFalse(recovered);self.assertEqual(again,rows);self.assertTrue(paths.raw.exists());self.assertTrue(paths.result.exists());self.assertFalse(paths.failure.exists());self.assertEqual(len(checkpoint.read_text().splitlines()),2);self.assertTrue((root/'annotation-probe-report.json').exists());self.assertFalse((root/'checkpoints/scene-proposals.jsonl').exists())

    def test_claim_orientation_forbidden_and_identity_rejected(self):
        description='Se observa una calle urbana.';text='una calle urbana';start=description.index(text);draft=normalize_annotation_draft({'description_es':description,'claims':[{'kind':'scene_structure','text_es':text,'span':{'start':start,'end':start+len(text)},'observability':'direct','certainty':'certain','requires_ocr':False,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]}],'visible_text':[],'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None},'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False},'human_review_required':True})
        row={'proposal_id':'','observation_id':'I01','reference_asset_id':self.first['reference_asset_id'],'reference_asset_sha256':self.first['reference_asset_sha256'],'proposal_status':'proposed','ai_draft':draft,'generation':{'input_identity_sha256':'a'*64,'cache_entry_id':'i20-assist-cache-sha256-'+'b'*64,'raw_output_sha256':'c'*64,'generated_at_utc':'2026-11-03T00:00:00Z','model_id':'m','model_revision':'d'*40}};row['proposal_id']=content_id('i20-assist-annotation-proposal-sha256-',row,'proposal_id');validate_annotation_proposal_record(row,fixture_row=self.first)
        for mutation in ('forbidden','orientation','identity'):
            changed=json.loads(json.dumps(row))
            if mutation=='forbidden':changed['ai_draft']['osm']='x'
            elif mutation=='orientation':changed['ai_draft']['orientation']['cardinal_conversion_allowed']=True
            else:changed['proposal_id']='i20-assist-annotation-proposal-sha256-'+'0'*64
            with self.assertRaises(Exception):validate_annotation_proposal_record(changed,fixture_row=self.first)


if __name__=='__main__':unittest.main()
