import unittest
from src.tfg_phase0.topn_promotion import apply_promotion,freeze_policy,restore_baseline
class TopNPromotionTests(unittest.TestCase):
 def baseline(self):return [{'rank':i,'candidate_id':f'c{i}','latitude':40.,'longitude':-3.,'cosine_similarity':1-i/1000} for i in range(1,101)]
 def test_disabled_preserves_top10_and_baseline(self):
  base=self.baseline();doc=apply_promotion(base,{'candidates':[]},freeze_policy());self.assertEqual(doc['final_top10_candidate_ids'],[f'c{i}' for i in range(1,11)]);self.assertEqual(doc['full_experimental_order'],[f'c{i}' for i in range(1,101)]);self.assertEqual(restore_baseline(doc),base)
 def test_positive_candidate_can_promote_from_open_block(self):
  base=self.baseline();aggregate={'candidates':[{'candidate_id':'c11','positive_evidence':1.,'valid_verdicts':5,'coverage_status':'available'}]};policy=freeze_policy(enabled=True,positive_weight=1.,minimum_positive_evidence=.5,max_promotions=1,opened_blocks=((11,20),));doc=apply_promotion(base,aggregate,policy);self.assertIn('c11',doc['final_top10_candidate_ids']);self.assertEqual(len(doc['operations']),1)
 def test_no_coverage_is_neutral(self):
  base=self.baseline();aggregate={'candidates':[{'candidate_id':'c11','positive_evidence':1.,'valid_verdicts':5,'coverage_status':'no_coverage'}]};policy=freeze_policy(enabled=True,positive_weight=1.,minimum_positive_evidence=.5,max_promotions=1,opened_blocks=((11,20),));doc=apply_promotion(base,aggregate,policy);self.assertNotIn('c11',doc['final_top10_candidate_ids'])
 def test_top20_reserve_can_promote_without_discard(self):
  base=self.baseline()[:20];aggregate={'candidates':[{'candidate_id':'c11','positive_evidence':1.,'valid_verdicts':2,'coverage_status':'available'}]};policy=freeze_policy(enabled=True,input_top_n=20,positive_weight=1.,minimum_positive_evidence=.5,max_promotions=1,opened_blocks=((11,20),));doc=apply_promotion(base,aggregate,policy);self.assertIn('c11',doc['final_top10_candidate_ids']);self.assertFalse(doc['policy']['discard']['available']);self.assertFalse(doc['protocol']['discard_used'])
 def test_zero_positive_evidence_is_not_eligible_with_nonzero_guard(self):
  base=self.baseline()[:50];aggregate={'candidates':[{'candidate_id':'c11','positive_evidence':0.,'valid_verdicts':8,'coverage_status':'available'}]};policy=freeze_policy(enabled=True,input_top_n=50,positive_weight=.2,minimum_positive_evidence=.01,max_promotions=10,opened_blocks=((11,20),(21,50)));doc=apply_promotion(base,aggregate,policy);decision=next(row for row in doc['candidate_decisions'] if row['candidate_id']=='c11');self.assertFalse(decision['eligible_for_promotion']);self.assertEqual(doc['operations'],[])
if __name__=='__main__':unittest.main()
