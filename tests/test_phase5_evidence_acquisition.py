import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_evidence_acquisition import F55EvidenceError, attach_download, build_complementary_review_queue, build_review_queue, canonical_bytes, DownloadedAsset, import_approved_field_records, import_approved_panoramax_reviews, inventory_id, parse_panoramax_response, review_queue_id, select_review_items, sha256_bytes, upgrade_visual_review_queue, validate_field_record, validate_inventory, validate_review_queue
from src.tfg_phase0.f5_ground_truth_evaluation import validate_ground_truth_dataset
from src.tfg_phase0.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]


class Phase5EvidenceAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.config=load_region_config(ROOT/"config/madrid.yaml"); cls.catalogs={}
        for size in (25,50):
            path=Path(cls.temp.name)/f"manifest-{size}.json"; write_manifest(build_catalog(cls.config,spacing_m=size),path); cls.catalogs[f"madrid-{size}m"]=load_verified_f1_catalog(path,cls.config)
        cls.raw=(ROOT/"tests/fixtures/f55_panoramax_response.geojson").read_bytes()

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def inventory(self): return parse_panoramax_response(self.raw,endpoint_url="https://example.test/search?bbox=x",retrieved_at_utc="2026-10-20T10:00:00Z",catalogs=self.catalogs)

    def test_parse_optional_metadata_license_hash_and_assignments(self):
        inventory=self.inventory(); self.assertEqual(len(inventory["items"]),3); self.assertEqual(inventory["inventory_id"],inventory_id(inventory)); self.assertEqual(validate_inventory(inventory,self.catalogs)["with_horizontal_accuracy"],2); validate_document(inventory,"f5_panoramax_inventory"); self.assertEqual(inventory["source"]["response_sha256"],sha256_bytes(self.raw)); missing=next(x for x in inventory["items"] if x["item_id"]=="item-b"); self.assertIsNone(missing["camera_position"]["horizontal_accuracy_m"]); self.assertEqual(missing["catalog_assignments"]["madrid-25m"]["status"],"accuracy_unavailable"); self.assertEqual(missing["license"]["identifier"],"CC-BY-SA-4.0")
        payload=json.loads(self.raw); payload.pop("type"); without_type=parse_panoramax_response(json.dumps(payload).encode(),endpoint_url="x",retrieved_at_utc="2026-10-20T10:00:00Z",catalogs=self.catalogs); self.assertEqual(len(without_type["items"]),3)

    def test_invalid_license_outside_bbox_and_duplicates_are_rejected(self):
        payload=json.loads(self.raw); payload["features"][0]["properties"]["license"]="unknown"
        with self.assertRaises(F55EvidenceError): parse_panoramax_response(json.dumps(payload).encode(),endpoint_url="x",retrieved_at_utc="2026-10-20T10:00:00Z",catalogs=self.catalogs)
        payload=json.loads(self.raw); payload["features"][0]["geometry"]["coordinates"]=[0,0]
        with self.assertRaises(F55EvidenceError): parse_panoramax_response(json.dumps(payload).encode(),endpoint_url="x",retrieved_at_utc="2026-10-20T10:00:00Z",catalogs=self.catalogs)
        payload=json.loads(self.raw); payload["features"].append(payload["features"][0])
        with self.assertRaises(F55EvidenceError): parse_panoramax_response(json.dumps(payload).encode(),endpoint_url="x",retrieved_at_utc="2026-10-20T10:00:00Z",catalogs=self.catalogs)

    def test_spatial_selection_and_pending_queue_are_deterministic(self):
        inventory=self.inventory(); first=select_review_items(inventory["items"],limit=3,max_per_collection=2); second=select_review_items(list(reversed(inventory["items"])),limit=3,max_per_collection=2); self.assertEqual(first,second); self.assertEqual(len(first),3); queue=build_review_queue(inventory,first); self.assertEqual(queue["review_queue_id"],review_queue_id(queue)); self.assertEqual(validate_review_queue(queue),{"pending":3,"approved":0,"rejected":0}); validate_document(queue,"f5_panoramax_review"); self.assertTrue(all(row["review"]["status"]=="pending" for row in queue["records"]))

    def test_download_attachment_and_review_state_validation(self):
        inventory=self.inventory(); original_id=inventory["inventory_id"]; queue=build_review_queue(inventory,["item-a"]); raw=b"fixture-image"; asset=DownloadedAsset("assets/item-a-thumb.jpg","https://example.test/item-a-thumb.jpg","2026-10-20T10:00:00Z",len(raw),hashlib.sha256(raw).hexdigest(),"image/jpeg"); attach_download(queue,"item-a","thumb",asset); self.assertEqual(inventory["inventory_id"],original_id); self.assertIsNone(next(x for x in inventory["items"] if x["item_id"]=="item-a")["assets"]["thumb"]["download"]); record=queue["records"][0]; record["review"].update(status="approved",reviewer="human",reviewed_at_utc="2026-10-20T11:00:00Z",license_verified=True,camera_position_verified=True,description_matches_evidence=True,orientation_usable=False,original_spanish_description="Veo una plaza y edificios junto a una calle.",acceptance_reasons=["metadata y evidencia revisadas"]); queue["review_queue_id"]=review_queue_id(queue); self.assertEqual(validate_review_queue(queue)["approved"],1); bad=copy.deepcopy(queue); bad["records"][0]["review"]["acceptance_reasons"]=[]; bad["review_queue_id"]=review_queue_id(bad)
        with self.assertRaises(F55EvidenceError): validate_review_queue(bad)
        duplicate=build_review_queue(inventory,["item-a","item-b"]); attach_download(duplicate,"item-a","thumb",asset); second=DownloadedAsset("assets/item-b-thumb.jpg","https://example.test/item-b-thumb.jpg","2026-10-20T10:00:00Z",len(raw),asset.sha256,"image/jpeg"); attach_download(duplicate,"item-b","thumb",second)
        with self.assertRaises(F55EvidenceError): validate_review_queue(duplicate)

    def field_record(self,status="approved"):
        return {"schema_version":"1.0","contract_version":"f55-field-observation-v1","record_id":"field-001","location_id":"loc-001","derivation_group_id":"group-001","partition":"development","captured_at_utc":"2026-10-20T10:00:00Z","device":"fixture-device","observer_position":{"latitude":40.416,"longitude":-3.704,"crs":"EPSG:4326","horizontal_accuracy_m":2.0,"source":"measured_observer_position"},"gnss_readings":[{"latitude":40.416,"longitude":-3.704,"horizontal_accuracy_m":2.0,"captured_at_utc":"2026-10-20T10:00:00Z"}],"orientation":{"status":"absent","cardinal":None,"bearing_degrees":None,"uncertainty_degrees":None,"verification_method":None,"evidence_ids":[],"egocentric_relations_present":False,"notes":None},"original_spanish_description":"Estoy en una plaza junto a una calle estrecha.","evidence":[{"evidence_id":"ev-1","kind":"survey_record","logical_path":"evidence/record.json","sha256":hashlib.sha256(b"evidence").hexdigest(),"description":"fixture","captured_at_utc":"2026-10-20T10:00:00Z"}],"consent_or_data_policy":"fixture","limitations":[],"review":{"status":status,"reviewer":"reviewer" if status!="pending" else None,"reviewed_at_utc":"2026-10-20T11:00:00Z" if status!="pending" else None,"validation_method":"independent fixture review" if status=="approved" else None,"notes":None}}

    def test_field_import_only_approved_and_verifies_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/"evidence").mkdir(); (root/"evidence/record.json").write_bytes(b"evidence"); approved=self.field_record(); pending=self.field_record("pending"); pending["record_id"]="field-002"; pending["location_id"]="loc-002"; pending["derivation_group_id"]="group-002"; queries,gt,counts=import_approved_field_records([approved,pending],evidence_root=root,catalogs=self.catalogs); self.assertEqual(counts,{"pending":1,"approved":1,"rejected":0}); self.assertEqual(len(queries["queries"]),1); self.assertEqual(queries["queries"][0]["provenance"]["source_type"],"human_in_situ"); validate_ground_truth_dataset(gt,queries,self.catalogs,source_sha256=gt["source_query_dataset"]["sha256"]); (root/"evidence/record.json").write_bytes(b"tampered")
            with self.assertRaises(F55EvidenceError): import_approved_field_records([approved],evidence_root=root,catalogs=self.catalogs)

    def test_incomplete_field_record_cannot_be_approved(self):
        record=self.field_record(); record["gnss_readings"]=[]
        with self.assertRaises(F55EvidenceError): validate_field_record(record)

    def test_panoramax_import_requires_approved_review_accuracy_and_asset(self):
        inventory=self.inventory(); queue=build_review_queue(inventory,["item-a"])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/"assets").mkdir(); raw=b"image"; (root/"assets/item-a-thumb.jpg").write_bytes(raw); attach_download(queue,"item-a","thumb",DownloadedAsset("assets/item-a-thumb.jpg","https://example.test/item-a-thumb.jpg","2026-10-20T10:00:00Z",len(raw),hashlib.sha256(raw).hexdigest(),"image/jpeg")); review=queue["records"][0]["review"]; review.update(status="approved",reviewer="human",reviewed_at_utc="2026-10-20T11:00:00Z",license_verified=True,camera_position_verified=True,description_matches_evidence=True,orientation_usable=False,original_spanish_description="Estoy en una plaza junto a varios edificios.",acceptance_reasons=["revisión humana completa"]); queue["review_queue_id"]=review_queue_id(queue); queries,gt,counts=import_approved_panoramax_reviews(queue,evidence_root=root,catalogs=self.catalogs); self.assertEqual(counts["approved"],1); self.assertEqual(queries["queries"][0]["provenance"]["source_type"],"existing_dataset"); validate_ground_truth_dataset(gt,queries,self.catalogs,source_sha256=gt["source_query_dataset"]["sha256"])
            missing=build_review_queue(inventory,["item-b"]); missing_review=missing["records"][0]["review"]; missing_review.update(status="approved",reviewer="human",reviewed_at_utc="2026-10-20T11:00:00Z",license_verified=True,camera_position_verified=True,description_matches_evidence=True,orientation_usable=False,original_spanish_description="Descripción revisada.",acceptance_reasons=["revisada"]); missing["review_queue_id"]=review_queue_id(missing)
            with self.assertRaises(F55EvidenceError): import_approved_panoramax_reviews(missing,evidence_root=root,catalogs=self.catalogs)

    def test_visual_review_is_separate_from_gt_approval(self):
        inventory=self.inventory(); queue=build_review_queue(inventory,["item-a"]); original=copy.deepcopy(queue["records"][0]); decisions={"contract_version":"f55b-visual-review-decisions-v1","reviewer":"responsable","recorded_at_utc":"2026-10-20T11:00:00Z","decisions":[{"item_id":"item-a","suitability":"suitable","visible_observations":["Plaza visible"],"proposed_spanish_description":"Estoy en una plaza.","notes":"piloto"}]}; reviewed=upgrade_visual_review_queue(queue,decisions); record=reviewed["records"][0]; self.assertEqual(reviewed["contract_version"],"f55-panoramax-review-v2"); self.assertEqual(record["visual_review"]["status"],"reviewed"); self.assertTrue(record["visual_review"]["benchmark_main_eligible"]); self.assertEqual(record["visual_review"]["description_final_review_status"],"pending"); self.assertEqual(record["review"]["status"],"pending"); self.assertEqual(record["camera_position"],original["camera_position"]); self.assertEqual(record["license"],original["license"]); self.assertEqual(record["assets"],original["assets"]); self.assertEqual(record["catalog_assignments"],original["catalog_assignments"]); self.assertEqual(validate_review_queue(reviewed),{"pending":1,"approved":0,"rejected":0}); validate_document(reviewed,"f5_panoramax_review")

    def test_complementary_queue_has_remaining_items_without_overlap(self):
        inventory=self.inventory(); primary=build_review_queue(inventory,["item-a"]); complementary=build_complementary_review_queue(inventory,primary); left={row["item_id"] for row in primary["records"]}; right={row["item_id"] for row in complementary["records"]}; self.assertFalse(left & right); self.assertEqual(left|right,{row["item_id"] for row in inventory["items"]}); self.assertEqual(complementary["contract_version"],"f55-panoramax-review-v2"); self.assertTrue(all(row["visual_review"]["status"]=="pending" for row in complementary["records"])); validate_document(complementary,"f5_panoramax_review")


if __name__=="__main__": unittest.main()
