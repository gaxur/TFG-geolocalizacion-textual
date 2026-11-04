import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from src.tfg_phase0.quality_gated_visual_postprocessor import QualityGatedVisualPostprocessor
from src.tfg_phase0.visual_quality_gate import ManifestAssetResolver,ScriptedQualityVerifier,VisualQualityError,accepted_associations,freeze_quality_reserves,parse_quality_decision,quality_schema,quality_task_id,run_quality_replacement

ROOT=Path(__file__).resolve().parents[1]

class Claims:
    def __init__(self):self.calls=[]
    def verify(self,*,candidate_id,asset,claims):self.calls.append(asset.image_id);return [{'claim_id':c['claim_id'],'verdict':'unverifiable'} for c in claims]

class VisualQualityGateTests(unittest.TestCase):
    def policy(self):
        value=json.loads((ROOT/'config/visual_quality_gate_v1.json').read_text());value['enabled']=True;value['status']='fixture_authorized';value['limits'].update({'target_accepted_images_per_candidate':1,'maximum_images_inspected_per_candidate':3,'maximum_replacements_per_candidate':2,'maximum_quality_vlm_calls':10,'maximum_claim_vlm_calls':10,'maximum_wall_seconds':100});return value

    def test_schemas_and_strict_parser(self):
        for name in ('visual_image_quality_decision.schema.json','visual_quality_pipeline_result.schema.json'):
            jsonschema.Draft202012Validator.check_schema(json.loads((ROOT/'schemas'/name).read_text()))
        self.assertEqual(parse_quality_decision('{"decision":"ACCEPT","reason_codes":["USABLE_SCENE"]}')['decision'],'ACCEPT')
        for invalid in (' ```json\n{}\n```','{"decision":"ACCEPT","reason_codes":["BLUR"]}','{"decision":"REJECT","reason_codes":["USABLE_SCENE"]}','{"decision":"REVIEW","reason_codes":[]}'):
            with self.subTest(invalid=invalid),self.assertRaises(VisualQualityError):parse_quality_decision(invalid)

    def test_cache_key_changes_with_model_prompt_and_image(self):
        model=self.policy()['quality_model'];left=quality_task_id(image_sha256='a'*64,model=model);same=quality_task_id(image_sha256='a'*64,model=model);changed=quality_task_id(image_sha256='b'*64,model=model);other={**model,'revision':'other'}
        self.assertEqual(left,same);self.assertNotEqual(left,changed);self.assertNotEqual(left,quality_task_id(image_sha256='a'*64,model=other))

    def test_reserve_plan_prefers_distinct_sequences(self):
        candidate=[{'candidate_id':'C1','latitude':40.415,'longitude':-3.704}]
        images=[{'image_id':'1','latitude':40.415,'longitude':-3.704,'sequence_id':'S1','orientation_degrees':0,'camera_type':'equirectangular','quality_score':.9,'width_px':1000,'height_px':500,'captured_at_epoch_ms':3},{'image_id':'2','latitude':40.41501,'longitude':-3.704,'sequence_id':'S1','orientation_degrees':0,'camera_type':'equirectangular','quality_score':.8,'width_px':1000,'height_px':500,'captured_at_epoch_ms':2},{'image_id':'3','latitude':40.41502,'longitude':-3.704,'sequence_id':'S2','orientation_degrees':0,'camera_type':'equirectangular','quality_score':.7,'width_px':1000,'height_px':500,'captured_at_epoch_ms':1}]
        plan=freeze_quality_reserves(candidate,images,reserve_depth=3)
        self.assertEqual([row['image_id'] for row in plan['reserves']],['1','3','2'])

    def test_reject_and_review_are_replaced_and_never_reach_claims(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);assets={};decisions={};reserves=[]
            for index,decision in enumerate(('REJECT','REVIEW','ACCEPT')):
                raw=f'image-{index}'.encode();path=root/f'{index}.bin';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();assets[str(index)]={'logical_path':path.name,'sha256':sha,'size_bytes':len(raw)};reserves.append({'candidate_id':'C1','reserve_index':index,'image_id':str(index),'sequence_id':f'S{index}'});decisions[sha]={'decision':decision,'reason_codes':{'REJECT':['BLUR'],'REVIEW':['AMBIGUOUS_QUALITY'],'ACCEPT':['USABLE_SCENE']}[decision]}
            claims=Claims();result=run_quality_replacement(reserves=reserves,claims_by_candidate={'C1':[{'claim_id':'claim'}]},policy=self.policy(),resolver=ManifestAssetResolver(assets,root=root),quality_verifier=ScriptedQualityVerifier(decisions),claim_verifier=claims,mode='fixture')
            self.assertEqual(result['candidates'][0]['accepted_image_ids'],['2']);self.assertEqual(claims.calls,['2']);self.assertEqual(result['summary']['successful_replacements'],1);self.assertEqual(result['summary']['quality_reject'],1);self.assertEqual(result['summary']['quality_review'],1)

    def test_all_rejected_abstains_without_penalty_or_infinite_loop(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);assets={};decisions={};reserves=[]
            for index in range(2):
                raw=f'bad-{index}'.encode();path=root/f'{index}.bin';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();assets[str(index)]={'logical_path':path.name,'sha256':sha,'size_bytes':len(raw)};reserves.append({'candidate_id':'C1','reserve_index':index,'image_id':str(index),'sequence_id':f'S{index}'});decisions[sha]={'decision':'REJECT','reason_codes':['BLUR']}
            result=run_quality_replacement(reserves=reserves,claims_by_candidate={'C1':[]},policy=self.policy(),resolver=ManifestAssetResolver(assets,root=root),quality_verifier=ScriptedQualityVerifier(decisions),mode='fixture')
            self.assertTrue(result['candidates'][0]['status'].startswith('abstain'));self.assertTrue(result['candidates'][0]['abstention_is_neutral']);self.assertEqual(len(result['attempts']),2)

    def test_quality_cache_avoids_call(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);raw=b'ok';path=root/'1.bin';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();assets={'1':{'logical_path':path.name,'sha256':sha,'size_bytes':2}};policy=self.policy();verifier=ScriptedQualityVerifier({});task=quality_task_id(image_sha256=sha,model=verifier.metadata);result=run_quality_replacement(reserves=[{'candidate_id':'C1','reserve_index':0,'image_id':'1','sequence_id':'S1'}],claims_by_candidate={'C1':[]},policy=policy,resolver=ManifestAssetResolver(assets,root=root),quality_verifier=verifier,quality_cache={task:{'decision':'ACCEPT','reason_codes':['USABLE_SCENE']}},mode='offline')
            self.assertEqual(verifier.calls,[]);self.assertEqual(result['summary']['quality_cache_hits'],1)

    def test_invalid_cached_accept_does_not_bypass_parser(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);raw=b'ok';path=root/'1.bin';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();assets={'1':{'logical_path':path.name,'sha256':sha,'size_bytes':2}};policy=self.policy();verifier=ScriptedQualityVerifier({sha:{'decision':'ACCEPT','reason_codes':['USABLE_SCENE']}});task=quality_task_id(image_sha256=sha,model=verifier.metadata);result=run_quality_replacement(reserves=[{'candidate_id':'C1','reserve_index':0,'image_id':'1','sequence_id':'S1'}],claims_by_candidate={'C1':[]},policy=policy,resolver=ManifestAssetResolver(assets,root=root),quality_verifier=verifier,quality_cache={task:{'decision':'ACCEPT','reason_codes':['BLUR']}},mode='offline')
            self.assertEqual(len(verifier.calls),1);self.assertEqual(result['summary']['quality_cache_hits'],0)

    def test_replacement_limit_is_not_exceeded(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);assets={};decisions={};reserves=[]
            for index in range(3):
                raw=f'bad-{index}'.encode();path=root/f'{index}.bin';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();assets[str(index)]={'logical_path':path.name,'sha256':sha,'size_bytes':len(raw)};reserves.append({'candidate_id':'C1','reserve_index':index,'image_id':str(index),'sequence_id':f'S{index}'});decisions[sha]={'decision':'REJECT','reason_codes':['BLUR']}
            policy=self.policy();policy['limits']['maximum_replacements_per_candidate']=1;result=run_quality_replacement(reserves=reserves,claims_by_candidate={'C1':[]},policy=policy,resolver=ManifestAssetResolver(assets,root=root),quality_verifier=ScriptedQualityVerifier(decisions),mode='fixture')
            self.assertEqual(len(result['attempts']),2);self.assertEqual(result['candidates'][0]['replacements'],1);self.assertEqual(result['candidates'][0]['status'],'abstain_replacement_budget_exhausted')

    def test_online_mode_fails_closed_without_authorized_policy(self):
        policy=self.policy();policy['status']='proposed_not_authorized_for_real_execution'
        with self.assertRaises(VisualQualityError):run_quality_replacement(reserves=[],claims_by_candidate={},policy=policy,resolver=None,quality_verifier=ScriptedQualityVerifier({}),mode='online')

    def test_postprocessor_disabled_is_exact_baseline(self):
        policy=self.policy();policy['enabled']=False;verifier=ScriptedQualityVerifier({});processor=QualityGatedVisualPostprocessor(reserve_k=10,policy=policy,reserve_source=lambda **k:None,resolver=None,quality_verifier=verifier,claims_source=lambda text:{},claim_verifier=None,ranking_policy=lambda a,b:None,mode='offline');rows=[{'rank':i+1,'candidate_id':f'C{i}','cosine_similarity':1-i/10,'latitude':40.0,'longitude':-3.0} for i in range(10)];retrieval={'gallery_id':'madrid-50m','visual_dataset_id':'v','embedding_dataset_id':'e','results':rows};result=processor.apply(query_text='texto',processing_variant='es_original',retrieval=retrieval);self.assertEqual(result['status'],'fallback_baseline');self.assertEqual(result['final_results'],rows)

    def test_postprocessor_all_abstain_does_not_call_ranking(self):
        with tempfile.TemporaryDirectory() as name:
            called=[];policy=self.policy();verifier=ScriptedQualityVerifier({});rows=[{'rank':i+1,'candidate_id':f'C{i}','cosine_similarity':1-i/10,'latitude':40.0,'longitude':-3.0} for i in range(10)];retrieval={'gallery_id':'madrid-50m','visual_dataset_id':'v','embedding_dataset_id':'e','results':rows};processor=QualityGatedVisualPostprocessor(reserve_k=10,policy=policy,reserve_source=lambda **k:{'reserves':[]},resolver=ManifestAssetResolver({},root=Path(name)),quality_verifier=verifier,claims_source=lambda text:{},claim_verifier=None,ranking_policy=lambda a,b:called.append(True),mode='offline');result=processor.apply(query_text='texto',processing_variant='es_original',retrieval=retrieval);self.assertEqual(result['reason'],'no_accepted_visual_evidence');self.assertEqual(called,[]);self.assertEqual(result['final_results'],rows)

    def test_only_accepted_images_are_projected_to_claims(self):
        sha='a'*64;result={'run_id':'visual-quality-run-sha256-'+'b'*64,'candidates':[{'candidate_id':'C1','accepted_image_ids':['A'],'accepted_image_sha256':[sha]},{'candidate_id':'C2','accepted_image_ids':[],'accepted_image_sha256':[]}],'attempts':[{'candidate_id':'C1','image_id':'A','image_sha256':sha,'quality_decision':'ACCEPT','quality_status':'valid','quality_task_id':'task'}]};rows=[{'candidate_id':'C1','image_id':'A','image_sha256':sha,'reserve_index':1},{'candidate_id':'C1','image_id':'B','image_sha256':'b'*64,'reserve_index':0},{'candidate_id':'C2','image_id':'C','image_sha256':'c'*64,'reserve_index':0}]
        projected=accepted_associations(result,rows);self.assertEqual(len(projected),1);self.assertEqual(projected[0]['image_id'],'A');self.assertEqual(projected[0]['quality_task_id'],'task')

if __name__=='__main__':unittest.main()
