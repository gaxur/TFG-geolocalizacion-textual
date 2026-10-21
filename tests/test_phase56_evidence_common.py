import hashlib
from pathlib import Path
import tempfile
import unittest
from src.tfg_phase0.catalog import build_catalog,write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f56_evidence_common import EvidenceValidationError,import_approved_field_records,validate_field_record
from src.tfg_phase0.f5_ground_truth_evaluation import validate_ground_truth_dataset
ROOT=Path(__file__).resolve().parents[1]
class Phase56EvidenceCommonTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cfg=load_region_config(ROOT/"config/madrid.yaml"); cls.temp=tempfile.TemporaryDirectory(); cls.catalogs={}
  for n in (25,50):
   p=Path(cls.temp.name)/f"m-{n}.json"; write_manifest(build_catalog(cfg,spacing_m=n),p); cls.catalogs[f"madrid-{n}m"]=load_verified_f1_catalog(p,cfg)
 @classmethod
 def tearDownClass(cls): cls.temp.cleanup()
 def record(self,status="approved"):
  return {"schema_version":"1.0","contract_version":"f55-field-observation-v1","record_id":"field-1","location_id":"loc-1","derivation_group_id":"group-1","partition":"development","captured_at_utc":"2026-10-21T07:00:00Z","device":"device","observer_position":{"latitude":40.416,"longitude":-3.704,"crs":"EPSG:4326","horizontal_accuracy_m":2.0,"source":"measured_observer_position"},"gnss_readings":[{"latitude":40.416,"longitude":-3.704,"horizontal_accuracy_m":2.0,"captured_at_utc":"2026-10-21T07:00:00Z"}],"orientation":{"status":"absent","cardinal":None,"bearing_degrees":None,"uncertainty_degrees":None,"verification_method":None,"evidence_ids":[],"egocentric_relations_present":False,"notes":None},"original_spanish_description":"Estoy en una plaza junto a varios edificios y una calle.","evidence":[{"evidence_id":"ev-1","kind":"survey_record","logical_path":"ev/data.bin","sha256":hashlib.sha256(b"evidence").hexdigest(),"description":"registro","captured_at_utc":"2026-10-21T07:00:00Z"}],"consent_or_data_policy":"policy-v1","limitations":[],"review":{"status":status,"reviewer":"reviewer" if status=="approved" else None,"reviewed_at_utc":"2026-10-21T08:00:00Z" if status=="approved" else None,"validation_method":"independent" if status=="approved" else None,"notes":None}}
 def test_only_approved_records_import_and_hashes_verify(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t); (root/"ev").mkdir(); (root/"ev/data.bin").write_bytes(b"evidence"); approved=self.record(); pending=self.record("pending"); pending.update(record_id="field-2",location_id="loc-2",derivation_group_id="group-2"); source,gt,counts=import_approved_field_records([approved,pending],evidence_root=root,catalogs=self.catalogs); self.assertEqual(counts,{"pending":1,"approved":1,"rejected":0}); self.assertEqual(len(source["queries"]),1); validate_ground_truth_dataset(gt,source,self.catalogs,source_sha256=gt["source_query_dataset"]["sha256"])
 def test_incomplete_approved_record_rejected(self):
  r=self.record(); r["gnss_readings"]=[]
  with self.assertRaises(EvidenceValidationError): validate_field_record(r)
if __name__=="__main__": unittest.main()
