import unittest
from src.tfg_phase0.adaptive_visual_acquisition import freeze_policy
from src.tfg_phase0.geometric_adaptive_acquisition import plan_geometric_adaptive

class GeometricAdaptiveTests(unittest.TestCase):
 def fixture(self):
  candidates=[{"candidate_id":"a","latitude":40.,"longitude":-3.,"generation":{"center_easting_m":500000,"center_northing_m":4427757.2187}},{"candidate_id":"b","latitude":40.,"longitude":-3.001,"generation":{"center_easting_m":499915,"center_northing_m":4427757.2187}}];slots=[{"slot_id":"H:a","query_id":"H","candidate":candidates[0]},{"slot_id":"H:b","query_id":"H","candidate":candidates[1]}];images=[{"image_id":"1","latitude":40.,"longitude":-3.,"sequence_id":"s1","orientation_degrees":0,"camera_type":"perspective","quality_score":1,"width_px":100,"height_px":100},{"image_id":"2","latitude":40.,"longitude":-3.0005,"sequence_id":"s2","orientation_degrees":90,"camera_type":"perspective","quality_score":1,"width_px":100,"height_px":100}];return slots,candidates,images
 def test_deterministic_and_no_gt(self):
  slots,candidates,images=self.fixture();policy=freeze_policy(rounds=((100,2,2),),max_unique_assets_total=4,max_new_assets=4,max_jobs_per_model=4,max_storage_bytes=32_000_000);left=plan_geometric_adaptive(slots,candidates,images,policy);right=plan_geometric_adaptive(list(reversed(slots)),list(reversed(candidates)),list(reversed(images)),policy);self.assertEqual({(r["slot_id"],r["global_record_id"]) for r in left["associations"]},{(r["slot_id"],r["global_record_id"]) for r in right["associations"]});self.assertFalse(left["protocol"]["ground_truth_used"])
 def test_budget_limits_hold(self):
  slots,candidates,images=self.fixture();policy=freeze_policy(rounds=((100,2,2),),max_unique_assets_total=1,max_new_assets=1,max_jobs_per_model=1,max_storage_bytes=8_000_000);doc=plan_geometric_adaptive(slots,candidates,images,policy);self.assertLessEqual(doc["summary"]["unique_assets"],1);self.assertLessEqual(doc["summary"]["associations"],1)
if __name__=="__main__":unittest.main()
