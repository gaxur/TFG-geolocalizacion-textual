import copy,json
from pathlib import Path
import unittest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f59_human_streetview import F59Error,build_dataset,evaluate,ranking_id

ROOT=Path(__file__).resolve().parents[1]

class Phase59Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cfg=load_region_config(ROOT/"config/madrid.yaml"); cls.catalogs={g:load_verified_f1_catalog(ROOT/f"data/processed/catalog/manifest-{size}m.json",cfg) for g,size in (("madrid-25m",25),("madrid-50m",50))}; cls.spec=json.loads((ROOT/"config/madrid_f59_human_streetview.json").read_text()); cls.dataset=build_dataset(cls.spec,cls.catalogs)
 def test_h01_h02_inside_and_reference_is_panorama(self):
  self.assertEqual([r["observation_id"] for r in self.dataset["observations"]],["H01","H02"]); self.assertTrue(all(r["geography"]["provided_coordinate_inside_d004"] and r["geography"]["panorama_coordinate_inside_d004"] for r in self.dataset["observations"])); self.assertEqual(self.dataset["protocol"]["reference_coordinate_role"],"panorama_coordinate"); self.assertTrue(all(r["geography"]["provided_to_panorama_distance_m"]>0 for r in self.dataset["observations"])); self.assertFalse(self.dataset["protocol"]["official_f54_evaluation"])
 def test_marker_and_panorama_assignments_are_separate(self):
  h02=self.dataset["observations"][1]; self.assertNotEqual(h02["provided_coordinate"],h02["panorama_coordinate"]); self.assertIn("provided_coordinate_assignments",h02["geography"]); self.assertIn("panorama_reference_assignments",h02["geography"])
 def test_coordinate_leak_is_rejected(self):
  bad=copy.deepcopy(self.spec); bad["observations"][0]["spanish_text"] += " 40.4198746"
  with self.assertRaises(F59Error): build_dataset(bad,self.catalogs)
 def test_evaluation_persists_candidate_distances(self):
  rows=[]
  for obs in self.dataset["observations"]:
   for kind in ("es_original","en_human_control","es_cartographic","en_conventional","en_toponym_preserved","en_cartographic"):
    for gallery in ("madrid-25m","madrid-50m"):
     ref=obs["panorama_coordinate"]; results=[{"rank":i,"candidate_id":f"{gallery}-{i}","latitude":ref["latitude"]+(i-1)*.0001,"longitude":ref["longitude"],"cosine_similarity":1-i/100} for i in range(1,11)]; rows.append({"source_query_id":obs["observation_id"],"control_id":f"{obs['observation_id']}-{kind}","kind":kind,"source":"test","language":"es","text_sha256":"1"*64,"gallery_id":gallery,"top_k":10,"results":results,"retrieval_ms":1.0,"pipeline_elapsed_ms":1.1})
  rankings={"schema_version":"1.0","contract_version":"f59-exploratory-rankings-v1","ranking_id":"","checkpoint_sha256":"d"*64,"gallery_ids":["madrid-25m","madrid-50m"],"ranking_method":"exhaustive_cosine","top_k":10,"rows":rows,"limitations":["coordinates_not_used_for_retrieval"]}; rankings["ranking_id"]=ranking_id(rankings); result=evaluate(self.dataset,rankings,dataset_sha256="a"*64,plan_sha256="b"*64,rankings_sha256="c"*64); self.assertEqual(len(result["per_observation"]),24); self.assertEqual(len(result["per_observation"][0]["candidates"]),10); self.assertEqual(result["per_observation"][0]["candidates"][0]["distance_to_panorama_reference_m"],0); self.assertFalse(result["per_observation"][0]["exact_recall_available"]); self.assertIsNone(result["per_observation"][0]["recall_at_10"]); self.assertEqual(result["coverage"]["officially_evaluable"],0)

if __name__=="__main__": unittest.main()
