import copy,json
from pathlib import Path
import unittest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f59_oriented_extension import F59ExtensionError,build_dataset

ROOT=Path(__file__).resolve().parents[1]

class Phase59OrientedTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cfg=load_region_config(ROOT/"config/madrid.yaml"); cls.catalogs={g:load_verified_f1_catalog(ROOT/f"data/processed/catalog/manifest-{s}m.json",cfg) for g,s in (("madrid-25m",25),("madrid-50m",50))}; cls.spec=json.loads((ROOT/"config/madrid_f59_h03_h10_streetview.json").read_text())
 def test_eight_cases_are_inside_and_keep_orientation_documentary(self):
  dataset=build_dataset(self.spec,self.catalogs); self.assertEqual([r["observation_id"] for r in dataset["observations"]],[f"H{i:02d}" for i in range(3,11)]); self.assertTrue(all(r["geography"]["panorama_coordinate_inside_d004"] for r in dataset["observations"])); self.assertTrue(all(r["orientation_audit"]["heading_recorded_but_not_model_input"] and not r["orientation_audit"]["cardinal_directions_inferred"] for r in dataset["observations"])); self.assertFalse(dataset["protocol"]["coordinates_heading_pitch_used_for_qwen_or_retrieval"])
 def test_only_literal_names_are_annotated(self):
  dataset=build_dataset(self.spec,self.catalogs); names={r["observation_id"]:[x["mention"] for x in r["toponyms"]] for r in dataset["observations"]}; self.assertEqual(names["H05"],["Hotel Anaco"]); self.assertEqual(names["H06"],["El Corte Inglés"]); self.assertEqual(names["H09"],["Pisco Sour Cocina Peruana"]); self.assertEqual(names["H10"],["La Vinoteca"]); self.assertEqual(names["H03"],[])
 def test_missing_name_and_orientation_audit_are_rejected(self):
  bad=copy.deepcopy(self.spec); bad["observations"][2]["proper_toponyms"][0]["mention"]="Nombre inventado"
  with self.assertRaises(F59ExtensionError): build_dataset(bad,self.catalogs)
  bad=copy.deepcopy(self.spec); bad["observations"][0]["osm_carto_audit"]["egocentric_relations_not_encoded"].remove("derecha")
  with self.assertRaises(F59ExtensionError): build_dataset(bad,self.catalogs)
 def test_coordinate_leak_is_rejected(self):
  bad=copy.deepcopy(self.spec); bad["observations"][0]["spanish_text"] += " 40.4154371"
  with self.assertRaises(F59ExtensionError): build_dataset(bad,self.catalogs)

if __name__=="__main__": unittest.main()
