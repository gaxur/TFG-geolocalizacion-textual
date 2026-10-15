import copy
import hashlib
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
from src.tfg_phase0.f4_contracts import F4_EMBEDDING_DIMENSION, F4_EXPERIMENTAL_PROFILE_ID, experimental_visual_profile
from src.tfg_phase0.f4_geometry import BBox3857, bbox_contains, bbox_wgs84_to_epsg3857, epsg3857_to_wgs84
from src.tfg_phase0.f4_preflight import load_verified_selection
from src.tfg_phase0.f4_validation import (
    F4ValidationError, embedding_dataset_id, geometry_document, load_verified_f1_50m,
    validate_embedding_manifest, validate_retrieval_result, validate_visual_bundle,
    validate_render_extract_provenance, validate_visual_manifest, visual_dataset_id,
)
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
ZERO_HASH = "0" * 64
ONE_HASH = "1" * 64


def png_rgb(width=512, height=512):
    def chunk(kind, payload):
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    rows = []
    for row in range(height):
        pixels = bytearray(b"\x00\x00\x00" * width)
        if row == 0:
            pixels[:3] = b"\xff\xff\xff"
        rows.append(b"\x00" + bytes(pixels))
    pixels = b"".join(rows)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


class Phase4ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            name: json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
            for name in (
                "f4_visual_manifest", "f4_embedding_manifest", "f4_retrieval_result",
                "f4_visual_selection", "f4_osm_source", "f4_renderer_provenance",
            )
        }
        cls.config = load_region_config(ROOT / "config/madrid.yaml")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.f1_path = self.root / "manifest-50m.json"
        write_manifest(build_catalog(self.config, spacing_m=50), self.f1_path)
        self.f1_before = self.f1_path.read_bytes()
        self.catalog = load_verified_f1_50m(self.f1_path, self.config)
        self.candidate = self.catalog.candidates[0]
        self.selection, self.selection_hash = load_verified_selection(ROOT / "config/madrid_f4_visual_fixture.json", self.catalog)
        self.visual = self._visual_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def _visual_manifest(self):
        source_bbox = bbox_wgs84_to_epsg3857(self.config["region"]["bbox"])
        candidates = {candidate.candidate_id: candidate for candidate in self.catalog.candidates}
        images = []
        for selected in self.selection["candidates"]:
            candidate = candidates[selected["candidate_id"]]
            geometry = geometry_document(candidate.latitude, candidate.longitude)
            covered = bbox_contains(
                source_bbox,
                BBox3857(**{field: geometry["output_bbox"][field] for field in ("min_x", "min_y", "max_x", "max_y")}),
            )
            images.append({
                "candidate_id": candidate.candidate_id,
                "latitude": candidate.latitude,
                "longitude": candidate.longitude,
                "generation_status": "generated" if covered else "insufficient_source",
                "geometry": geometry,
                "image_path": f"images/{candidate.candidate_id}.png" if covered else None,
                "image_sha256": ZERO_HASH if covered else None,
                "width_px": 512 if covered else None,
                "height_px": 512 if covered else None,
                "color_mode": "RGB" if covered else None,
                "format": "PNG" if covered else None,
                "error_code": None if covered else "source_does_not_cover_output_bbox",
            })
        document = {
            "schema_version": "2.0", "visual_dataset_id": "f4-madrid-visual-sha256-" + ZERO_HASH,
            "contract_version": "f4-visual-dataset-v2", "generator_version": "phase4-visual-dataset-v2",
            "catalog": {
                "manifest_id": self.catalog.manifest_id, "manifest_sha256": self.catalog.sha256,
                "region_id": self.catalog.region_id, "catalog_version": self.catalog.catalog_version,
                "spacing_m": 50, "cell_size_m": 50, "grid_hash": self.catalog.grid_hash,
            },
            "selection": {"selection_id": "f4-nine-candidates-v1", "logical_path": "config/madrid_f4_visual_fixture.json", "sha256": self.selection_hash},
            "profile": experimental_visual_profile(),
            "source": {
                "contract_version": "f4-osm-source-v1", "source_id": "synthetic-source-v1", "source_type": "synthetic_fixture",
                "data_path": "fixtures/source.osm", "data_sha256": ZERO_HASH,
                "provenance_path": "fixtures/provenance.json", "provenance_sha256": ONE_HASH,
                "coverage_bbox_wgs84": dict(self.config["region"]["bbox"]), "coverage_bbox_epsg3857": source_bbox.as_document(),
                "selection": {"nodes": "bbox", "ways": "bbox_intersection", "relations": "fixture"},
                "closure": {"ways": "all_referenced_nodes", "relations": "not_expanded"},
                "license": "fixture-only", "attribution": "Synthetic test fixture",
            },
            "renderer": {
                "contract_version": "f4-renderer-provenance-v1", "renderer_id": "fixture-renderer-v1",
                "name": "fixture-renderer", "version": "1.0", "configuration_path": "renderer/config.json",
                "configuration_sha256": ONE_HASH, "container_image_digest": None, "license": "fixture-only",
            },
            "style": {
                "style_id": "fixture-style", "version": "1.0", "repository_commit": "1" * 40,
                "compiled_style_path": "style/style.xml", "compiled_style_sha256": ZERO_HASH,
                "assets_manifest_path": "style/assets.json", "assets_manifest_sha256": ONE_HASH,
                "fonts_manifest_path": "style/fonts.json", "fonts_manifest_sha256": ZERO_HASH, "license": "fixture-only",
            },
            "images": images,
        }
        document["visual_dataset_id"] = visual_dataset_id(document)
        return document

    def _embedding_manifest(self):
        document = {
            "schema_version": "2.0", "embedding_dataset_id": "f4-madrid-embeddings-sha256-" + ZERO_HASH,
            "contract_version": "f4-image-embeddings-v2", "generator_version": "phase4-crosstext2loc-embeddings-v1", "generator_source_sha256": ZERO_HASH,
            "visual_dataset": {"visual_dataset_id": self.visual["visual_dataset_id"], "manifest_sha256": ONE_HASH},
            "model": {"name": "CLIP-L/14@336", "architecture": "ViT-L/14@336px", "cvg_text_commit": "6910d2747a94fbe985309bde60cd4732bcbbf50f", "cvg_utils_sha256": ZERO_HASH, "openai_clip_commit": "dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1", "openai_clip_weights_filename": "ViT-L-14-336px.pt", "openai_clip_weights_sha256": "3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02", "text_context_length": 300},
            "checkpoint": {"filename": "long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth", "size_bytes": 1712649548, "sha256": "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d", "selection_status": "provisional_d013"},
            "preprocessing": {"policy": "official_openai_clip_preprocess", "input_width_px": 336, "input_height_px": 336, "image_color_mode": "RGB", "text_tokenizer": "clip.tokenize_context_300", "text_truncation": True},
            "environment": {"container_image_id": "sha256:" + "2" * 64, "python_version": "3.12.3", "torch_version": "test", "torchvision_version": "test", "cuda_version": "test", "device_type": "cuda", "inference_dtype": "float32"},
            "embedding": {"matrix_path": "embeddings/image_embeddings.npy", "matrix_sha256": ZERO_HASH, "candidate_ids_path": "embeddings/candidate_ids.jsonl", "candidate_ids_sha256": ONE_HASH, "candidate_ids_format": "jsonl_object_candidate_id_v1", "count": 9, "dimension": 768, "dtype": "float32", "byte_order": "little", "normalization": "l2", "row_order": "visual_manifest_order"},
        }
        document["embedding_dataset_id"] = embedding_dataset_id(document)
        return document

    def _retrieval_result(self):
        return {
            "schema_version": "2.0", "contract_version": "f4-exhaustive-retrieval-v2",
            "query": {"query_id": "query-fixture", "text": "A square near a street", "language": "en"},
            "embedding_dataset_id": "f4-madrid-embeddings-sha256-" + ZERO_HASH, "checkpoint_sha256": "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d", "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "gallery_count": 9, "requested_k": 5, "effective_k": 1,
            "results": [{"rank": 1, "candidate_id": self.candidate.candidate_id, "latitude": self.candidate.latitude, "longitude": self.candidate.longitude, "score": 0.25}],
            "timings_ms": {"text_encoding": 10.0, "ranking": 0.1, "total": 10.2},
        }

    def test_schemas_accept_realistic_synthetic_contracts(self):
        retrieval = self._retrieval_result()
        retrieval["requested_k"] = 1
        documents = (
            self.visual, self._embedding_manifest(), retrieval, self.selection,
            self.visual["source"], {"renderer": self.visual["renderer"], "style": self.visual["style"]},
        )
        for name, document in zip(self.schemas, documents):
            jsonschema.Draft202012Validator.check_schema(self.schemas[name])
            jsonschema.validate(document, self.schemas[name])
            validate_document(document, name)

    def test_assets_manifest_contract_rejects_duplicate_paths(self):
        assets = {
            "schema_version": "1.0", "manifest_id": "assets-fixture", "kind": "renderer_assets",
            "files": [{"logical_path": "symbols/a.svg", "sha256": ZERO_HASH, "size_bytes": 1, "source": "fixture", "license": "CC0-1.0"}],
        }
        schema = json.loads((SCHEMAS / "f4_assets_manifest.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(assets, schema)
        validate_document(assets, "f4_assets_manifest")
        assets["files"].append(copy.deepcopy(assets["files"][0]))
        with self.assertRaises(SchemaValidationError):
            validate_document(assets, "f4_assets_manifest")

    def test_profile_is_v2_unconfirmed_and_immutable_by_copy(self):
        first, second = experimental_visual_profile(), experimental_visual_profile()
        self.assertEqual(first["profile_id"], F4_EXPERIMENTAL_PROFILE_ID)
        self.assertEqual(first["compatibility_status"], "experimental_unconfirmed")
        first["zoom"] = 1
        self.assertEqual(second["zoom"], 18)

    def test_verified_f1_is_50m_and_unmodified(self):
        self.assertEqual((self.catalog.spacing_m, self.catalog.cell_size_m, len(self.catalog.candidates)), (50, 50, 253))
        self.assertEqual(self.f1_path.read_bytes(), self.f1_before)
        f1_25m = self.root / "manifest-25m.json"
        write_manifest(build_catalog(self.config, spacing_m=25), f1_25m)
        with self.assertRaises(F4ValidationError):
            load_verified_f1_50m(f1_25m, self.config)

    def test_visual_manifest_validates_geometry_and_identity(self):
        validate_visual_manifest(self.visual, self.catalog, selection=self.selection, selection_sha256=self.selection_hash)
        for field in ("center_x", "global_pixel_y", "crop_left_px", "native_meters_per_pixel"):
            invalid = copy.deepcopy(self.visual)
            invalid["images"][0]["geometry"][field] += 0.01
            invalid["visual_dataset_id"] = visual_dataset_id(invalid)
            with self.subTest(field=field), self.assertRaises(F4ValidationError):
                validate_visual_manifest(invalid, self.catalog, selection=self.selection, selection_sha256=self.selection_hash)

    def test_rejects_duplicate_ids_and_image_paths(self):
        self.visual["images"][1]["image_path"] = self.visual["images"][0]["image_path"]
        self.visual["visual_dataset_id"] = visual_dataset_id(self.visual)
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(self.visual, self.catalog, selection=self.selection, selection_sha256=self.selection_hash)

    def test_manifest_rejects_omitting_a_selected_candidate(self):
        self.visual["images"].pop()
        self.visual["visual_dataset_id"] = visual_dataset_id(self.visual)
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(self.visual, self.catalog, selection=self.selection, selection_sha256=self.selection_hash)

    def test_manifest_rejects_a_substituted_nine_candidate_selection(self):
        substituted = copy.deepcopy(self.selection)
        substituted["candidates"][0], substituted["candidates"][1] = substituted["candidates"][1], substituted["candidates"][0]
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(
                self.visual,
                self.catalog,
                selection=substituted,
                selection_sha256=self.selection_hash,
            )

    def test_insufficient_coverage_must_be_explicit(self):
        east_probe = self.visual["images"][2]
        self.assertEqual(east_probe["generation_status"], "insufficient_source")
        east_probe.update(generation_status="generated", image_path=f"images/{east_probe['candidate_id']}.png", image_sha256=ZERO_HASH, width_px=512, height_px=512, color_mode="RGB", format="PNG", error_code=None)
        self.visual["visual_dataset_id"] = visual_dataset_id(self.visual)
        with self.assertRaises(F4ValidationError):
            validate_visual_manifest(self.visual, self.catalog, selection=self.selection, selection_sha256=self.selection_hash)

    def test_complete_bundle_verifies_png_and_rejects_corruption(self):
        (self.root / "config").mkdir()
        selection_raw = (ROOT / "config/madrid_f4_visual_fixture.json").read_bytes()
        (self.root / "config/madrid_f4_visual_fixture.json").write_bytes(selection_raw)
        (self.root / "fixtures").mkdir()
        source_raw = b"synthetic source"
        provenance_raw = b"{}"
        (self.root / "fixtures/source.osm").write_bytes(source_raw)
        (self.root / "fixtures/provenance.json").write_bytes(provenance_raw)
        self.visual["source"]["data_sha256"] = hashlib.sha256(source_raw).hexdigest()
        self.visual["source"]["provenance_sha256"] = hashlib.sha256(provenance_raw).hexdigest()
        (self.root / "renderer").mkdir()
        effective_raw = b"effective renderer input"
        (self.root / "renderer/effective.py").write_bytes(effective_raw)
        renderer_config_document = {
            "schema_version": "1.0",
            "container_image_digest": None,
            "files": [{
                "logical_path": "renderer/effective.py",
                "sha256": hashlib.sha256(effective_raw).hexdigest(),
                "size_bytes": len(effective_raw),
                "source": "fixture",
                "license": "fixture-only",
            }],
        }
        renderer_config = json.dumps(renderer_config_document, sort_keys=True).encode()
        (self.root / "renderer/config.json").write_bytes(renderer_config)
        self.visual["renderer"]["configuration_sha256"] = hashlib.sha256(renderer_config).hexdigest()
        (self.root / "style/symbols").mkdir(parents=True)
        (self.root / "style/fonts").mkdir()
        style_raw = b"style fixture"
        asset_raw = b"asset fixture"
        font_raw = b"font fixture"
        (self.root / "style/style.xml").write_bytes(style_raw)
        (self.root / "style/symbols/a.svg").write_bytes(asset_raw)
        (self.root / "style/fonts/a.ttf").write_bytes(font_raw)
        assets = {"schema_version": "1.0", "manifest_id": "assets", "kind": "renderer_assets", "files": [{"logical_path": "style/symbols/a.svg", "sha256": hashlib.sha256(asset_raw).hexdigest(), "size_bytes": len(asset_raw), "source": "fixture", "license": "fixture-only"}]}
        fonts = {"schema_version": "1.0", "manifest_id": "fonts", "kind": "fonts", "files": [{"logical_path": "style/fonts/a.ttf", "sha256": hashlib.sha256(font_raw).hexdigest(), "size_bytes": len(font_raw), "source": "fixture", "license": "fixture-only"}]}
        assets_raw = json.dumps(assets, sort_keys=True).encode()
        fonts_raw = json.dumps(fonts, sort_keys=True).encode()
        (self.root / "style/assets.json").write_bytes(assets_raw)
        (self.root / "style/fonts.json").write_bytes(fonts_raw)
        self.visual["style"].update(
            compiled_style_sha256=hashlib.sha256(style_raw).hexdigest(),
            assets_manifest_sha256=hashlib.sha256(assets_raw).hexdigest(),
            fonts_manifest_sha256=hashlib.sha256(fonts_raw).hexdigest(),
        )
        image_dir = self.root / "images"
        image_dir.mkdir()
        raw = png_rgb()
        candidates = {candidate.candidate_id: candidate for candidate in self.catalog.candidates}
        source_bbox = self.visual["source"]["coverage_bbox_epsg3857"]
        _, expanded_east = epsg3857_to_wgs84(source_bbox["max_x"] + 100, 0)
        self.visual["source"]["coverage_bbox_wgs84"]["east"] = expanded_east
        self.visual["source"]["coverage_bbox_epsg3857"] = bbox_wgs84_to_epsg3857(self.visual["source"]["coverage_bbox_wgs84"]).as_document()
        images = []
        for selected in self.selection["candidates"]:
            candidate = candidates[selected["candidate_id"]]
            path = image_dir / f"{candidate.candidate_id}.png"
            path.write_bytes(raw)
            images.append({
                "candidate_id": candidate.candidate_id, "latitude": candidate.latitude, "longitude": candidate.longitude,
                "generation_status": "generated", "geometry": geometry_document(candidate.latitude, candidate.longitude),
                "image_path": f"images/{candidate.candidate_id}.png", "image_sha256": hashlib.sha256(raw).hexdigest(),
                "width_px": 512, "height_px": 512, "color_mode": "RGB", "format": "PNG", "error_code": None,
            })
        self.visual["images"] = images
        self.visual["visual_dataset_id"] = visual_dataset_id(self.visual)
        validate_visual_bundle(self.visual, self.catalog, selection=self.selection, selection_sha256=self.selection_hash, dataset_root=self.root, project_root=self.root)
        path = image_dir / f"{self.candidate.candidate_id}.png"
        corrupt = bytearray(raw)
        corrupt[-5] ^= 1
        path.write_bytes(corrupt)
        self.visual["images"][0]["image_sha256"] = hashlib.sha256(corrupt).hexdigest()
        self.visual["visual_dataset_id"] = visual_dataset_id(self.visual)
        with self.assertRaises(F4ValidationError):
            validate_visual_bundle(self.visual, self.catalog, selection=self.selection, selection_sha256=self.selection_hash, dataset_root=self.root, project_root=self.root)

    def test_render_extract_provenance_is_verified(self):
        source_raw = b"pbf fixture"
        provenance = {
            "acquired_at_utc": "2026-10-15T08:35:22Z",
            "attribution": self.visual["source"]["attribution"],
            "bbox": self.visual["source"]["coverage_bbox_wgs84"],
            "closure": self.visual["source"]["closure"],
            "data_timestamp_utc": "2026-10-14T20:21:12Z",
            "http": {"etag": "fixture", "last_modified": "2026-10-15T02:08:42Z"},
            "license": self.visual["source"]["license"],
            "raw_format": "osmpbf",
            "raw_sha256": hashlib.sha256(source_raw).hexdigest(),
            "raw_size_bytes": len(source_raw),
            "resolved_filename": "fixture.osm.pbf",
            "selection": self.visual["source"]["selection"],
            "source_id": "f4-source-fixture",
            "source_url": "https://example.test/fixture.osm.pbf",
        }
        source = copy.deepcopy(self.visual["source"])
        source.update(
            source_id=provenance["source_id"],
            source_type="osm_render_extract",
            data_sha256=provenance["raw_sha256"],
        )
        validate_render_extract_provenance(provenance, source_raw, source)
        provenance["raw_size_bytes"] += 1
        with self.assertRaises(F4ValidationError):
            validate_render_extract_provenance(provenance, source_raw, source)

    def test_embedding_and_top_k_contracts_remain_separate(self):
        embedding = self._embedding_manifest()
        self.assertEqual(embedding["embedding"]["dimension"], F4_EMBEDDING_DIMENSION)
        validate_embedding_manifest(embedding)
        result = self._retrieval_result()
        result["requested_k"] = 1
        validate_retrieval_result(result, self.catalog)
        self.assertNotIn("ground_truth", result)
        invalid = copy.deepcopy(result)
        invalid["ground_truth"] = {}
        with self.assertRaises(F4ValidationError):
            validate_retrieval_result(invalid, self.catalog)


if __name__ == "__main__":
    unittest.main()
