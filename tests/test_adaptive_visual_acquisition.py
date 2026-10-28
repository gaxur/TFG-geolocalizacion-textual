import unittest
from src.tfg_phase0.adaptive_visual_acquisition import AdaptiveAcquisitionError,freeze_policy,plan_adaptive

class AdaptiveVisualTests(unittest.TestCase):
 def candidates(self):return [{"candidate_id":"a","latitude":40.,"longitude":-3.},{"candidate_id":"b","latitude":40.,"longitude":-3.001}]
 def images(self):return [{"image_id":str(i),"latitude":40.,"longitude":-3.+i*.00005,"sequence_id":f"s{i}","orientation_degrees":0,"camera_type":"perspective","quality_score":1,"width_px":100,"height_px":100} for i in range(6)]
 def test_no_gt_and_deterministic_inventory_order(self):
  p=freeze_policy(rounds=((25,1,1),(100,2,2)),max_unique_assets_total=10,max_new_assets=10,max_jobs_per_model=20,max_storage_bytes=80_000_000);left=plan_adaptive(self.candidates(),self.images(),p,claims_per_candidate=2);right=plan_adaptive(self.candidates(),list(reversed(self.images())),p,claims_per_candidate=2);self.assertEqual(left["associations"],right["associations"])
 def test_limits_and_sequence_diversity(self):
  images=self.images();images[1]["sequence_id"]=images[0]["sequence_id"];p=freeze_policy(rounds=((100,2,2),),max_unique_assets_total=4,max_new_assets=4,max_jobs_per_model=4,max_storage_bytes=32_000_000);doc=plan_adaptive(self.candidates(),images,p,claims_per_candidate=1);self.assertLessEqual(doc["summary"]["new_assets"],4);self.assertLessEqual(doc["summary"]["associations"],4)
 def test_candidate_without_photos_remains_zero(self):
  p=freeze_policy(rounds=((25,1,1),),max_unique_assets_total=2,max_new_assets=2,max_jobs_per_model=2,max_storage_bytes=16_000_000);doc=plan_adaptive([{"candidate_id":"far","latitude":41.,"longitude":-4.}],self.images(),p);self.assertEqual(doc["coverage"][0]["coverage"],0)
 def test_gt_rejected(self):
  p=freeze_policy(rounds=((25,1,1),),max_unique_assets_total=2,max_new_assets=2,max_jobs_per_model=2,max_storage_bytes=16_000_000)
  with self.assertRaises(ValueError):plan_adaptive([{**self.candidates()[0],"ground_truth":True}],self.images(),p)
 def test_policy_rejects_unbounded_or_nonmonotonic(self):
  with self.assertRaises(AdaptiveAcquisitionError):freeze_policy(rounds=((50,2,2),(25,4,4)))

 def test_existing_assets_do_not_consume_new_asset_budget(self):
  images=self.images();p=freeze_policy(rounds=((100,2,2),),max_unique_assets_total=6,max_new_assets=0,max_jobs_per_model=4,max_storage_bytes=1);doc=plan_adaptive([self.candidates()[0]],images,p,existing_asset_ids=[row["image_id"] for row in images],claims_per_candidate=1);self.assertGreater(doc["summary"]["associations"],0);self.assertEqual(doc["summary"]["new_assets"],0)

 def test_claim_count_caps_jobs(self):
  p=freeze_policy(rounds=((100,8,8),),max_unique_assets_total=20,max_new_assets=20,max_jobs_per_model=2,max_storage_bytes=160_000_000);doc=plan_adaptive([self.candidates()[0]],self.images(),p,claims_per_candidate=2);self.assertLessEqual(doc["summary"]["associations"],1)

if __name__=="__main__":unittest.main()
