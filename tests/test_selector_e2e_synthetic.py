import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.mapillary_cache import MapillaryCache, MapillaryCacheError
from src.tfg_phase0.selector_e2e import build_physical_plan, evaluate_synthetic_rankings, execute_physical_plan, freeze_arm_rankings, physical_task_id, project_results
from src.tfg_phase0.symmetric_visual_reranking import freeze_symmetric_policy


def claim(claim_id, orientation=False):
    return {"claim_id": claim_id, "source_text_sha256": "0" * 64, "kind": "egocentric_relation" if orientation else "object_presence", "value": {"relation": "left_of_observer", "subject_type": "building"} if orientation else {"object_type": "building"}, "evidence": {"text": "left" if orientation else "building", "span": {"start": 0, "end": 4 if orientation else 8}}, "specificity": "distinctive", "requires_ocr": False, "requires_orientation": orientation}


class SelectorEndToEndSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.claims = {"Q": [claim("claim-object"), claim("claim-orientation", True)]}
        self.models = {"qwen3-vl-2b": {"model_id": "Qwen/Qwen3-VL-2B-Instruct", "revision": "2b-rev", "weight_sha256": "2" * 64}, "qwen3-vl-8b": {"model_id": "Qwen/Qwen3-VL-8B-Instruct", "revision": "8b-rev", "weight_sha256": ["8" * 64]}}
        self.baseline = [{"rank": index, "candidate_id": f"c{index}", "latitude": 40 + index * 0.00001, "longitude": -3.0, "cosine_similarity": 1 - index / 1000} for index in range(1, 51)]
        self.fixture_queries = [{"query_id": "Q", "baseline_results": self.baseline}]
        common = {"query_id": "Q", "candidate_id": "c11", "image_id": "1", "sequence_id": "s1", "orientation_comparable": False}
        self.arms = {"coverage": {"associations": [common, {"query_id": "Q", "candidate_id": "c10", "image_id": "2", "sequence_id": "s2", "orientation_comparable": False}]}, "geometric": {"associations": [common, {"query_id": "Q", "candidate_id": "c9", "image_id": "3", "sequence_id": "s3", "orientation_comparable": False}]}}

    def test_complete_pipeline_acquires_deduplicates_resumes_freezes_and_evaluates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Synthetic authorization exists only in this temporary fixture.
            authorization = {"approved": True, "terms_reviewed": True, "fixture_only": True}
            self.assertTrue(authorization["approved"] and authorization["fixture_only"])
            cache = MapillaryCache(root / "cache", max_gb=1, ttl_hours=1)
            assets = {}
            for image_id, raw in (("1", b"shared-image"), ("2", b"coverage-image"), ("3", b"geometric-image")):
                assets[image_id] = cache.store(image_id, raw, {"provider": "FakeTransport", "license": "synthetic"})
            # Shared asset is acquired once and conflicting bytes are rejected.
            self.assertEqual(cache.store("1", b"shared-image", {"provider": "FakeTransport"})["sha256"], assets["1"]["sha256"])
            with self.assertRaises(MapillaryCacheError):
                cache.store("1", b"corrupt", {"provider": "FakeTransport"})
            plan = build_physical_plan(self.arms, assets, self.claims, self.models)
            self.assertLess(plan["summary"]["physical_tasks"], plan["summary"]["logical_jobs"])
            object_claim = self.claims["Q"][0]
            reused_id = physical_task_id(self.models["qwen3-vl-2b"], assets["1"]["sha256"], object_claim, policy_unverifiable=False)
            previous = {reused_id: {"status": "valid", "verdict": "supported"}}
            calls = {"qwen3-vl-2b": [], "qwen3-vl-8b": []}
            results = {}
            for model_key in self.models:
                checkpoint = root / f"{model_key}.jsonl"
                failed = {"done": False}
                def flaky(task, model_key=model_key):
                    calls[model_key].append(task["task_id"])
                    if model_key == "qwen3-vl-8b" and not failed["done"]:
                        failed["done"] = True
                        raise RuntimeError("synthetic interruption")
                    return "supported" if task["image_id"] in {"1", "3"} else "unverifiable"
                if model_key == "qwen3-vl-8b":
                    with self.assertRaises(RuntimeError):
                        execute_physical_plan(plan, model_key=model_key, checkpoint_path=checkpoint, previous_results={}, execute=flaky)
                    calls_before = len(calls[model_key])
                    results[model_key] = execute_physical_plan(plan, model_key=model_key, checkpoint_path=checkpoint, previous_results={}, execute=lambda task: (calls[model_key].append(task["task_id"]) or ("supported" if task["image_id"] in {"1", "3"} else "unverifiable")))
                    self.assertGreater(len(calls[model_key]), calls_before)
                else:
                    results[model_key] = execute_physical_plan(plan, model_key=model_key, checkpoint_path=checkpoint, previous_results=previous, execute=flaky)
                    self.assertNotIn(reused_id, calls[model_key])
            projected = {(arm, model): project_results(plan, results[model], arm=arm, model_key=model) for arm in self.arms for model in self.models}
            # The shared physical task projects into both arms with one task ID.
            shared_ids = {row["physical_task_id"] for key, rows in projected.items() for row in rows if row["image_id"] == "1" and row["claim_id"] == "claim-object"}
            self.assertEqual(len(shared_ids), 2)  # one physical ID per model, not per arm
            policy = freeze_symmetric_policy()
            frozen_path = root / "frozen-rankings.json"
            frozen = freeze_arm_rankings(fixture_queries=self.fixture_queries, arm_manifests=self.arms, claims_by_query=self.claims, projected=projected, policy=policy, output_path=frozen_path)
            self.assertTrue(frozen_path.is_file())
            self.assertTrue(all(query["reranking"]["audit"]["candidate_set_invariant_top50"] for model in frozen["models"].values() for arm in model.values() for query in arm))
            frozen_bytes = frozen_path.read_bytes()
            # Synthetic GT only enters after the ranking file is frozen.
            evaluation = evaluate_synthetic_rankings(frozen, {"Q": {"latitude": 40.0001, "longitude": -3.0}})
            self.assertEqual(evaluation["reference_kind"], "synthetic_fixture")
            self.assertFalse(evaluation["real_ground_truth"])
            self.assertEqual(frozen_path.read_bytes(), frozen_bytes)

    def test_gt_in_pre_evaluation_inputs_is_rejected(self):
        bad_arms = json.loads(json.dumps(self.arms))
        bad_arms["coverage"]["ground_truth"] = {"latitude": 40}
        assets = {"1": {"sha256": hashlib.sha256(b"x").hexdigest()}}
        with self.assertRaisesRegex(ValueError, "GT"):
            build_physical_plan(bad_arms, assets, self.claims, self.models)

    def test_model_results_cannot_be_reused_across_models(self):
        image_sha = hashlib.sha256(b"x").hexdigest()
        self.assertNotEqual(physical_task_id(self.models["qwen3-vl-2b"], image_sha, self.claims["Q"][0], policy_unverifiable=False), physical_task_id(self.models["qwen3-vl-8b"], image_sha, self.claims["Q"][0], policy_unverifiable=False))

    def test_missing_physical_result_is_rejected(self):
        assets={"1":{"sha256":hashlib.sha256(b"1").hexdigest()},"2":{"sha256":hashlib.sha256(b"2").hexdigest()},"3":{"sha256":hashlib.sha256(b"3").hexdigest()}}
        plan=build_physical_plan(self.arms,assets,self.claims,self.models)
        with self.assertRaisesRegex(ValueError,"resultado físico ausente"):
            project_results(plan,{},arm="coverage",model_key="qwen3-vl-2b")

    def test_checkpoint_key_distinguishes_model_and_policy_for_same_image_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            shared_claim=self.claims["Q"][1];image_sha=hashlib.sha256(b"same").hexdigest();model=self.models["qwen3-vl-2b"];tasks=[]
            for policy in (False,True):
                task_id=physical_task_id(model,image_sha,shared_claim,policy_unverifiable=policy)
                tasks.append({"task_id":task_id,"model_key":"qwen3-vl-2b","image_id":"1","image_sha256":image_sha,"claim":shared_claim,"policy_unverifiable":policy})
            plan={"task_plan_id":"test-plan","tasks":tasks,"projections":[]}
            results=execute_physical_plan(plan,model_key="qwen3-vl-2b",checkpoint_path=Path(temporary)/"run.jsonl",previous_results={},execute=lambda task:"supported")
            self.assertEqual(len(results),2)


if __name__ == "__main__":
    unittest.main()
