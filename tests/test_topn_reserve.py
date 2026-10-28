import unittest
from src.tfg_phase0.topn_reserve import TopNReserveError,resolve_top_k,validate_top10_prefix
class TopNReserveTests(unittest.TestCase):
 def test_prefix_validation(self):
  results=[{'rank':i,'candidate_id':str(i),'latitude':1.,'longitude':2.,'cosine_similarity':1-i/100} for i in range(1,101)];old={'rows':[{'query_id':'H','kind':'k','gallery_id':'g','results':results[:10]}]};new={'rows':[{'query_id':'H','kind':'k','gallery_id':'g','results':results}]};self.assertTrue(validate_top10_prefix(new,old)['exact_prefix_match'])
 def test_full_is_resolved_per_gallery(self):
  self.assertEqual(resolve_top_k('full',gallery_count=253),253)
  self.assertEqual(resolve_top_k('full',gallery_count=1115),1115)
 def test_500_is_not_silently_clamped_for_50m(self):
  with self.assertRaises(TopNReserveError):resolve_top_k(500,gallery_count=253)
 def test_controlled_ks_are_supported(self):
  for value in (10,20,50,100,200):self.assertEqual(resolve_top_k(value,gallery_count=253),value)
if __name__=='__main__':unittest.main()
