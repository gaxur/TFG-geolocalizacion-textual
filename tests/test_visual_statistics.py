import unittest
from src.tfg_phase0.visual_statistics import exact_mcnemar,grouped_accuracy,paired_cluster_bootstrap,wilson_interval
class VisualStatisticsTests(unittest.TestCase):
 def test_wilson_is_bounded(self):
  lo,hi=wilson_interval(8,10);self.assertTrue(0<lo<.8<hi<1)
 def test_mcnemar_is_paired(self):
  value=exact_mcnemar([True,True,False,False],[True,False,True,True]);self.assertEqual((value['left_only'],value['right_only']),(1,2))
 def test_grouped_accuracy(self):
  value=grouped_accuracy([{'query_id':'a','correct':True},{'query_id':'a','correct':False},{'query_id':'b','correct':True}]);self.assertEqual(value['macro_group_accuracy'],.75)
 def test_cluster_bootstrap_is_reproducible(self):
  rows=[{'query_id':'a','left_correct':False,'right_correct':True},{'query_id':'b','left_correct':True,'right_correct':True}]
  self.assertEqual(paired_cluster_bootstrap(rows,iterations=100,seed=3),paired_cluster_bootstrap(rows,iterations=100,seed=3))
if __name__=='__main__':unittest.main()
