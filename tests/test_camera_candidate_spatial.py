import unittest
from src.tfg_phase0.camera_candidate_spatial import SpatialAssociationError,annotate_ambiguity,bearing_degrees,circular_difference_degrees,classify_camera_candidate,cone_square_intersection,square_metrics

class SpatialAssociationTests(unittest.TestCase):
 def test_square_interior_boundary_outside(self):
  self.assertEqual(square_metrics(100,200,100,200,50)["position_relation"],"interior");self.assertEqual(square_metrics(125,200,100,200,50)["position_relation"],"boundary");self.assertEqual(square_metrics(135,200,100,200,50)["surface_distance_m"],10)
 def test_corner_distance(self):self.assertAlmostEqual(square_metrics(135,235,100,200,50)["surface_distance_m"],14.1421356)
 def test_bearings_and_circular_difference(self):
  self.assertEqual(bearing_degrees(0,0,0,1),0);self.assertEqual(bearing_degrees(0,0,1,0),90);self.assertEqual(circular_difference_degrees(359,1),2);self.assertEqual(circular_difference_degrees(0,180),180)
 def test_cone_intersection_front_and_back(self):
  self.assertEqual(cone_square_intersection(0,-100,0,90,0,0,50)["relation"],"positive_area");self.assertEqual(cone_square_intersection(0,-100,180,90,0,0,50)["relation"],"disjoint")
 def test_invalid_fov(self):
  with self.assertRaises(SpatialAssociationError):cone_square_intersection(0,0,0,180,10,10)
 def test_missing_heading_is_explicit(self):
  camera={"latitude":40.,"longitude":-3.,"orientation_degrees":None,"camera_type":"perspective","horizontal_accuracy_m":None};candidate={"generation":{"center_easting_m":500000,"center_northing_m":4427757.2187}}
  result=classify_camera_candidate(camera,candidate);self.assertEqual(result["fov_basis"],"unavailable");self.assertIsNone(result["horizontal_fov_degrees"])
 def test_ambiguity_retains_multiple_candidates(self):
  rows=[{"global_record_id":"m:1","candidate_id":"a","within_round":True,"cone_cell_relation":"positive_area","base_category":"camera_outside_view_compatible"},{"global_record_id":"m:1","candidate_id":"b","within_round":True,"cone_cell_relation":"positive_area","base_category":"camera_outside_view_compatible"}];output=annotate_ambiguity(rows);self.assertTrue(all(row["classification"]=="spatially_ambiguous" for row in output));self.assertEqual(output[0]["competing_candidate_ids"],["a","b"])
if __name__=="__main__":unittest.main()
