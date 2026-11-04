import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.visual_postprocessor import PrecomputedVisualPostprocessor, VisualPostprocessorError, query_identity


def retrieval():
    return {"gallery_id":"madrid-50m","visual_dataset_id":"visual","embedding_dataset_id":"embedding","results":[{"rank":rank,"candidate_id":f"c{rank}","latitude":40.0+rank/1000,"longitude":-3.0,"cosine_similarity":.6-rank/100} for rank in range(1,51)]}


class VisualPostprocessorTests(unittest.TestCase):
    def bundle(self,path,entries):
        path.write_text(json.dumps({"contract_version":"atlas-precomputed-visual-bundle-v2","bundle_id":"bundle-test","reserve_k":50,"models":["Qwen/Qwen3-VL-8B-Instruct"],"entries":entries}))

    def test_precomputed_result_changes_order_and_keeps_structured_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"bundle.json";base=retrieval();identity=query_identity("query","es_original",base)
            entry={"request_id":identity,"reserve_candidate_ids":[f"c{i}" for i in range(1,51)],"final_candidate_ids":["c11"]+[f"c{i}" for i in range(1,10)],"model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":"r"},"policy_id":"p","evidence":[{"candidate_id":"c11","reason":"exclusive_support"}]};self.bundle(path,[entry])
            result=PrecomputedVisualPostprocessor(path).apply(query_text="query",processing_variant="es_original",retrieval=base)
            self.assertEqual(result["status"],"applied");self.assertEqual(result["final_results"][0]["candidate_id"],"c11");self.assertEqual(len(result["baseline_results"]),10);self.assertEqual(result["evidence"][0]["reason"],"exclusive_support")

    def test_missing_result_explicitly_falls_back_to_ct2l(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"bundle.json";self.bundle(path,[]);base=retrieval();result=PrecomputedVisualPostprocessor(path).apply(query_text="missing",processing_variant="es_original",retrieval=base)
            self.assertEqual(result["status"],"fallback_baseline");self.assertEqual(result["final_results"],base["results"][:10])

    def test_incompatible_baseline_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"bundle.json";base=retrieval();identity=query_identity("query","es_original",base);self.bundle(path,[{"request_id":identity,"reserve_candidate_ids":["x"],"final_candidate_ids":[f"c{i}" for i in range(1,11)],"model":{},"policy_id":"p"}])
            with self.assertRaises(VisualPostprocessorError):PrecomputedVisualPostprocessor(path).apply(query_text="query",processing_variant="es_original",retrieval=base)


if __name__=="__main__":unittest.main()
