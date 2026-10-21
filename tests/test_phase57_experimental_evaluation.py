import copy,hashlib,json
from pathlib import Path
import unittest
import jsonschema
from src.tfg_phase0.f57_experimental_evaluation import F57Error,audit_variants,canonical_bytes,evaluate_approximate,evaluation_id,paired_comparisons,ranking_id,run_provisional_rankings
from src.tfg_phase0.validation import validate_document

ROOT=Path(__file__).resolve().parents[1]

def sidecar_and_run():
 observations=[]; records=[]
 for qid in ("SV-01","SV-02","SV-03","SV-04"):
  original="Estoy en una plaza con una torre a mi izquierda"
  variants=[]
  for kind,text in (("es_original",original),("es_cartographic",original),("en_conventional","I am in a square with a tower to my left"),("en_toponym_preserved","I am in a square with a tower to my left"),("en_cartographic","I am in a square with a tower to my left")):
   variants.append({"variant_id":f"{qid}-{kind}","kind":kind,"status":"reviewed" if kind=="es_original" else "generated","text":text,"language":"es" if kind.startswith("es_") else "en","review_status":"reviewed" if kind=="es_original" else "pending"})
   if kind!="es_original": records.append({"source_query_id":qid,"kind":kind,"output_text_sha256":hashlib.sha256(text.encode()).hexdigest(),"validation":{"structurally_valid":True}})
  observations.append({"source_query_id":qid,"variants":variants})
 return {"observations":observations},{"records":records}

def streetview():
 rows=[]
 for index,qid in enumerate(("SV-01","SV-02","SV-03","SV-04")):
  rows.append({"observation_id":qid,"link_coordinate":{"latitude":40.4+index*.001,"longitude":-3.7},"geography":{"link_point_assignments":{"madrid-25m":{"status":"assigned","candidate_id":f"madrid-25m-c1"},"madrid-50m":{"status":"assigned","candidate_id":f"madrid-50m-c1"}}}})
 return {"dataset_id":"f56-streetview-documentary-sha256-"+"5"*64,"observations":rows}

def rankings():
 rows=[]
 for qid in ("SV-01","SV-02","SV-03","SV-04"):
  for kind in ("es_original","es_cartographic","en_conventional","en_toponym_preserved","en_cartographic"):
   for gallery in ("madrid-25m","madrid-50m"):
     results=[{"rank":rank,"candidate_id":f"{gallery}-c{rank}","latitude":40.4+(rank-1)*.0001,"longitude":-3.7,"cosine_similarity":1-rank/100} for rank in range(1,11)]
     rows.append({"source_query_id":qid,"variant_id":f"{qid}-{kind}","variant_kind":kind,"language":"es","text_sha256":"1"*64,"gallery_id":gallery,"top_k":10,"results":results,"retrieval_ms":2.0,"pipeline_elapsed_ms":2.1})
 document={"schema_version":"1.0","contract_version":"f57-provisional-rankings-v1","ranking_id":"","checkpoint_sha256":"d"*64,"gallery_ids":["madrid-25m","madrid-50m"],"ranking_method":"exhaustive_cosine","top_k":10,"rows":rows,"limitations":["coordinates_not_used_for_retrieval"]}; document["ranking_id"]=ranking_id(document); return document

class Phase57Tests(unittest.TestCase):
 def test_provisional_runner_records_latency(self):
  class Retriever:
   gallery_ids=("madrid-25m","madrid-50m")
   def retrieve_many(self,*,gallery_ids,query_id,text,language,k):
    retrievals=[]
    for gallery in gallery_ids: retrievals.append({"gallery_id":gallery,"effective_k":10,"ranking_method":"exhaustive_cosine","tie_break":"candidate_id_ascending","results":[{"rank":rank,"candidate_id":f"{gallery}-{rank}","latitude":40.4,"longitude":-3.7,"cosine_similarity":1-rank/100} for rank in range(1,11)]})
    return {"model":{"checkpoint_sha256":"d"*64},"retrievals":retrievals,"timings_ms":{"total":1.5}}
  sidecar,run=sidecar_and_run(); audit=audit_variants(sidecar,run); report=run_provisional_rankings(sidecar,audit,Retriever(),gallery_ids=("madrid-25m","madrid-50m")); self.assertEqual(len(report["rows"]),40); self.assertTrue(all(row["retrieval_ms"]==1.5 and row["pipeline_elapsed_ms"]>=0 for row in report["rows"]))
 def test_audit_allows_twenty_and_rejects_coordinate_leak(self):
  sidecar,run=sidecar_and_run(); audit=audit_variants(sidecar,run); self.assertEqual(len(audit["eligible_pairs"]),20); bad=copy.deepcopy(sidecar); bad["observations"][0]["variants"][1]["text"]="40.4169, -3.7033"; audit=audit_variants(bad,run); self.assertIn("coordinate_leak",audit["issues"][1]["issue_codes"]); self.assertEqual(len(audit["eligible_pairs"]),19)
 def test_recall_georecall_haversine_and_official_separation(self):
  result=evaluate_approximate(streetview(),rankings(),streetview_sha256="a"*64,variants_sha256="b"*64,rankings_sha256="c"*64); metric=result["metrics"][0]; self.assertEqual(metric["recall_at_k"]["1"]["value"],1.0); self.assertEqual(metric["geo_recall_at_k"]["1"]["25"],.25); self.assertGreater(metric["top1_error_m"]["mean"],100); self.assertEqual(metric["retrieval_latency_ms"]["mean"],2.0); self.assertFalse(result["protocol"]["official_f54_evaluation"]); self.assertEqual(result["coverage"]["officially_evaluable"],0); self.assertIn("not_f54_metrics",result["limitations"]); self.assertEqual(result["evaluation_id"],evaluation_id(result)); validate_document(result,"f57_experimental_evaluation")
 def test_incomplete_rankings_are_rejected(self):
  report=rankings(); report["rows"][0]["results"].pop(); report["ranking_id"]=ranking_id(report)
  with self.assertRaises(F57Error): evaluate_approximate(streetview(),report,streetview_sha256="a"*64,variants_sha256="b"*64,rankings_sha256="c"*64)
 def test_missing_variant_is_not_zero_and_pairs_are_complete_case(self):
  report=rankings(); report["rows"]=[row for row in report["rows"] if not (row["source_query_id"]=="SV-04" and row["variant_kind"]=="en_cartographic")]; report["ranking_id"]=ranking_id(report); result=evaluate_approximate(streetview(),report,streetview_sha256="a"*64,variants_sha256="b"*64,rankings_sha256="c"*64); metric=next(row for row in result["metrics"] if row["gallery_id"]=="madrid-25m" and row["variant_kind"]=="en_cartographic"); self.assertEqual(metric["evaluated_count"],3); paired=next(row for row in result["paired_comparisons"] if row["gallery_id"]=="madrid-25m" and row["variant_kind"]=="en_cartographic"); self.assertEqual(paired["paired_count"],3)
 def test_schemas_are_valid_and_enforce_experimental_label(self):
  for name in ("f57_variant_audit","f57_experimental_evaluation"): jsonschema.Draft202012Validator.check_schema(json.loads((ROOT/f"schemas/{name}.schema.json").read_text()))

if __name__=="__main__": unittest.main()
