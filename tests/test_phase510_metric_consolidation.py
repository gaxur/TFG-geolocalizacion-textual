import copy,json
from pathlib import Path
import unittest
from src.tfg_phase0.f510_metric_consolidation import F510Error,_consolidate_rows,audit_overlaps,verify_manifest

ROOT=Path(__file__).resolve().parents[1]

class Phase510Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  paths=[ROOT/"results/generated/f5/f59-h03-h10/final/evaluation-h01-h10.json",ROOT/"results/generated/f5/f56/f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a/dataset.json",ROOT/"results/generated/f5/f59-h01-h02/inputs/dataset.json",ROOT/"results/generated/f5/f59-h03-h10/inputs/dataset.json"]
  if not all(path.is_file() for path in paths): raise unittest.SkipTest("artefactos locales F5.9/F5.10 no disponibles")
  cls.combined=json.loads(paths[0].read_text()); cls.f56=json.loads(paths[1].read_text()); cls.h12=json.loads(paths[2].read_text()); cls.h310=json.loads(paths[3].read_text())
 def test_metrics_have_correct_geographic_and_exact_denominators(self):
  report=_consolidate_rows(self.combined["per_observation"],tuple(f"H{i:02d}" for i in range(1,11))); m={(x["gallery_id"],x["kind"]):x for x in report["metrics"]}; self.assertEqual(m[("madrid-25m","en_cartographic")]["geo_recall_at_1"]["50"]["hits"],3); self.assertEqual(m[("madrid-25m","en_cartographic")]["geo_recall_at_1"]["50"]["total"],10); self.assertEqual(m[("madrid-50m","en_toponym_preserved")]["recall_at_1_exact"]["hits"],1); self.assertEqual(m[("madrid-50m","en_toponym_preserved")]["recall_at_1_exact"]["total"],9)
  self.assertEqual(m[("madrid-25m","es_original")]["geo_recall_at_10"]["50"]["leave_one_out_range"],[1/3,4/9])
 def test_nearest_rank_histogram_and_paired_transitions_are_complete(self):
  report=_consolidate_rows(self.combined["per_observation"],tuple(f"H{i:02d}" for i in range(1,11))); metric=report["metrics"][0]; self.assertEqual(sum(metric["nearest_candidate_rank"]["histogram"].values()),10); pair=next(x for x in report["paired_comparisons"] if x["gallery_id"]=="madrid-25m" and x["kind"]=="es_cartographic"); self.assertEqual(pair["geo_recall_at_10"]["50"]["total"],10); self.assertEqual(pair["recall_at_1_exact"]["unavailable"],1)
 def test_detects_exact_and_spatial_f57_overlaps(self):
  audit=audit_overlaps(self.f56,self.h12,self.h310); pairs={(x["f57_observation_id"],x["f59_observation_id"]):x for x in audit["pairs_within_25m_or_same_panorama"]}; self.assertTrue(pairs[("SV-02","H10")]["same_panorama"]); self.assertAlmostEqual(pairs[("SV-02","H10")]["distance_m"],0); self.assertFalse(pairs[("SV-03","H03")]["same_panorama"]); self.assertLess(pairs[("SV-03","H03")]["distance_m"],11)
 def test_duplicate_rows_are_rejected_and_manifests_verify(self):
  rows=copy.deepcopy(self.combined["per_observation"]); rows.append(copy.deepcopy(rows[0]));
  with self.assertRaises(F510Error): _consolidate_rows(rows,tuple(f"H{i:02d}" for i in range(1,11)))
  verified=verify_manifest(ROOT/"results/generated/f5/f59-h01-h02/final/manifest.json",ROOT); self.assertEqual(verified["mismatches"],[])

if __name__=="__main__": unittest.main()
