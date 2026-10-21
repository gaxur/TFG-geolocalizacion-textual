import copy,hashlib,json
from pathlib import Path
import unittest
from src.tfg_phase0.f55c_experimental_evaluation import audit_benchmark,audit_variants,evaluate,ranking_id

ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/"results/generated/f5/f55c-final/f55c-synthetic-osm-sha256-bf7aea13116cda8e027343535f0a6d2de3bd6582aa09c6a65d1f14e9b24873c2/benchmark.json"

class Phase55cExperimentalTests(unittest.TestCase):
 def setUp(self):
  if not BENCH.is_file(): self.skipTest("benchmark F5.5c local no disponible")
  self.benchmark=json.loads(BENCH.read_text())
 def test_audit_does_not_approve_pending_benchmark(self):
  audit=audit_benchmark(self.benchmark); self.assertEqual(audit["summary"]["pending_human_review"],35); self.assertTrue(all(row["review_status"]=="pending" for row in audit["observations"])); self.assertFalse(audit["real_ground_truth"])
 def test_variant_audit_rejects_name_from_hidden_evidence(self):
  source=self.benchmark["observations"][0]; name=next(item["name"] for item in source["evidence"] if item["name"]); original=source["description"]["text"]; translated="Within the cartographic area there is a place of worship, buildings and urban facilities."
  variants=[{"variant_id":"o","kind":"es_original","status":"reviewed","text":original,"review_status":"reviewed"},{"variant_id":"v","kind":"en_toponym_preserved","status":"generated","text":translated+" "+name,"review_status":"pending"}]
  sidecar={"observations":[{"source_query_id":source["observation_id"],"partition":source["partition"],"variants":variants}]}; run={"records":[{"source_query_id":source["observation_id"],"kind":"en_toponym_preserved","output_text_sha256":hashlib.sha256((translated+" "+name).encode()).hexdigest(),"validation":{"structurally_valid":True}}]}; audit=audit_variants(sidecar,run,self.benchmark); self.assertIn("osm_toponym_introduced",audit["issues"][1]["issue_codes"])
 def test_evaluation_is_partitioned_and_never_official(self):
  rows=[]
  for source in self.benchmark["observations"][:2]:
   for gallery in ("madrid-25m","madrid-50m"):
    results=[{"rank":i,"candidate_id":source["reference"][gallery]["candidate_id"] if i==1 else f"{gallery}-x-{i}","latitude":source["reference"]["latitude"],"longitude":source["reference"]["longitude"],"cosine_similarity":1-i/100} for i in range(1,11)]
    rows.append({"source_query_id":source["observation_id"],"partition":source["partition"],"variant_kind":"es_original","gallery_id":gallery,"results":results,"retrieval_ms":1.0,"pipeline_elapsed_ms":1.1})
  rankings={"contract_version":"f55c-exploratory-rankings-v1","checkpoint_sha256":"d"*64,"gallery_ids":["madrid-25m","madrid-50m"],"ranking_method":"exhaustive_cosine","top_k":10,"rows":rows,"limitations":["synthetic_osm"]}; rankings["ranking_id"]=ranking_id(rankings); result=evaluate(self.benchmark,rankings,benchmark_sha256="a"*64,variants_sha256="b"*64,rankings_sha256="c"*64); self.assertFalse(result["protocol"]["official_f54_evaluation"]); self.assertEqual(result["coverage"]["officially_evaluable"],0); self.assertEqual({m["partition"] for m in result["metrics"]},{"all","development","evaluation"})

if __name__=="__main__": unittest.main()
