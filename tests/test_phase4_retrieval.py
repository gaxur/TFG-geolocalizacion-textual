import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_retrieval import build_retrieval_result, exhaustive_rank, normalize_l2
from src.tfg_phase0.f4_validation import F4ValidationError, embedding_dataset_id, load_verified_f1_50m, validate_embedding_bundle, validate_retrieval_result


ROOT = Path(__file__).resolve().parents[1]


class Phase4RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config = load_region_config(ROOT / "config/madrid.yaml")
        manifest_path = self.root / "f1.json"
        write_manifest(build_catalog(config, spacing_m=50), manifest_path)
        self.catalog = load_verified_f1_50m(manifest_path, config)
        self.ids = tuple(candidate.candidate_id for candidate in self.catalog.candidates[:9])
        self.visual = {"visual_dataset_id": "f4-madrid-visual-sha256-" + "1" * 64, "images": [{"candidate_id": candidate_id, "generation_status": "generated"} for candidate_id in self.ids]}
        self.visual_raw = b'{"fixture":true}\n'
        self.matrix = np.zeros((9, 768), dtype="<f4")
        for index in range(9):
            self.matrix[index, index] = 1.0
        embedding_dir = self.root / "embeddings"
        embedding_dir.mkdir()
        np.save(embedding_dir / "image_embeddings.npy", self.matrix, allow_pickle=False)
        ids_raw = b"".join((json.dumps({"candidate_id": candidate_id}, sort_keys=True, separators=(",", ":")) + "\n").encode() for candidate_id in self.ids)
        (embedding_dir / "candidate_ids.jsonl").write_bytes(ids_raw)
        self.document = {
            "schema_version": "2.0", "embedding_dataset_id": "f4-madrid-embeddings-sha256-" + "0" * 64,
            "contract_version": "f4-image-embeddings-v2", "generator_version": "phase4-crosstext2loc-embeddings-v1", "generator_source_sha256": "2" * 64,
            "visual_dataset": {"visual_dataset_id": self.visual["visual_dataset_id"], "manifest_sha256": hashlib.sha256(self.visual_raw).hexdigest()},
            "model": {"name": "CLIP-L/14@336", "architecture": "ViT-L/14@336px", "cvg_text_commit": "6910d2747a94fbe985309bde60cd4732bcbbf50f", "cvg_utils_sha256": "4" * 64, "openai_clip_commit": "dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1", "openai_clip_weights_filename": "ViT-L-14-336px.pt", "openai_clip_weights_sha256": "3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02", "text_context_length": 300},
            "checkpoint": {"filename": "long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth", "size_bytes": 1712649548, "sha256": "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d", "selection_status": "provisional_d013"},
            "preprocessing": {"policy": "official_openai_clip_preprocess", "input_width_px": 336, "input_height_px": 336, "image_color_mode": "RGB", "text_tokenizer": "clip.tokenize_context_300", "text_truncation": True},
            "environment": {"container_image_id": "sha256:" + "3" * 64, "python_version": "3.12", "torch_version": "test", "torchvision_version": "test", "cuda_version": "test", "device_type": "cuda", "inference_dtype": "float32"},
            "embedding": {"matrix_path": "embeddings/image_embeddings.npy", "matrix_sha256": hashlib.sha256((embedding_dir / "image_embeddings.npy").read_bytes()).hexdigest(), "candidate_ids_path": "embeddings/candidate_ids.jsonl", "candidate_ids_sha256": hashlib.sha256(ids_raw).hexdigest(), "candidate_ids_format": "jsonl_object_candidate_id_v1", "count": 9, "dimension": 768, "dtype": "float32", "byte_order": "little", "normalization": "l2", "row_order": "visual_manifest_order"},
        }
        self.document["embedding_dataset_id"] = embedding_dataset_id(self.document)

    def tearDown(self):
        self.temporary.cleanup()

    def test_valid_embedding_bundle(self):
        matrix, ids = validate_embedding_bundle(self.document, self.root, self.visual, self.visual_raw, self.catalog)
        self.assertEqual(matrix.shape, (9, 768))
        self.assertEqual(ids, self.ids)

    def test_rejects_visual_and_checkpoint_incompatibility(self):
        visual = copy.deepcopy(self.visual)
        visual["visual_dataset_id"] = "f4-madrid-visual-sha256-" + "9" * 64
        with self.assertRaises(F4ValidationError):
            validate_embedding_bundle(self.document, self.root, visual, self.visual_raw, self.catalog)
        document = copy.deepcopy(self.document)
        document["checkpoint"]["sha256"] = "9" * 64
        document["embedding_dataset_id"] = embedding_dataset_id(document)
        with self.assertRaises(F4ValidationError):
            validate_embedding_bundle(document, self.root, self.visual, self.visual_raw, self.catalog)

    def test_rejects_symlinked_embedding_artifact(self):
        matrix_path = self.root / "embeddings/image_embeddings.npy"
        target = self.root / "embeddings/matrix-target.npy"
        matrix_path.rename(target)
        matrix_path.symlink_to(target.name)
        with self.assertRaises(F4ValidationError):
            validate_embedding_bundle(self.document, self.root, self.visual, self.visual_raw, self.catalog)

    def test_rejects_wrong_shape_dtype_nonfinite_zero_and_reordered_ids(self):
        cases = []
        cases.append(np.ones((8, 768), dtype="<f4"))
        cases.append(np.ones((9, 767), dtype="<f4"))
        cases.append(self.matrix.astype(np.float64))
        nonfinite = self.matrix.copy(); nonfinite[0, 0] = np.nan; cases.append(nonfinite)
        zero = self.matrix.copy(); zero[0] = 0; cases.append(zero)
        for index, matrix in enumerate(cases):
            path = self.root / "embeddings/image_embeddings.npy"
            np.save(path, matrix, allow_pickle=False)
            document = copy.deepcopy(self.document)
            document["embedding"]["matrix_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            document["embedding_dataset_id"] = embedding_dataset_id(document)
            with self.subTest(index=index), self.assertRaises(F4ValidationError):
                validate_embedding_bundle(document, self.root, self.visual, self.visual_raw, self.catalog)
        np.save(self.root / "embeddings/image_embeddings.npy", self.matrix, allow_pickle=False)
        reversed_raw = b"".join((json.dumps({"candidate_id": candidate_id}, sort_keys=True, separators=(",", ":")) + "\n").encode() for candidate_id in reversed(self.ids))
        ids_path = self.root / "embeddings/candidate_ids.jsonl"; ids_path.write_bytes(reversed_raw)
        document = copy.deepcopy(self.document); document["embedding"]["candidate_ids_sha256"] = hashlib.sha256(reversed_raw).hexdigest(); document["embedding_dataset_id"] = embedding_dataset_id(document)
        with self.assertRaises(F4ValidationError): validate_embedding_bundle(document, self.root, self.visual, self.visual_raw, self.catalog)

    def test_normalization_and_zero_vector(self):
        vector = np.zeros(768, dtype=np.float32); vector[0] = 3; vector[1] = 4
        normalized = normalize_l2(vector)
        self.assertAlmostEqual(float(np.linalg.norm(normalized)), 1.0, places=6)
        with self.assertRaises(F4ValidationError): normalize_l2(np.zeros(768, dtype=np.float32))
        vector[0] = np.inf
        with self.assertRaises(F4ValidationError): normalize_l2(vector)

    def test_exhaustive_rank_k_and_deterministic_tie(self):
        query = np.zeros(768, dtype=np.float32); query[0] = 1
        ranked = exhaustive_rank(self.matrix, self.ids, query, 20)
        self.assertEqual(len(ranked), 9)
        self.assertEqual(ranked[0][0], self.ids[0])
        self.assertEqual([candidate_id for candidate_id, score in ranked[1:]], sorted(self.ids[1:]))
        for invalid in (0, -1, True):
            with self.assertRaises(F4ValidationError): exhaustive_rank(self.matrix, self.ids, query, invalid)

    def test_result_is_recomputed_without_ground_truth(self):
        query = np.zeros(768, dtype=np.float32); query[0] = 1
        ranked = exhaustive_rank(self.matrix, self.ids, query, 20)
        result = build_retrieval_result(
            query_id="fixture", text="description only", language="en",
            embedding_dataset_id=self.document["embedding_dataset_id"],
            checkpoint_sha256=self.document["checkpoint"]["sha256"], ranked=ranked,
            catalog=self.catalog, gallery_count=len(self.ids), requested_k=20,
            timings_ms={"text_encoding": 1.0, "ranking": 1.0, "total": 2.0},
        )
        self.assertNotIn("ground_truth", result)
        self.assertEqual(result["effective_k"], 9)
        validate_retrieval_result(
            result, self.catalog, embedding_manifest=self.document,
            candidate_ids=self.ids, matrix=self.matrix, text_embedding=query,
        )
        invalid = copy.deepcopy(result); invalid["results"][0]["score"] -= 0.1
        with self.assertRaises(F4ValidationError):
            validate_retrieval_result(
                invalid, self.catalog, embedding_manifest=self.document,
                candidate_ids=self.ids, matrix=self.matrix, text_embedding=query,
            )

    def test_full_gallery_ranking_scores_all_253_candidates(self):
        ids = tuple(candidate.candidate_id for candidate in self.catalog.candidates)
        matrix = np.zeros((253, 768), dtype="<f4")
        for index in range(253):
            matrix[index, index % 768] = 1.0
        query = np.zeros(768, dtype=np.float32); query[252] = 1.0
        ranked = exhaustive_rank(matrix, ids, query, 300)
        self.assertEqual(len(ranked), 253)
        self.assertEqual(ranked[0][0], ids[252])
        result = build_retrieval_result(
            query_id="full", text="description only", language="en",
            embedding_dataset_id=self.document["embedding_dataset_id"],
            checkpoint_sha256=self.document["checkpoint"]["sha256"], ranked=ranked,
            catalog=self.catalog, gallery_count=253, requested_k=300,
            timings_ms={"text_encoding": 1.0, "ranking": 1.0, "total": 2.0},
        )
        self.assertEqual(result["gallery_count"], 253)
        self.assertEqual(result["effective_k"], 253)

    def test_25m_gallery_ranking_scores_all_1115_candidates(self):
        ids = tuple(f"candidate-{index:04d}" for index in range(1115))
        matrix = np.zeros((1115, 768), dtype="<f4")
        matrix[:, 0] = 1.0
        query = np.zeros(768, dtype=np.float32); query[0] = 1.0
        ranked = exhaustive_rank(matrix, ids, query, 2000)
        self.assertEqual(len(ranked), 1115)
        self.assertEqual([candidate_id for candidate_id, _ in ranked], sorted(ids))


if __name__ == "__main__":
    unittest.main()
