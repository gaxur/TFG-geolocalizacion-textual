import unittest

from src.tfg_phase0.reliable_osm_promotion import build_reliable_variants, catalog_statistics, promotion_confidence


class ReliableOsmPromotionTests(unittest.TestCase):
    def test_catalog_statistics_measure_global_name_ambiguity(self):
        objects={
            'node/1':{'tags':{'name':'Chain'}},
            'node/2':{'tags':{'official_name':'Chain'}},
        }
        stats=catalog_statistics(objects,[{'osm_ref':'node/1','candidate_id':'a'},{'osm_ref':'node/2','candidate_id':'b'}])
        self.assertEqual(stats['name_cells']['chain'],['a','b'])

    def test_repeated_chain_name_is_not_high_confidence(self):
        candidate={'candidate_id':'x','original_rank':5,'matches':[{'kind':'exact_name','query':'Chain','value':'Chain','osm_ref':'node/1'}]}
        textual={'names':[{'text':'Chain','normalized':'chain','generic':False}], 'categories':[]}
        catalog={'name_cells':{'chain':['a','b']},'name_objects':{'chain':['node/1','node/2']}}
        result=promotion_confidence(query_id='Q',candidate=candidate,textual_evidence=textual,catalog=catalog,visual=None)
        self.assertEqual(result['confidence'],'low')
        self.assertIn('name_repeated_across_catalog_cells',result['reasons'])

    def test_unmatched_distinctive_name_blocks_category_conjunction(self):
        candidate={'candidate_id':'x','original_rank':8,'matches':[
            {'kind':'category','category':'hairdresser','specificity':'specific','score':1,'osm_ref':'node/1'},
            {'kind':'category','category':'bollard','specificity':'specific','score':1,'osm_ref':'node/2'},
        ]}
        textual={'names':[{'text':'Alonzo','normalized':'alonzo','generic':False}], 'categories':[]}
        catalog={'name_cells':{},'name_objects':{}}
        result=promotion_confidence(query_id='Q',candidate=candidate,textual_evidence=textual,catalog=catalog,visual=None)
        self.assertEqual(result['confidence'],'low')
        self.assertIn('distinctive_query_name_not_matched',result['reasons'])

    def test_high_unique_name_can_change_top1_but_protected_policy_cannot(self):
        order=['a','b','c','d','e','f']
        confidence=[{'candidate_id':'e','source_rank':5,'confidence':'high'}]
        variants,audit=build_reliable_variants(order,confidence)
        self.assertEqual(variants['top1_protected'][0],'a')
        self.assertEqual(variants['top1_protected'][4],'e')
        self.assertEqual(variants['top1_conditioned'][0],'e')
        self.assertFalse(audit['abstained'])

if __name__=='__main__':unittest.main()
