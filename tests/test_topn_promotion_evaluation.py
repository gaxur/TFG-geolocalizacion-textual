import unittest
from src.tfg_phase0.topn_promotion import apply_promotion,freeze_policy
from src.tfg_phase0.topn_promotion_evaluation import evaluate_promotion
class TopNPromotionEvaluationTests(unittest.TestCase):
 def test_promotion_can_improve_distance(self):
  base=[{'rank':i,'candidate_id':f'c{i}','latitude':40.,'longitude':-3.01 if i<=10 else -3.,'cosine_similarity':1-i/1000} for i in range(1,101)];aggregate={'candidates':[{'candidate_id':'c11','positive_evidence':1.,'valid_verdicts':3,'coverage_status':'available'}]};doc=apply_promotion(base,aggregate,freeze_policy(enabled=True,positive_weight=1.,minimum_positive_evidence=.5,max_promotions=1,opened_blocks=((11,20),)));result=evaluate_promotion(doc,reference_latitude=40.,reference_longitude=-3.,reference_candidate_id='c11');self.assertTrue(result['transition']['improved']);self.assertTrue(result['transition']['relevant_promoted'])
if __name__=='__main__':unittest.main()
