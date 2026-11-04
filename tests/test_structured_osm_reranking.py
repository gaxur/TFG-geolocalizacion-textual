import unittest
import json
from pathlib import Path
from src.tfg_phase0.structured_osm_reranking import build_structured_evidence,build_variants,extract_text_evidence,index_f3

ROOT=Path(__file__).resolve().parents[1]

class StructuredOsmRerankingTests(unittest.TestCase):
    def test_extracts_names_categories_and_keeps_orientation_unscored(self):
        evidence=extract_text_evidence('A mi derecha veo «Café Sol», una farmacia y un árbol.')
        self.assertEqual(evidence['names'][0]['normalized'],'cafe sol')
        self.assertEqual({row['category'] for row in evidence['categories']},{'pharmacy','tree'})
        self.assertTrue(evidence['spatial_relations'][0]['requires_orientation'])
        self.assertFalse(evidence['spatial_relations'][0]['used_for_scoring'])

    def test_specific_exact_name_outweighs_generic_category(self):
        objects={
            'node/1':{'osm_ref':'node/1','geometry_role':'point','tags':{'name':'Café Sol','amenity':'cafe'}},
            'node/2':{'osm_ref':'node/2','geometry_role':'point','tags':{'natural':'tree'}},
        }
        association=lambda cid,ref:{'candidate_id':cid,'osm_ref':ref,'within':True,'contains':False,'crosses':False,'overlaps':False,'touches':False,'intersects':True,'center_distance_m':2.0}
        by=index_f3([association('a','node/1'),association('b','node/2')])
        result=build_structured_evidence(text='Veo «Café Sol» y un árbol.',candidate_ids=['b','a'],associations_by_candidate=by,objects=objects)
        self.assertEqual(result['candidate_evidence'][0]['candidate_id'],'a')
        self.assertEqual(result['candidate_evidence'][0]['evidence_level'],'strong')

    def test_weak_only_abstains_and_preserves_all_variants(self):
        objects={'node/1':{'osm_ref':'node/1','geometry_role':'point','tags':{'natural':'tree'}}}
        association={'candidate_id':'b','osm_ref':'node/1','within':True,'contains':False,'crosses':False,'overlaps':False,'touches':False,'intersects':True,'center_distance_m':1.0}
        result=build_structured_evidence(text='Veo un árbol.',candidate_ids=['a','b'],associations_by_candidate=index_f3([association]),objects=objects)
        variants,audit=build_variants(['a','b'],result)
        self.assertTrue(audit['abstained'])
        self.assertTrue(all(order==['a','b'] for order in variants.values()))

    def test_conditional_promotion_is_limited_to_one_candidate(self):
        rows=[{'candidate_id':'c','original_rank':3,'score':5.0,'evidence_level':'strong','matches':[]},{'candidate_id':'b','original_rank':2,'score':1.0,'evidence_level':'moderate','matches':[]},{'candidate_id':'a','original_rank':1,'score':0.0,'evidence_level':'none','matches':[]}]
        evidence={'candidate_evidence':rows,'summary':{'informative':True}}
        variants,audit=build_variants(['a','b','c'],evidence)
        self.assertEqual(variants['conditional_strong_top1'],['c','a','b'])
        self.assertEqual(audit['promoted_candidate_id'],'c')

    def test_frozen_v4_rankings_do_not_use_gt_and_preserve_candidate_budget(self):
        path=ROOT/'results/generated/mapillary/h26-h37-exploratory-v4/structured-rankings.frozen.json'
        if not path.exists(): self.skipTest('artefacto v4 todavía no materializado')
        document=json.loads(path.read_text())
        self.assertFalse(document['protocol']['ground_truth_used'])
        self.assertTrue(document['protocol']['all_variants_frozen_before_evaluation'])
        for query in document['queries'].values():
            baseline=set(query['variants']['baseline'])
            self.assertEqual(len(baseline),100)
            for ranking in query['variants'].values():
                self.assertEqual(len(ranking),100)
                self.assertEqual(set(ranking),baseline)

    def test_v4_manifest_keeps_historical_inputs_immutable(self):
        path=ROOT/'results/generated/mapillary/h26-h37-exploratory-v4/manifest.json'
        if not path.exists(): self.skipTest('manifest v4 todavía no materializado')
        document=json.loads(path.read_text())
        self.assertEqual(document['status'],'completed_no_policy_replacement')
        self.assertFalse(document['protocol']['gpu_used'])
        self.assertFalse(document['protocol']['network_used'])
        self.assertFalse(document['frozen_inputs']['modified'])

if __name__=='__main__':unittest.main()
