import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.catalog import build_catalog,write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f56_streetview_documentary import StreetViewDocumentaryError,build_dataset,dataset_id,execution_gate,exploratory_reference_adapter,png_dimensions,render_review_html,validate_dataset
from src.tfg_phase0.validation import validate_document

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"config/madrid_f56_streetview_documentary.json"

class Phase56StreetViewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.cfg=load_region_config(ROOT/"config/madrid.yaml"); cls.temp=tempfile.TemporaryDirectory(); cls.catalogs={}
  for n in (25,50):
   path=Path(cls.temp.name)/f"manifest-{n}.json"; write_manifest(build_catalog(cls.cfg,spacing_m=n),path); cls.catalogs[f"madrid-{n}m"]=load_verified_f1_catalog(path,cls.cfg)
  cls.spec=json.loads(SPEC.read_text()); cls.document=build_dataset(cls.spec,image_root=ROOT/"data/streetview",catalogs=cls.catalogs)
 @classmethod
 def tearDownClass(cls): cls.temp.cleanup()
 def test_four_images_hashes_identity_and_git_policy(self):
  self.assertEqual(len(self.document["observations"]),4); self.assertEqual(self.document["dataset_id"],dataset_id(self.document)); self.assertEqual(len({r["image"]["sha256"] for r in self.document["observations"]}),4); self.assertTrue(all(r["image"]["git_tracking_forbidden"] for r in self.document["observations"])); validate_document(self.document,"f56_streetview_documentary"); self.assertEqual(validate_dataset(self.document,catalogs=self.catalogs,image_root=ROOT/"data/streetview")["observations"],4)
 def test_sv02_excluded_and_active_link_points_assigned(self):
  by={r["observation_id"]:r for r in self.document["observations"]}; self.assertNotIn("SV-02",by); excluded=self.document["excluded_observations"][0]; self.assertEqual(excluded["observation_id"],"SV-02"); self.assertEqual(excluded["reason"],"outside_d004_and_both_gallery_coverages"); self.assertGreater(excluded["d004_north_excess_m"],16); self.assertFalse((ROOT/"data/streetview/SV-02.png").exists()); self.assertTrue(all(by[x]["geography"]["inside_d004_by_link_coordinate"] for x in ("SV-01","SV-03","SV-04","SV-05"))); self.assertTrue(all(v["status"]=="assigned" for x in by for v in by[x]["geography"]["link_point_assignments"].values()))
 def test_unknown_uncertainty_disables_exact_recall_and_official_accuracy(self):
  self.assertTrue(all(r["link_coordinate"]["positional_uncertainty"]=="unknown" and not r["geography"]["exact_recall_eligible"] and not r["geography"]["official_geographic_accuracy_eligible"] for r in self.document["observations"])); adapter=exploratory_reference_adapter(self.document); self.assertFalse(adapter["real_ground_truth"]); self.assertFalse(adapter["official_metrics_allowed"]); self.assertTrue(all(not r["exact_recall_eligible"] for r in adapter["observations"])); gate=execution_gate(self.document); self.assertFalse(gate["ready_for_variant_generation"]); self.assertFalse(gate["ready_for_exploratory_rankings"]); self.assertFalse(gate["ready_for_official_geographic_evaluation"]); self.assertEqual(gate["counts"]["observations"],4); self.assertEqual(gate["counts"]["inside_d004"],4); self.assertNotIn("observations_outside_d004",gate["blockers"]); self.assertEqual(gate["counts"]["rankings_generated"],0)
 def test_descriptions_have_no_coordinate_or_panorama_leak(self):
  for row in self.document["observations"]: self.assertFalse(row["description"]["contains_coordinates"]); self.assertFalse(row["description"]["contains_internal_ids"]); self.assertNotIn(row["provenance"]["panorama_id"],row["description"]["text"]); self.assertEqual(row["description"]["formal_review_status"],"pending")
 def test_tampering_and_missing_images_are_rejected(self):
  bad=copy.deepcopy(self.document); bad["observations"][0]["geography"]["exact_recall_eligible"]=True; bad["dataset_id"]=dataset_id(bad)
  with self.assertRaises(StreetViewDocumentaryError): validate_dataset(bad,catalogs=self.catalogs)
  spec=copy.deepcopy(self.spec); spec["observations"][0]["image_path"]="missing.png"
  with self.assertRaises(StreetViewDocumentaryError): build_dataset(spec,image_root=ROOT/"data/streetview",catalogs=self.catalogs)
 def test_png_parser_rejects_non_png(self):
  with self.assertRaises(StreetViewDocumentaryError): png_dimensions(b"not-png")
 def test_offline_html_uses_explicit_local_image_prefix(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/"review.html"; render_review_html(self.document,path,image_prefix="../../data/streetview"); text=path.read_text(); self.assertIn("../../data/streetview/SV-01.png",text); self.assertIn(self.spec["observations"][0]["external_url"],text)
if __name__=="__main__": unittest.main()
