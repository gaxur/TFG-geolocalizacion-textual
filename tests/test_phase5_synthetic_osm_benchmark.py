import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_synthetic_osm_benchmark import SyntheticBenchmarkError, apply_human_review, association_relation, benchmark_id, build_description, quality_metrics, spatial_group_partitions, spatial_select, synthetic_evaluation_adapter, validate_benchmark_against_f3, validate_synthetic_benchmark
from src.tfg_phase0.validation import validate_document


ROOT=Path(__file__).resolve().parents[1]
F3=ROOT/"data/processed/osm/osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141/f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453"
BENCH=ROOT/"results/generated/f5/f55c-final/f55c-synthetic-osm-sha256-bf7aea13116cda8e027343535f0a6d2de3bd6582aa09c6a65d1f14e9b24873c2/benchmark.json"


class Phase5SyntheticOSMBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=load_region_config(ROOT/"config/madrid.yaml"); cls.temp=tempfile.TemporaryDirectory(); cls.catalogs={}
        for size in (25,50):
            path=Path(cls.temp.name)/f"manifest-{size}.json"; write_manifest(build_catalog(cls.config,spacing_m=size),path); cls.catalogs[size]=load_verified_f1_catalog(path,cls.config)
        cls.document=json.loads(BENCH.read_text()) if BENCH.is_file() and F3.is_dir() else None

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_real_benchmark_contract_hash_assignments_and_f3_evidence(self):
        if self.document is None: self.skipTest("artefactos locales F3/F5.5c no disponibles")
        summary=validate_synthetic_benchmark(self.document); self.assertEqual(summary["observations"],35); self.assertGreaterEqual(summary["minimum_pair_distance_m"],70); self.assertEqual(self.document["benchmark_id"],benchmark_id(self.document)); validate_document(self.document,"f5_synthetic_osm_benchmark"); validate_benchmark_against_f3(self.document,catalog_50=self.catalogs[50],catalog_25=self.catalogs[25],f3_bundle=F3); self.assertTrue(all(row["reference"]["madrid-25m"]["status"]=="assigned" and row["reference"]["madrid-50m"]["status"]=="assigned" for row in self.document["observations"]))

    def test_synthetic_is_never_human_gt_and_review_starts_pending(self):
        if self.document is None: self.skipTest("benchmark local F5.5c no disponible")
        self.assertTrue(all(row["source_type"]=="synthetic_osm" and row["reference"]["synthetic_coordinate_not_gnss"] and row["review"]["status"]=="pending" for row in self.document["observations"])); adapter=synthetic_evaluation_adapter(self.document); self.assertFalse(adapter["real_ground_truth"]); self.assertEqual(adapter["observations"],[]); self.assertEqual(adapter["excluded_pending"],35); tampered=copy.deepcopy(self.document); tampered["observations"][0]["source_type"]="human_in_situ"; tampered["benchmark_id"]=benchmark_id(tampered)
        with self.assertRaises(SyntheticBenchmarkError): validate_synthetic_benchmark(tampered)

    def test_partitions_do_not_split_spatial_groups(self):
        if self.document is None: self.skipTest("benchmark local F5.5c no disponible")
        groups={}
        for row in self.document["observations"]: self.assertEqual(groups.setdefault(row["spatial_group_id"],row["partition"]),row["partition"])
        self.assertIn("development",groups.values()); self.assertIn("evaluation",groups.values())

    def test_evidence_tampering_is_rejected_against_f3(self):
        if self.document is None: self.skipTest("artefactos locales F3/F5.5c no disponibles")
        tampered=copy.deepcopy(self.document); tampered["observations"][0]["evidence"][0]["center_distance_m"]+=1; tampered["benchmark_id"]=benchmark_id(tampered)
        with self.assertRaises(SyntheticBenchmarkError): validate_benchmark_against_f3(tampered,catalog_50=self.catalogs[50],catalog_25=self.catalogs[25],f3_bundle=F3)

    def test_predicates_and_description_quality_are_conservative(self):
        self.assertEqual(association_relation({"touches":False,"contains":False,"within":False,"crosses":True,"overlaps":False,"intersects":True}),"crosses_cell")
        evidence=[{"semantic_type":"street","center_distance_m":5,"relation":"crosses_cell"},{"semantic_type":"building","center_distance_m":10,"relation":"overlaps_cell"},{"semantic_type":"park","center_distance_m":20,"relation":"inside_cell"}]
        text,used=build_description(evidence); self.assertNotIn("visible",text.casefold()); self.assertNotIn("izquierda",text.casefold()); self.assertTrue(quality_metrics(text,used)["passes_automatic_quality"])

    def test_spatial_selection_is_seeded_and_text_unique(self):
        candidates=[]
        for index,candidate in enumerate(self.catalogs[50].candidates[:10]): candidates.append({"candidate":candidate,"description":f"texto-{index}"})
        left=spatial_select(candidates,count=5,seed=55,minimum_spacing_m=10); right=spatial_select(list(reversed(candidates)),count=5,seed=55,minimum_spacing_m=10); self.assertEqual([x["candidate"].candidate_id for x in left],[x["candidate"].candidate_id for x in right]); self.assertEqual(len({x["description"] for x in left}),len(left))

    def test_human_review_requires_exact_coverage_and_does_not_change_evidence(self):
        if self.document is None: self.skipTest("benchmark local F5.5c no disponible")
        decisions={"contract_version":"f55c-synthetic-review-decisions-v1","reviewer":"human","reviewed_at_utc":"2026-10-21T08:00:00Z","decisions":[{"observation_id":row["observation_id"],"decision":"approve","notes":"coherencia OSM revisada"} for row in self.document["observations"]]}; reviewed=apply_human_review(self.document,decisions); self.assertEqual([r["evidence"] for r in reviewed["observations"]],[r["evidence"] for r in self.document["observations"]]); self.assertEqual(len(synthetic_evaluation_adapter(reviewed)["observations"]),35); decisions["decisions"].pop()
        with self.assertRaises(SyntheticBenchmarkError): apply_human_review(self.document,decisions)


if __name__=="__main__": unittest.main()
