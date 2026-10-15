import copy
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import jsonschema

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_contracts import (
    F4_EMBEDDING_DIMENSION,
    F4_EXPERIMENTAL_PROFILE_ID,
    experimental_visual_profile,
)
from src.tfg_phase0.f4_validation import (
    F4ValidationError,
    embedding_dataset_id,
    load_verified_f1_50m,
    validate_embedding_manifest,
    validate_retrieval_result,
    validate_visual_manifest,
    verify_visual_image_files,
    visual_dataset_id,
)
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
ZERO_HASH = "0" * 64
ONE_HASH = "1" * 64


def png_rgb(width=512, height=512):
    def chunk(kind, payload):
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    pixels = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


class Phase4ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            name: json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
            for name in ("f4_visual_manifest", "f4_embedding_manifest", "f4_retrieval_result")
        }
        cls.config = load_region_config(ROOT / "config" / "madrid.yaml")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.f1_path = self.root / "manifest-50m.json"
        write_manifest(build_catalog(self.config, spacing_m=50), self.f1_path)
        self.f1_before = self.f1_path.read_bytes()
        self.catalog = load_verified_f1_50m(self.f1_path, self.config)
        self.candidate = self.catalog.candidates[0]
        self.visual = self._visual_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def _visual_manifest(self):
        candidate = self.candidate
        document = {
            "schema_version": "1.0",
            "visual_dataset_id": "f4-madrid-visual-sha256-" + ZERO_HASH,
            "contract_version": "f4-visual-dataset-v1",
            "generator_version": "phase4-visual-dataset-v1",
            "catalog": {
                "manifest_id": self.catalog.manifest_id,
                "manifest_sha256": self.catalog.sha256,
                "region_id": self.catalog.region_id,
                "catalog_version": self.catalog.catalog_version,
                "spacing_m": self.catalog.spacing_m,
                "cell_size_m": self.catalog.cell_size_m,
                "grid_hash": self.catalog.grid_hash,
            },
            "profile": experimental_visual_profile(),
            "source": {
                "source_id": "synthetic-source-v1",
                "source_type": "synthetic_fixture",
                "data_sha256": ZERO_HASH,
                "license": "fixture-only",
                "attribution": "Synthetic test fixture",
            },
            "renderer": {"name": "fixture-renderer", "version": "1.0", "configuration_sha256": ONE_HASH},
            "style": {"style_id": "fixture-style", "version": "1.0", "sha256": ZERO_HASH, "license": "fixture-only"},
            "images": [{
                "candidate_id": candidate.candidate_id,
                "latitude": candidate.latitude,
                "longitude": candidate.longitude,
                "generation_status": "generated",
                "image_path": "images/candidate-001.png",
                "image_sha256": ZERO_HASH,
                "width_px": 512,
                "height_px": 512,
                "color_mode": "RGB",
                "format": "PNG",
                "requested_bbox": {"crs": "EPSG:3857", "min_x": 0.0, "min_y": 0.0, "max_x": 67.2512, "max_y": 67.2512},
                "rendered_bbox": {"crs": "EPSG:3857", "min_x": -10.0, "min_y": -10.0, "max_x": 100.0, "max_y": 100.0},
                "meters_per_pixel_x": 0.21484375,
                "meters_per_pixel_y": 0.21484375,
                "transformations": {
                    "source_width_px": 512, "source_height_px": 512,
                    "crop_left_px": 128, "crop_top_px": 128,
                    "crop_width_px": 256, "crop_height_px": 256,
                    "output_width_px": 512, "output_height_px": 512,
                    "resize_interpolation": "bicubic",
                },
                "error_code": None,
            }],
        }
        document["visual_dataset_id"] = visual_dataset_id(document)
        return document

    def _embedding_manifest(self):
        document = {
            "schema_version": "1.0",
            "embedding_dataset_id": "f4-madrid-embeddings-sha256-" + ZERO_HASH,
            "contract_version": "f4-image-embeddings-v1",
            "visual_dataset": {"visual_dataset_id": self.visual["visual_dataset_id"], "manifest_sha256": ONE_HASH},
            "model": {
                "name": "CLIP-L/14@336", "architecture": "ViT-L/14@336px",
                "cvg_text_commit": "6910d2747a94fbe985309bde60cd4732bcbbf50f",
                "openai_clip_commit": "dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1",
                "text_context_length": 300,
            },
            "checkpoint": {"filename": "checkpoint.pth", "sha256": ZERO_HASH, "selection_status": "provisional_d013"},
            "preprocessing": {"policy": "official_clip_preprocess", "input_width_px": 336, "input_height_px": 336},
            "embedding": {
                "matrix_path": "embeddings/image_embeddings.npy", "matrix_sha256": ZERO_HASH,
                "candidate_ids_path": "embeddings/candidate_ids.jsonl", "candidate_ids_sha256": ONE_HASH,
                "count": 1, "dimension": 768, "dtype": "float32", "normalization": "l2",
                "row_order": "candidate_ids_file_order",
            },
        }
        document["embedding_dataset_id"] = embedding_dataset_id(document)
        return document

    def _retrieval_result(self):
        return {
            "schema_version": "1.0",
            "contract_version": "f4-exhaustive-retrieval-v1",
            "query": {"query_id": "query-fixture", "text": "A square near a street", "language": "en"},
            "embedding_dataset_id": "f4-madrid-embeddings-sha256-" + ZERO_HASH,
            "ranking_method": "exhaustive_cosine",
            "requested_k": 5,
            "results": [{
                "rank": 1, "candidate_id": self.candidate.candidate_id,
                "latitude": self.candidate.latitude, "longitude": self.candidate.longitude,
                "score": 0.25,
            }],
            "timings_ms": {"text_encoding": 10.0, "ranking": 0.1, "total": 10.2},
        }

    def test_schemas_are_valid_and_accept_synthetic_contracts(self):
        documents = (self.visual, self._embedding_manifest(), self._retrieval_result())
        for name, document in zip(self.schemas, documents):
            schema = self.schemas[name]
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(document, schema)
            validate_document(document, name)

    def test_experimental_profile_is_fixed_and_returns_independent_copies(self):
        first = experimental_visual_profile()
        second = experimental_visual_profile()
        self.assertEqual(first["profile_id"], F4_EXPERIMENTAL_PROFILE_ID)
        self.assertEqual(first["compatibility_status"], "experimental_unconfirmed")
        first["output"]["width_px"] = 1
        self.assertEqual(second["output"]["width_px"], 512)

    def test_loads_only_verified_50m_f1_without_modifying_it(self):
        self.assertEqual(self.catalog.spacing_m, 50)
        self.assertEqual(self.catalog.cell_size_m, 50)
        self.assertEqual(len(self.catalog.candidates), 253)
        self.assertEqual(self.f1_path.read_bytes(), self.f1_before)
        f1_25m = self.root / "manifest-25m.json"
        write_manifest(build_catalog(self.config, spacing_m=25), f1_25m)
        with self.assertRaises(F4ValidationError):
            load_verified_f1_50m(f1_25m, self.config)

    def test_visual_identity_is_deterministic_and_effective(self):
        first = visual_dataset_id(self.visual)
        reordered = json.loads(json.dumps(self.visual, sort_keys=False))
        self.assertEqual(first, visual_dataset_id(reordered))
        changed = copy.deepcopy(self.visual)
        changed["style"]["sha256"] = ONE_HASH
        self.assertNotEqual(first, visual_dataset_id(changed))
        changed["images"][0]["latitude"] = math.nan
        with self.assertRaises(F4ValidationError):
            visual_dataset_id(changed)

    def test_visual_manifest_rejects_bad_paths_duplicates_and_coordinates(self):
        invalid = copy.deepcopy(self.visual)
        invalid["images"][0]["image_path"] = "/tmp/image.png"
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(invalid, self.catalog)

        invalid = copy.deepcopy(self.visual)
        invalid["images"].append(copy.deepcopy(invalid["images"][0]))
        invalid["visual_dataset_id"] = visual_dataset_id(invalid)
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(invalid, self.catalog)

        for value in (math.nan, math.inf):
            invalid = copy.deepcopy(self.visual)
            invalid["images"][0]["latitude"] = value
            with self.subTest(value=value), self.assertRaises(F4ValidationError):
                validate_visual_manifest(invalid, self.catalog)

        invalid = copy.deepcopy(self.visual)
        invalid["images"][0]["longitude"] += 0.0001
        invalid["visual_dataset_id"] = visual_dataset_id(invalid)
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(invalid, self.catalog)

    def test_visual_manifest_rejects_identity_and_catalog_mismatches(self):
        validate_visual_manifest(self.visual, self.catalog)
        invalid = copy.deepcopy(self.visual)
        invalid["visual_dataset_id"] = "f4-madrid-visual-sha256-" + ONE_HASH
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(invalid, self.catalog)
        invalid = copy.deepcopy(self.visual)
        invalid["catalog"]["manifest_sha256"] = ZERO_HASH
        invalid["visual_dataset_id"] = visual_dataset_id(invalid)
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(invalid, self.catalog)

    def test_generation_status_has_coherent_metadata(self):
        failed = copy.deepcopy(self.visual)
        image = failed["images"][0]
        image.update({field: None for field in (
            "image_path", "image_sha256", "width_px", "height_px", "color_mode", "format",
            "rendered_bbox", "meters_per_pixel_x", "meters_per_pixel_y", "transformations",
        )})
        image["generation_status"] = "insufficient_source"
        image["error_code"] = "source_does_not_cover_requested_bbox"
        failed["visual_dataset_id"] = visual_dataset_id(failed)
        validate_visual_manifest(failed, self.catalog)

        invalid = copy.deepcopy(failed)
        invalid["images"][0]["image_path"] = "images/partial.png"
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(invalid, self.catalog)

    def test_verifies_synthetic_png_hash_dimensions_and_color_type(self):
        image_dir = self.root / "images"
        image_dir.mkdir()
        raw = png_rgb()
        path = image_dir / "candidate-001.png"
        path.write_bytes(raw)
        self.visual["images"][0]["image_sha256"] = __import__("hashlib").sha256(raw).hexdigest()
        self.visual["visual_dataset_id"] = visual_dataset_id(self.visual)
        validate_visual_manifest(self.visual, self.catalog)
        verify_visual_image_files(self.visual, self.root)
        path.write_bytes(raw + b"changed")
        with self.assertRaises(F4ValidationError):
            verify_visual_image_files(self.visual, self.root)

    def test_embedding_contract_is_768_and_references_generated_images(self):
        embedding = self._embedding_manifest()
        self.assertEqual(embedding["embedding"]["dimension"], F4_EMBEDDING_DIMENSION)
        validate_embedding_manifest(embedding, self.visual)
        invalid = copy.deepcopy(embedding)
        invalid["embedding"]["dimension"] = 512
        with self.assertRaises(F4ValidationError):
            validate_embedding_manifest(invalid, self.visual)
        invalid = copy.deepcopy(embedding)
        invalid["embedding"]["matrix_path"] = "../outside.npy"
        with self.assertRaises(F4ValidationError):
            validate_embedding_manifest(invalid, self.visual)
        invalid = copy.deepcopy(embedding)
        invalid["embedding"]["matrix_sha256"] = ONE_HASH
        with self.assertRaises(F4ValidationError):
            validate_embedding_manifest(invalid, self.visual)

    def test_top_k_contract_has_no_ground_truth_and_matches_f1(self):
        result = self._retrieval_result()
        validate_retrieval_result(result, self.catalog)
        self.assertNotIn("ground_truth", result)
        invalid = copy.deepcopy(result)
        invalid["ground_truth"] = {"latitude": 0, "longitude": 0}
        with self.assertRaises(F4ValidationError):
            validate_retrieval_result(invalid, self.catalog)
        invalid = copy.deepcopy(result)
        invalid["results"][0]["score"] = math.nan
        with self.assertRaises(F4ValidationError):
            validate_retrieval_result(invalid, self.catalog)


if __name__ == "__main__":
    unittest.main()
