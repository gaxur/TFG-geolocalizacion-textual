import copy,json
from pathlib import Path
import unittest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_validation import load_verified_f1_catalog
from src.tfg_phase0.f5_text_transform import GenerationConfig,TransformResult,TransformerMetadata
from src.tfg_phase0.h11_h25_independent import H11H25Error,build_dataset,build_plan,evaluate,historical_rows,run_rankings,transform_dataset
ROOT=Path(__file__).resolve().parents[1]
class Transformer:
 metadata=TransformerMetadata("fake","Qwen/Qwen3-8B","b968826d9c46dd6066d109eabc6255188de91218","Qwen/Qwen3-8B","r","a"*64,True)
 def __init__(self): self.calls=[]
 def transform(self,text,task,names,config):
  self.calls.append((text,task,tuple(names))); numbers=" ".join(__import__("re").findall(r"\d+",text)); output="A building by a street, to my left and right, in front and behind. "+" ".join(names)+" "+numbers; return TransformResult(output.strip(),output.strip(),1.0)
class Retriever:
 gallery_ids=("madrid-25m","madrid-50m")
 def __init__(self): self.calls=[]
 def retrieve_many(self,*,gallery_ids,query_id,text,language,k):
  self.calls.append((tuple(gallery_ids),query_id,text,language,k)); return {"model":{"checkpoint_sha256":"d"*64},"timings_ms":{"total":1.0},"retrievals":[{"gallery_id":g,"results":[{"rank":i,"candidate_id":f"{g}-{i}","latitude":40.415+i*.00001,"longitude":-3.704,"cosine_similarity":1-i/100} for i in range(1,11)]} for g in gallery_ids]}
class H11H25Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  paths=[ROOT/"results/generated/f5/f56/f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a/dataset.json",ROOT/"results/generated/f5/f59-h01-h02/inputs/dataset.json",ROOT/"results/generated/f5/f59-h03-h10/inputs/dataset.json"]
  if not all(path.is_file() for path in paths): raise unittest.SkipTest("artefactos históricos locales no disponibles")
  cfg=load_region_config(ROOT/"config/madrid.yaml"); manifests=[ROOT/"data/processed/catalog/manifest-25m.json",ROOT/"data/processed/catalog/manifest-50m.json"]
  if not all(path.is_file() for path in manifests): raise unittest.SkipTest("catálogos locales no disponibles")
  cls.cats={g:load_verified_f1_catalog(ROOT/f"data/processed/catalog/manifest-{n}m.json",cfg) for g,n in (("madrid-25m",25),("madrid-50m",50))}; cls.spec=json.loads((ROOT/"config/madrid_h11_h25_independent.json").read_text()); cls.hist=historical_rows(*(json.loads(x.read_text()) for x in paths)); cls.dataset=build_dataset(cls.spec,cls.cats,cls.hist)
 def test_dataset_counts_categories_h16_and_d004(self):
  self.assertEqual(len(self.dataset["observations"]),15); counts={c:sum(x["category"]==c for x in self.dataset["observations"]) for c in ("simple","intermediate","complex")}; self.assertEqual(counts,{"simple":5,"intermediate":5,"complex":5}); h16=next(x for x in self.dataset["observations"] if x["query_id"]=="H16"); self.assertEqual(h16["scene_type"],"interior_user_photo"); self.assertIsNone(h16["source"]["heading_degrees"]); self.assertTrue(all(x["reference"]["inside_d004"] for x in self.dataset["observations"]))
 def test_invalid_id_coordinate_and_duplicate_are_rejected(self):
  bad=copy.deepcopy(self.spec); bad["observations"][0]["query_id"]="H99"
  with self.assertRaises(H11H25Error): build_dataset(bad,self.cats,self.hist)
  bad=copy.deepcopy(self.spec); bad["observations"][0]["latitude"]=41
  dataset=build_dataset(bad,self.cats,self.hist); self.assertFalse(dataset["observations"][0]["reference"]["inside_d004"])
  bad=copy.deepcopy(self.spec); bad["observations"][1]["text"]=bad["observations"][0]["text"]
  with self.assertRaises(H11H25Error): build_dataset(bad,self.cats,self.hist)
 def test_exactly_fifteen_qwen_calls_and_no_fallback(self):
  transformer=Transformer(); run=transform_dataset(self.dataset,transformer,GenerationConfig()); self.assertEqual(len(transformer.calls),15); self.assertTrue(all(x[1]=="translate_en_cartographic" for x in transformer.calls)); plan=build_plan(self.dataset,run); self.assertEqual(len(plan["controls"]),30); self.assertEqual(plan["excluded"],[])
  broken=copy.deepcopy(run); broken["records"][0]["status"]="rejected"; plan=build_plan(self.dataset,broken); self.assertEqual(len(plan["controls"]),29); self.assertEqual(plan["excluded"][0]["reason"],"qwen_failed_no_fallback")
 def test_thirty_retrieval_calls_sixty_rows_and_metrics(self):
  run=transform_dataset(self.dataset,Transformer()); plan=build_plan(self.dataset,run); retriever=Retriever(); rankings=run_rankings(plan,retriever); self.assertEqual(len(retriever.calls),30); self.assertTrue(all(x[0]==("madrid-25m","madrid-50m") for x in retriever.calls)); self.assertEqual(len(rankings["rows"]),60); report=evaluate(self.dataset,rankings,run); self.assertEqual(report["coverage"],{"observations":15,"qwen_generated":15,"rankings":60,"exterior":14,"interior":1}); self.assertTrue(any(x["group"]=="interior_h16" and x["count"]==1 for x in report["metrics"])); self.assertEqual(len(report["paired"]),2)
if __name__=="__main__": unittest.main()
