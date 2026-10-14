import copy
import json
import math
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shapely import Point

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f3_associations import (
    CandidateAssociationInventory,
    CandidateOSMAssociation,
    associate_candidates_with_osm,
)
from src.tfg_phase0.f3_bundle import (
    F3BundleConflictError,
    F3PublicationUnsupportedError,
    publish_f3_bundle,
)
from src.tfg_phase0.f3_contracts import F3_BUNDLE_FILES
from src.tfg_phase0.f3_geometry import (
    GEOMETRY_POLICY,
    MetricBBox,
    NormalizedGeometryInventory,
    NormalizedOSMObject,
    normalize_osm_geometries,
)
from src.tfg_phase0.f3_identity import (
    build_f3_identity,
    f3_dataset_id,
    generator_source_manifest,
    identity_from_provenance,
    sha256_bytes,
)
from src.tfg_phase0.f3_inputs import (
    CandidateInput,
    CatalogInput,
    D049RulesInput,
    OSMInventory,
    OSMMemberInput,
    OSMNodeInput,
    OSMRelationInput,
    SnapshotInput,
    VerifiedF3Inputs,
    f3_config_input,
    load_d049_rules,
    load_verified_f3_inputs,
)
from src.tfg_phase0.f3_relations import build_relation_context
from src.tfg_phase0.f3_serialization import (
    F3SerializationError,
    build_f3_bundle_bytes,
    canonical_json_bytes,
    checksum_bytes,
    normalize_metric,
    serialize_jsonl,
)
from src.tfg_phase0.f3_validation import F3BundleValidationError, validate_f3_bundle
from src.tfg_phase0.osm_snapshot import (
    build_overpass_query,
    build_snapshot_provenance,
    publish_snapshot,
    validate_osm_xml,
)
from src.tfg_phase0.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "third_party/osm-polygon-features/v0.9.2/polygon-features.json"


def fixture_inputs():
    catalog_path = ROOT / "tests/fixtures/f3/osm_objects.json"
    source_path = ROOT / "tests/fixtures/f3/inputs/source.osm"
    provenance_path = ROOT / "tests/fixtures/f3/provenance.json"
    config_path = ROOT / "config/madrid.yaml"
    candidate = CandidateInput("candidate-001", 40.4168, -3.7038, 440000.0, 4474000.0, 0, 0, ())
    catalog_raw = catalog_path.read_bytes()
    source_raw = source_path.read_bytes()
    config_raw = config_path.read_bytes()
    config = json.loads(config_raw)
    node = OSMNodeInput(1, 40.4168, -3.7038, (("name", "Águila"),), "node_bbox")
    relation = OSMRelationInput(20, (("type", "collection"),), (OSMMemberInput("node", 1, "stop", True),))
    catalog = CatalogInput(
        path=catalog_path, size_bytes=len(catalog_raw), sha256=sha256_bytes(catalog_raw),
        manifest_id="madrid-pilot-grid-v1-s25-l25", region_id="madrid_pilot",
        catalog_version="madrid-pilot-grid-v1", spacing_m=25, cell_size_m=25,
        source_crs="EPSG:4326", projected_crs="EPSG:25830", grid_hash="0123456789ab",
        region_bbox_wgs84=config["region"]["bbox"], provenance={}, candidates=(candidate,),
    )
    snapshot = SnapshotInput(
        directory=source_path.parent, source_path=source_path, provenance_path=provenance_path,
        osm_snapshot_id=f"osm-madrid-pilot-osmxml-sha256-{sha256_bytes(source_raw)}",
        raw_sha256=sha256_bytes(source_raw), raw_size_bytes=len(source_raw), raw=source_raw,
        provenance={
            "schema_version": "1.0", "region_id": "madrid_pilot",
            "selection": {"nodes": "bbox", "ways": "bbox_intersection", "relations": "direct_parent_of_local_node_or_way"},
            "closure": {"ways": "all_referenced_nodes", "relations": "not_expanded"},
        },
    )
    rules = load_d049_rules(RULES)
    inputs = VerifiedF3Inputs(
        catalog=catalog, snapshot=snapshot,
        inventory=OSMInventory((node,), (), (relation,)), rules=rules,
        config_sha256=sha256_bytes(config_raw), config_canonical_sha256="f" * 64,
        config_path=config_path,
        config_effective_sha256=sha256_bytes(canonical_json_bytes(f3_config_input(config))),
    )
    geometry = Point(440000.0, 4474000.0)
    normalized = NormalizedGeometryInventory((NormalizedOSMObject(
        osm_type="node", osm_id=1, osm_ref="node/1", tags=node.tags,
        source_role="node_bbox", geometry_role="point", geometry_status="valid",
        geometry_reason=None, classification_diagnostic=None, is_closed=None,
        metric_bbox=MetricBBox(*geometry.bounds), geometry=geometry,
    ),), (relation,), "2.1.2", "3.13.1", GEOMETRY_POLICY)
    associations = CandidateAssociationInventory((CandidateOSMAssociation(
        "candidate-001", "node", 1, "node/1", "point", True,
        False, True, False, False, False, False, 0.0,
    ),), 1, 1)
    relations = build_relation_context(inputs, normalized, associations)
    return inputs, normalized, associations, relations


def materialize(directory, outputs):
    directory.mkdir()
    for name, content in outputs.items():
        (directory / name).write_bytes(content)


class Phase3BundleTests(unittest.TestCase):
    def test_canonical_json_unicode_and_empty_jsonl(self):
        self.assertEqual(canonical_json_bytes({"á": 1, "a": 2}), b'{"a":2,"\xc3\xa1":1}')
        self.assertEqual(serialize_jsonl(()), b"")
        self.assertEqual(serialize_jsonl(({"b": 2, "a": 1},)), b'{"a":1,"b":2}\n')
        with self.assertRaises(F3SerializationError):
            canonical_json_bytes({"x": math.nan})

    def test_metric_rounding_half_even_and_negative_zero(self):
        self.assertEqual(normalize_metric(1.2345665), 1.234566)
        self.assertEqual(normalize_metric(1.2345675), 1.234568)
        self.assertEqual(normalize_metric(-0.0000001), 0.0)
        with self.assertRaises(F3SerializationError):
            normalize_metric(math.inf)

    def test_config_projection_excludes_unrelated_blocks(self):
        config = json.loads((ROOT / "config/madrid.yaml").read_text())
        changed = copy.deepcopy(config)
        changed["osm_acquisition"]["endpoint"] = "https://example.test"
        changed["artifacts"]["processed_osm"] = "elsewhere"
        self.assertEqual(f3_config_input(config), f3_config_input(changed))

    def test_source_manifest_is_closed_and_ordered(self):
        document = generator_source_manifest(ROOT)
        paths = [row["path"] for row in document["files"]]
        self.assertEqual(document["version"], "f3-generator-source-v1")
        self.assertEqual(paths, sorted(paths))
        self.assertIn("src/tfg_phase0/catalog.py", paths)
        self.assertIn("src/tfg_phase0/f3_validation.py", paths)
        self.assertNotIn("src/tfg_phase0/f3_bundle.py", paths)

    def test_identity_known_vector_and_platform_independence(self):
        inputs, _, _, _ = fixture_inputs()
        identity = build_f3_identity(
            inputs, generator_hash="1" * 64, transform_hash="2" * 64,
            python_version="3.12.3", numpy_version="2.5.4",
            shapely_version="2.1.2", geos_version="3.13.1",
        )
        self.assertEqual(
            f3_dataset_id(identity),
            "f3-madrid-pilot-associations-sha256-3ee4213e0a53703011324ce8d42da8ef5af1aeda1953a4e046fcd2fc6a9faf7c",
        )
        self.assertNotIn("platform_system", identity["software"])
        changed = copy.deepcopy(identity)
        changed["geometry"]["direct_node_policy"] = "other"
        self.assertNotEqual(f3_dataset_id(identity), f3_dataset_id(changed))
        for group, field in (
            ("catalog", "manifest_sha256"), ("osm", "raw_sha256"),
            ("rules", "sha256"), ("config", "canonical_sha256"),
            ("software", "numpy_version"),
        ):
            changed = copy.deepcopy(identity)
            changed[group][field] = "changed"
            self.assertNotEqual(f3_dataset_id(identity), f3_dataset_id(changed))

    def test_bundle_bytes_are_deterministic_and_provenance_is_valid(self):
        values = fixture_inputs()
        first = build_f3_bundle_bytes(*values, project_root=ROOT)
        second = build_f3_bundle_bytes(*values, project_root=ROOT)
        self.assertEqual(first, second)
        dataset_id, outputs, provenance = first
        self.assertEqual(set(outputs), set(F3_BUNDLE_FILES))
        self.assertEqual(dataset_id, f3_dataset_id(identity_from_provenance(provenance)))
        validate_document(provenance, "f3_provenance")
        self.assertTrue(outputs["provenance.json"].endswith(b"\n"))

    def test_integral_validation_and_corruption(self):
        values = fixture_inputs()
        dataset_id, outputs, provenance = build_f3_bundle_bytes(*values, project_root=ROOT)
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / dataset_id
            materialize(bundle, outputs)
            self.assertEqual(
                validate_f3_bundle(
                    bundle, inputs=values[0], normalized=values[1],
                    association_inventory=values[2], relation_inventory=values[3],
                    expected_identity=identity_from_provenance(provenance),
                ),
                provenance,
            )
            original = (bundle / "osm_objects.jsonl").read_bytes()
            (bundle / "osm_objects.jsonl").write_bytes(original + b" ")
            with self.assertRaises(F3BundleValidationError):
                validate_f3_bundle(
                    bundle, inputs=values[0], normalized=values[1],
                    association_inventory=values[2], relation_inventory=values[3],
                )

    def test_numeric_representation_must_match_canonical_bytes(self):
        values = fixture_inputs()
        dataset_id, outputs, _ = build_f3_bundle_bytes(*values, project_root=ROOT)
        outputs["candidate_osm_associations.jsonl"] = outputs[
            "candidate_osm_associations.jsonl"
        ].replace(b'"center_distance_m":0.0', b'"center_distance_m":0')
        outputs["sha256.txt"] = checksum_bytes(outputs)
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / dataset_id
            materialize(bundle, outputs)
            with self.assertRaises(F3BundleValidationError):
                validate_f3_bundle(
                    bundle, inputs=values[0], normalized=values[1],
                    association_inventory=values[2], relation_inventory=values[3],
                )

    def test_checksum_format_is_strict(self):
        values = fixture_inputs()
        dataset_id, outputs, _ = build_f3_bundle_bytes(*values, project_root=ROOT)
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / dataset_id
            materialize(bundle, outputs)
            checksum = (bundle / "sha256.txt").read_text()
            (bundle / "sha256.txt").write_text(checksum.replace("  ", " ", 1))
            with self.assertRaises(F3BundleValidationError):
                validate_f3_bundle(
                    bundle, inputs=values[0], normalized=values[1],
                    association_inventory=values[2], relation_inventory=values[3],
                )

    def test_platform_metadata_does_not_change_identity(self):
        values = fixture_inputs()
        _, _, provenance = build_f3_bundle_bytes(*values, project_root=ROOT)
        changed = copy.deepcopy(provenance)
        changed["software"]["platform_system"] = "Other"
        changed["software"]["platform_machine"] = "other"
        self.assertEqual(
            f3_dataset_id(identity_from_provenance(provenance)),
            f3_dataset_id(identity_from_provenance(changed)),
        )

    def test_informative_config_hash_does_not_change_effective_identity(self):
        values = fixture_inputs()
        _, _, provenance = build_f3_bundle_bytes(*values, project_root=ROOT)
        changed = copy.deepcopy(provenance)
        changed["inputs"]["config"]["file_sha256"] = "9" * 64
        self.assertEqual(
            f3_dataset_id(identity_from_provenance(provenance)),
            f3_dataset_id(identity_from_provenance(changed)),
        )

    def test_false_informative_provenance_is_rejected(self):
        values = fixture_inputs()
        dataset_id, outputs, provenance = build_f3_bundle_bytes(*values, project_root=ROOT)
        changed = copy.deepcopy(provenance)
        changed["inputs"]["catalog"]["size_bytes"] += 1
        outputs["provenance.json"] = canonical_json_bytes(changed, newline=True)
        outputs["sha256.txt"] = checksum_bytes(outputs)
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / dataset_id
            materialize(bundle, outputs)
            with self.assertRaises(F3BundleValidationError):
                validate_f3_bundle(
                    bundle, inputs=values[0], normalized=values[1],
                    association_inventory=values[2], relation_inventory=values[3],
                )

    def test_extra_file_and_symlink_are_rejected(self):
        values = fixture_inputs()
        dataset_id, outputs, _ = build_f3_bundle_bytes(*values, project_root=ROOT)
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / dataset_id
            materialize(bundle, outputs)
            (bundle / "extra").write_text("x")
            with self.assertRaises(F3BundleValidationError):
                validate_f3_bundle(
                    bundle, inputs=values[0], normalized=values[1],
                    association_inventory=values[2], relation_inventory=values[3],
                )
            (bundle / "extra").unlink()
            (bundle / "sha256.txt").unlink()
            (bundle / "sha256.txt").symlink_to(bundle / "provenance.json")
            with self.assertRaises(F3BundleValidationError):
                validate_f3_bundle(
                    bundle, inputs=values[0], normalized=values[1],
                    association_inventory=values[2], relation_inventory=values[3],
                )

    def test_publish_and_cache_hit_without_overwrite(self):
        values = fixture_inputs()
        with tempfile.TemporaryDirectory() as directory:
            destination, cache_hit = publish_f3_bundle(
                *values, project_root=ROOT, processed_osm_root=Path(directory)
            )
            self.assertFalse(cache_hit)
            before = {path.name: path.read_bytes() for path in destination.iterdir()}
            same, cache_hit = publish_f3_bundle(
                *values, project_root=ROOT, processed_osm_root=Path(directory)
            )
            self.assertEqual(same, destination)
            self.assertTrue(cache_hit)
            self.assertEqual(before, {path.name: path.read_bytes() for path in destination.iterdir()})

    def test_existing_corrupt_bundle_is_conflict(self):
        values = fixture_inputs()
        with tempfile.TemporaryDirectory() as directory:
            destination, _ = publish_f3_bundle(
                *values, project_root=ROOT, processed_osm_root=Path(directory)
            )
            (destination / "sha256.txt").write_text("corrupt\n")
            with self.assertRaises(F3BundleConflictError):
                publish_f3_bundle(*values, project_root=ROOT, processed_osm_root=Path(directory))

    def test_unsupported_atomic_publish_cleans_temporary(self):
        values = fixture_inputs()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch(
                "src.tfg_phase0.f3_bundle._rename_noreplace",
                side_effect=F3PublicationUnsupportedError("unsupported"),
            ):
                with self.assertRaises(F3PublicationUnsupportedError):
                    publish_f3_bundle(*values, project_root=ROOT, processed_osm_root=output)
            snapshot_root = output / values[0].snapshot.osm_snapshot_id
            self.assertEqual(tuple(snapshot_root.iterdir()), ())

    def test_write_failure_cleans_only_own_temporary(self):
        values = fixture_inputs()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            marker_parent = output / values[0].snapshot.osm_snapshot_id
            marker_parent.mkdir()
            marker = marker_parent / ".unrelated"
            marker.write_text("keep")
            original_open = Path.open

            def fail_bundle_write(path, mode="r", *args, **kwargs):
                if mode == "xb":
                    raise OSError("write failed")
                return original_open(path, mode, *args, **kwargs)

            with patch("pathlib.Path.open", new=fail_bundle_write):
                with self.assertRaises(OSError):
                    publish_f3_bundle(*values, project_root=ROOT, processed_osm_root=output)
            self.assertEqual(marker.read_text(), "keep")
            self.assertEqual(tuple(path for path in marker_parent.iterdir() if path != marker), ())

    def test_changed_config_is_rejected_before_publication(self):
        values = fixture_inputs()
        changed = replace(values[0], config_sha256="0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(F3BundleConflictError):
                publish_f3_bundle(
                    changed, *values[1:], project_root=ROOT,
                    processed_osm_root=Path(directory),
                )

    def test_cache_hit_allows_non_effective_config_change(self):
        values = fixture_inputs()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            destination, _ = publish_f3_bundle(
                *values, project_root=ROOT, processed_osm_root=output
            )
            config_path = ROOT / "tests/fixtures/f3/cache-hit-config.json"
            try:
                config = json.loads((ROOT / "config/madrid.yaml").read_text())
                config["osm_acquisition"]["endpoint"] = "https://example.test/api"
                config_path.write_text(json.dumps(config), encoding="utf-8")
                changed = replace(values[0], config_path=config_path)
                same, cache_hit = publish_f3_bundle(
                    changed, *values[1:], project_root=ROOT, processed_osm_root=output
                )
                self.assertEqual(same, destination)
                self.assertTrue(cache_hit)
            finally:
                config_path.unlink(missing_ok=True)

    def test_lock_cleanup_failure_is_reported(self):
        values = fixture_inputs()
        with tempfile.TemporaryDirectory() as directory:
            original_rmdir = Path.rmdir

            def fail_lock(path):
                if path.name.endswith(".lock"):
                    raise OSError("lock cleanup failed")
                return original_rmdir(path)

            with patch("pathlib.Path.rmdir", new=fail_lock):
                with self.assertRaisesRegex(Exception, "lock propio"):
                    publish_f3_bundle(
                        *values, project_root=ROOT,
                        processed_osm_root=Path(directory),
                    )

    def test_full_synthetic_pipeline_to_published_bundle(self):
        config = load_region_config(ROOT / "config/madrid.yaml")
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as directory:
            temporary = Path(directory)
            manifest_path = temporary / "manifest.json"
            write_manifest(build_catalog(config, spacing_m=50), manifest_path)
            raw = (ROOT / "tests/fixtures/f3/inputs/source.osm").read_bytes()
            counts = validate_osm_xml(raw, len(raw), config["region"]["bbox"])
            provenance = build_snapshot_provenance(
                config=config,
                query=build_overpass_query(config["region"]["bbox"], 60),
                raw=raw,
                counts=counts,
                acquired_at=datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc),
                attempts=1,
                http_status=200,
                content_type="application/xml",
            )
            part = temporary / "source.part"
            part.write_bytes(raw)
            snapshot_dir, _ = publish_snapshot(
                raw_part=part,
                snapshots_root=temporary / "snapshots",
                provenance=provenance,
            )
            inputs = load_verified_f3_inputs(
                manifest_path=manifest_path,
                snapshot_dir=snapshot_dir,
                config_path=ROOT / "config/madrid.yaml",
                rules_path=RULES,
            )
            normalized = normalize_osm_geometries(inputs)
            associations = associate_candidates_with_osm(inputs.catalog, normalized)
            relations = build_relation_context(inputs, normalized, associations)
            destination, cache_hit = publish_f3_bundle(
                inputs, normalized, associations, relations,
                project_root=ROOT,
                processed_osm_root=temporary / "processed",
            )
            self.assertFalse(cache_hit)
            document = validate_f3_bundle(
                destination, inputs=inputs, normalized=normalized,
                association_inventory=associations, relation_inventory=relations,
            )
            self.assertEqual(document["f3_dataset_id"], destination.name)


if __name__ == "__main__":
    unittest.main()
