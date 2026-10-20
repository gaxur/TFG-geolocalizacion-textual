import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import assign_reference, query_dataset_id
from src.tfg_phase0.crs import epsg25830_to_wgs84
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_ground_truth_evaluation import F54ValidationError, evaluate_variant_rankings, geographic_evaluation_id, ground_truth_dataset_id, validate_ground_truth_dataset
from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id
from src.tfg_phase0.f5_variant_ranking import variant_ranking_report_id
from src.tfg_phase0.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]
KINDS = ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved", "en_cartographic")


class Phase5GroundTruthEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_region_config(ROOT / "config/madrid.yaml")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.catalogs = {}
        for size in (25, 50):
            path = Path(cls.temporary.name) / f"manifest-{size}m.json"
            write_manifest(build_catalog(cls.config, spacing_m=size), path)
            cls.catalogs[f"madrid-{size}m"] = load_verified_f1_catalog(path, cls.config)

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def source(self, *, validated=True):
        candidate = self.catalogs["madrid-50m"].candidates[100]
        reference = {"status": "validated" if validated else "pending", "latitude": candidate.latitude if validated else None, "longitude": candidate.longitude if validated else None, "crs": "EPSG:4326" if validated else None, "capture_method": "surveyed_gnss" if validated else None, "reported_accuracy_m": 0.0 if validated else None, "validation_method": "independent_field_review" if validated else None, "catalog_assignment": assign_reference(candidate.latitude, candidate.longitude, self.catalogs["madrid-50m"], reported_accuracy_m=0.0) if validated else None}
        query = {"query_id": "obs-001", "location_id": "loc-001", "derivation_group_id": "group-001", "partition": "development", "description": {"text": "Estoy en una plaza junto a una calle.", "language": "es", "contains_coordinates": False}, "provenance": {"source_type": "human_in_situ", "description": "Fixture que representa la forma contractual de una observación, no un dato real del TFG.", "independent_environment_observation": True, "instructions_version": "fixture", "collected_at_utc": "2026-10-20T10:00:00Z"}, "reference": reference, "ambiguity": {"status": "not_ambiguous" if validated else "unreviewed", "notes": None}, "validation_status": "validated" if validated else "pending"}
        document = {"schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "", "dataset_version": "fixture", "region": {"region_id": "madrid_pilot", "bbox_wgs84": dict(self.config["region"]["bbox"])}, "catalog": {"manifest_id": self.catalogs["madrid-50m"].manifest_id, "manifest_sha256": self.catalogs["madrid-50m"].sha256, "candidate_count": 253, "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"}, "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": .8}, "queries": [query]}
        document["dataset_id"] = query_dataset_id(document); return document

    def gt(self, source, *, validated=True):
        query = source["queries"][0]
        reference = query["reference"]
        evidence = [{"evidence_id": "ev-001", "kind": "survey_record", "logical_reference": "evidence/obs-001.json", "sha256": "1" * 64, "description": "Registro de campo revisado", "captured_at_utc": "2026-10-20T10:00:00Z", "review_status": "reviewed"}] if validated else []
        observer = {key: reference[key] for key in ("status", "latitude", "longitude", "crs", "capture_method", "reported_accuracy_m", "validation_method")}; observer.update(evidence=evidence, review_notes="revisado" if validated else None)
        assignments = {gallery: assign_reference(reference["latitude"], reference["longitude"], catalog, reported_accuracy_m=reference["reported_accuracy_m"]) for gallery, catalog in self.catalogs.items()} if validated else {gallery: None for gallery in self.catalogs}
        observation = {"source_query_id": "obs-001", "location_id": "loc-001", "derivation_group_id": "group-001", "partition": "development", "description_profile": "complete_observation", "comparison_parent_query_id": None, "observer_reference": observer, "orientation": {"status": "absent", "cardinal": None, "bearing_degrees": None, "uncertainty_degrees": None, "verification_method": None, "evidence_ids": [], "egocentric_relations_present": False, "notes": None}, "catalog_assignments": assignments, "description_review_status": "reviewed" if validated else "pending", "limitations": []}
        raw = json.dumps(source, sort_keys=True).encode()
        document = {"schema_version": "1.0", "contract_version": "f5-ground-truth-dataset-v1", "dataset_id": "", "dataset_version": "fixture", "source_query_dataset": {"dataset_id": source["dataset_id"], "sha256": hashlib.sha256(raw).hexdigest()}, "catalogs": {gallery: {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": len(catalog.candidates), "cell_size_m": catalog.cell_size_m} for gallery, catalog in self.catalogs.items()}, "collection_protocol": {"version": "f54-madrid-observer-collection-v1", "target_observations": {"minimum": 20, "maximum": 30}, "observer_position_policy": "observer_wgs84_not_mentioned_object", "description_policy": "original_spanish_independent_observation", "ground_truth_capture_before_ranking": True, "evidence_required": True, "orientation_policy": "explicit_evidence_no_egocentric_to_cardinal_inference", "synthetic_excluded_from_accuracy": True}, "observations": [observation]}
        document["dataset_id"] = ground_truth_dataset_id(document); return document, raw

    def variants(self, source):
        variants = []
        for kind in KINDS:
            variants.append({"variant_id": f"v-{kind}", "kind": kind, "status": "reviewed", "text": source["queries"][0]["description"]["text"] if kind.startswith("es_") else "I am in a square next to a street.", "language": "es" if kind.startswith("es_") else "en", "generation": {"method": "original" if kind == "es_original" else ("model_assisted_cartographic_rewrite" if kind == "es_cartographic" else "model_assisted_translation"), "tool_or_model": "fixture", "version": "v1", "configuration_or_prompt": "fixture", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"] if kind == "es_original" else (["cartographic_filter"] if kind == "es_cartographic" else ["translation"]), "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []})
        document = json.loads((ROOT / "config/madrid_f53b_textual_variants_template.json").read_text()); raw=json.dumps(source,sort_keys=True).encode(); document["source_query_dataset"]={"dataset_id":source["dataset_id"],"sha256":hashlib.sha256(raw).hexdigest()}; document["observations"]=[{"source_query_id":"obs-001","source_input_sha256":"2"*64,"partition":"development","location_id":"loc-001","derivation_group_id":"group-001","toponyms":[],"orientation":{"status":"absent","cardinal":None,"bearing_degrees":None,"bearing_convention":None,"method":None,"uncertainty_degrees":None,"provenance":None,"verification_status":"not_applicable","relative_relations_present":False,"notes":None},"variants":variants,"notes":None}]; document["dataset_id"]=textual_variant_dataset_id(document); return document

    def ranking(self, gt, variants):
        rows=[]
        for gallery,catalog in self.catalogs.items():
            correct=gt["observations"][0]["catalog_assignments"][gallery]["candidate_id"]
            candidate=next(x for x in catalog.candidates if x.candidate_id==correct)
            others=[x for x in catalog.candidates if x.candidate_id!=correct][:9]
            results=[candidate,*others]
            for variant in variants["observations"][0]["variants"]:
                rows.append({"source_query_id":"obs-001","partition":"development","variant_id":variant["variant_id"],"kind":variant["kind"],"review_status":"reviewed","gallery_id":gallery,"top_k":10,"results":[{"rank":i,"candidate_id":x.candidate_id,"latitude":x.latitude,"longitude":x.longitude,"cosine_similarity":1-i/100} for i,x in enumerate(results,1)],"top1_margin":.01,"spatial_dispersion_m":1.0,"transformation_ms":1.0,"retrieval_ms":2.0,"pipeline_elapsed_ms":2.1})
        raw=json.dumps(variants,sort_keys=True).encode(); report={"schema_version":"1.0","contract_version":"f5-variant-ranking-report-v1","report_id":"","sidecar":{"dataset_id":variants["dataset_id"],"sha256":hashlib.sha256(raw).hexdigest(),"transformation_run_id":None},"retrieval":{"checkpoint_sha256":"3"*64,"gallery_ids":["madrid-25m","madrid-50m"],"top_k":10,"ranking_method":"exhaustive_cosine","tie_break":"candidate_id_ascending","scores_fused":False,"coordinates_fused":False},"rankings":rows,"comparisons":[],"cross_gallery":[],"geographic_accuracy_available":False,"limitations":["fixture"]}; report["report_id"]=variant_ranking_report_id(report); return report,raw

    def test_validated_gt_assigns_both_catalogs_and_evaluates_metrics(self):
        source=self.source(); gt,source_raw=self.gt(source); summary=validate_ground_truth_dataset(gt,source,self.catalogs,source_sha256=hashlib.sha256(source_raw).hexdigest()); self.assertTrue(summary["geographic_evaluation_ready"]); self.assertNotEqual(gt["observations"][0]["catalog_assignments"]["madrid-25m"]["candidate_id"],gt["observations"][0]["catalog_assignments"]["madrid-50m"]["candidate_id"])
        variants=self.variants(source); report,variant_raw=self.ranking(gt,variants); evaluation=evaluate_variant_rankings(gt,variants,report,gt_sha256="4"*64,variant_sha256=hashlib.sha256(variant_raw).hexdigest(),ranking_sha256="5"*64); self.assertEqual(len(evaluation["metrics"]),10); self.assertEqual(len(evaluation["variant_comparisons"]),8); self.assertTrue(all(row["recall_at_k"]["1"]==1 for row in evaluation["metrics"])); self.assertEqual(evaluation["evaluation_id"],geographic_evaluation_id(evaluation)); validate_document(evaluation,"f5_geographic_evaluation")

    def test_pending_and_synthetic_gt_cannot_enter_accuracy(self):
        source=self.source(validated=False); gt,raw=self.gt(source,validated=False); summary=validate_ground_truth_dataset(gt,source,self.catalogs,source_sha256=hashlib.sha256(raw).hexdigest()); self.assertFalse(summary["geographic_evaluation_ready"])
        source=self.source(); source["queries"][0]["provenance"]["source_type"]="synthetic"; source["dataset_id"]=query_dataset_id(source); gt,raw=self.gt(source)
        with self.assertRaises(F54ValidationError): validate_ground_truth_dataset(gt,source,self.catalogs,source_sha256=hashlib.sha256(raw).hexdigest())

    def test_orientation_requires_evidence_and_gt_leakage_is_rejected(self):
        source=self.source(); gt,raw=self.gt(source); gt["observations"][0]["orientation"].update(status="verified",cardinal="north",uncertainty_degrees=5.0,verification_method="compass",evidence_ids=[]); gt["dataset_id"]=ground_truth_dataset_id(gt)
        with self.assertRaises(F54ValidationError): validate_ground_truth_dataset(gt,source,self.catalogs,source_sha256=hashlib.sha256(raw).hexdigest())
        gt,_=self.gt(source); variants=self.variants(source); report,variant_raw=self.ranking(gt,variants); report["retrieval"]["scores_fused"]=True; report["report_id"]=variant_ranking_report_id(report)
        with self.assertRaises(F54ValidationError): evaluate_variant_rankings(gt,variants,report,gt_sha256="4"*64,variant_sha256=hashlib.sha256(variant_raw).hexdigest(),ranking_sha256="5"*64)

    def test_outside_coverage_and_boundary_are_distinguished_per_catalog(self):
        bbox=self.config["region"]["bbox"]; gap25=assign_reference(bbox["south"]+.000001,bbox["west"]+.000001,self.catalogs["madrid-25m"]); gap50=assign_reference(bbox["south"]+.000001,bbox["west"]+.000001,self.catalogs["madrid-50m"]); self.assertEqual(gap25["status"],"outside_catalog_coverage"); self.assertEqual(gap50["status"],"outside_catalog_coverage")
        candidate=self.catalogs["madrid-50m"].candidates[0]; lat,lon=epsg25830_to_wgs84(candidate.center_easting_m+25,candidate.center_northing_m); self.assertEqual(assign_reference(lat,lon,self.catalogs["madrid-50m"])["status"],"boundary_ambiguous")

    def test_missing_ranking_remains_recall_failure_and_thresholds_validate(self):
        source=self.source(); gt,_=self.gt(source); variants=self.variants(source); report,variant_raw=self.ranking(gt,variants); report["rankings"]=[row for row in report["rankings"] if row["kind"]!="en_cartographic"]; report["report_id"]=variant_ranking_report_id(report); evaluation=evaluate_variant_rankings(gt,variants,report,gt_sha256="4"*64,variant_sha256=hashlib.sha256(variant_raw).hexdigest(),ranking_sha256="5"*64); rows=[row for row in evaluation["metrics"] if row["variant_kind"]=="en_cartographic"]; self.assertTrue(all(row["recall_at_k"]["1"]==0 for row in rows)); self.assertTrue(all(row["rankings_observed"]==0 for row in rows))
        with self.assertRaises(F54ValidationError): evaluate_variant_rankings(gt,variants,report,gt_sha256="4"*64,variant_sha256=hashlib.sha256(variant_raw).hexdigest(),ranking_sha256="5"*64,distance_thresholds_m=(100,25))

    def test_five_variant_link_and_review_are_required(self):
        source=self.source(); gt,_=self.gt(source); variants=self.variants(source); variants["observations"][0]["variants"].pop(); report,variant_raw=self.ranking(gt,self.variants(source))
        with self.assertRaises(F54ValidationError): evaluate_variant_rankings(gt,variants,report,gt_sha256="4"*64,variant_sha256=hashlib.sha256(json.dumps(variants,sort_keys=True).encode()).hexdigest(),ranking_sha256="5"*64)
        variants=self.variants(source); variants["observations"][0]["variants"][-1]["status"]="generated"; variants["observations"][0]["variants"][-1]["review_status"]="pending"; raw=json.dumps(variants,sort_keys=True).encode(); report,_=self.ranking(gt,self.variants(source)); report["sidecar"].update(dataset_id=variants["dataset_id"],sha256=hashlib.sha256(raw).hexdigest()); report["report_id"]=variant_ranking_report_id(report); evaluation=evaluate_variant_rankings(gt,variants,report,gt_sha256="4"*64,variant_sha256=hashlib.sha256(raw).hexdigest(),ranking_sha256="5"*64); self.assertGreater(evaluation["coverage"]["observation_excluded_counts"]["variant_not_reviewed"],0)

    def test_evidence_reference_hash_and_timestamp_are_verifiable(self):
        source=self.source(); gt,raw=self.gt(source); evidence=gt["observations"][0]["observer_reference"]["evidence"][0]
        for field,value in (("logical_reference","../secret"),("sha256","invalid"),("captured_at_utc","2026-10-20")):
            original=evidence[field]; evidence[field]=value; gt["dataset_id"]=ground_truth_dataset_id(gt)
            with self.assertRaises(F54ValidationError): validate_ground_truth_dataset(gt,source,self.catalogs,source_sha256=hashlib.sha256(raw).hexdigest())
            evidence[field]=original


if __name__ == "__main__": unittest.main()
