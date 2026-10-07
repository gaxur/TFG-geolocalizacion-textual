import copy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f3_inputs import (
    D049_RULES_SHA256,
    F3InputError,
    load_d049_rules,
    load_verified_catalog,
    load_verified_f3_inputs,
    load_verified_snapshot,
    parse_osm_inventory,
)
from src.tfg_phase0.osm_snapshot import (
    SnapshotConflictError,
    build_overpass_query,
    build_snapshot_provenance,
    publish_snapshot,
    validate_local_snapshot,
    validate_osm_xml,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = ROOT / "tests" / "fixtures" / "f3" / "inputs" / "source.osm"
RULES = ROOT / "third_party" / "osm-polygon-features" / "v0.9.2" / "polygon-features.json"
FIXED_NOW = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)


class Phase3InputTests(unittest.TestCase):
    def setUp(self):
        self.config = load_region_config(ROOT / "config" / "madrid.yaml")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest_path = self.root / "manifest-25m.json"
        write_manifest(build_catalog(self.config, spacing_m=25), self.manifest_path)
        self.snapshot_dir = self._build_snapshot()

    def tearDown(self):
        self.temporary.cleanup()

    def _build_snapshot(self, name="snapshots"):
        raw = SOURCE_FIXTURE.read_bytes()
        counts = validate_osm_xml(raw, len(raw), self.config["region"]["bbox"])
        provenance = build_snapshot_provenance(
            config=self.config,
            query=build_overpass_query(self.config["region"]["bbox"], 60),
            raw=raw,
            counts=counts,
            acquired_at=FIXED_NOW,
            attempts=1,
            http_status=200,
            content_type="application/xml",
        )
        part = self.root / "source.osm.part"
        part.write_bytes(raw)
        snapshot_dir, _ = publish_snapshot(
            raw_part=part,
            snapshots_root=self.root / name,
            provenance=provenance,
        )
        return snapshot_dir

    def test_loads_verified_f1_without_regenerating_it(self):
        catalog = load_verified_catalog(self.manifest_path, self.config)
        self.assertEqual(catalog.manifest_id, "madrid-pilot-grid-v1-s25-l25")
        self.assertEqual(catalog.spacing_m, 25)
        self.assertEqual(len(catalog.candidates), 1115)
        self.assertEqual(dict(catalog.region_bbox_wgs84), self.config["region"]["bbox"])
        self.assertEqual(catalog.provenance["artifact_id"], catalog.manifest_id)
        with self.assertRaises(FrozenInstanceError):
            catalog.spacing_m = 50
        with self.assertRaises(TypeError):
            catalog.provenance["artifact_id"] = "changed"

    def test_rejects_incomplete_or_extra_candidate_sequence(self):
        original = self.manifest_path.read_bytes()
        for index in (0, 10, -1):
            manifest = json.loads(original)
            del manifest["candidates"][index]
            self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(missing_index=index), self.assertRaises(F3InputError):
                load_verified_catalog(self.manifest_path, self.config)

        self.manifest_path.write_bytes(original)
        manifest = json.loads(original)
        extra = copy.deepcopy(manifest["candidates"][-1])
        extra["generation"]["column"] += 1
        extra["candidate_id"] = extra["candidate_id"].rsplit("C", 1)[0] + "C9999"
        manifest["candidates"].append(extra)
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

    def test_rejects_missing_invalid_and_incoherent_f1(self):
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.root / "missing.json", self.config)

        invalid_json = self.root / "invalid.json"
        invalid_json.write_text("{", encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(invalid_json, self.config)

        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["manifest_id"] = "incoherent"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

    def test_rejects_duplicate_and_incoherent_candidate_identity(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["candidates"].append(copy.deepcopy(manifest["candidates"][0]))
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

    def test_rejects_modified_candidate_coordinates_and_geometry(self):
        fields = (
            ("generation", "center_easting_m"),
            ("generation", "center_northing_m"),
            (None, "latitude"),
            (None, "longitude"),
        )
        original = self.manifest_path.read_bytes()
        for group, field in fields:
            self.manifest_path.write_bytes(original)
            manifest = json.loads(original)
            target = manifest["candidates"][0] if group is None else manifest["candidates"][0][group]
            target[field] += 0.001
            self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(F3InputError):
                load_verified_catalog(self.manifest_path, self.config)

        self.manifest_path.write_bytes(original)
        manifest = json.loads(original)
        manifest["candidates"][0]["cell_geometry"]["coordinates"][0][0][0] += 0.0001
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

    def test_rejects_duplicate_center_and_wrong_candidate_order(self):
        original = self.manifest_path.read_bytes()
        manifest = json.loads(original)
        manifest["candidates"][1]["generation"]["center_easting_m"] = manifest["candidates"][0]["generation"]["center_easting_m"]
        manifest["candidates"][1]["generation"]["center_northing_m"] = manifest["candidates"][0]["generation"]["center_northing_m"]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

        self.manifest_path.write_bytes(original)
        manifest = json.loads(original)
        manifest["candidates"][0], manifest["candidates"][1] = manifest["candidates"][1], manifest["candidates"][0]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

    def test_rejects_incoherent_grid_and_parameters_hashes(self):
        original = self.manifest_path.read_bytes()
        manifest = json.loads(original)
        manifest["generation"]["grid_hash"] = "0" * 12
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

        self.manifest_path.write_bytes(original)
        manifest = json.loads(original)
        manifest["provenance"]["parameters_hash"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

    def test_rejects_non_finite_bbox(self):
        incompatible = copy.deepcopy(self.config)
        incompatible["region"]["bbox"]["north"] = math.nan
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, incompatible)

        write_manifest(build_catalog(self.config, spacing_m=25), self.manifest_path)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["candidates"][0]["candidate_id"] = "candidate-wrong"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, self.config)

    def test_rejects_incompatible_config_without_selecting_a_default_spacing(self):
        incompatible = copy.deepcopy(self.config)
        incompatible["region"]["bbox"]["north"] += 0.001
        with self.assertRaises(F3InputError):
            load_verified_catalog(self.manifest_path, incompatible)

        manifest_50 = self.root / "manifest-50m.json"
        write_manifest(build_catalog(self.config, spacing_m=50), manifest_50)
        self.assertEqual(load_verified_catalog(manifest_50, self.config).spacing_m, 50)

    def test_validates_and_loads_local_f2(self):
        provenance, raw = validate_local_snapshot(self.snapshot_dir)
        snapshot = load_verified_snapshot(self.snapshot_dir)
        self.assertEqual(snapshot.osm_snapshot_id, provenance["osm_snapshot_id"])
        self.assertEqual(snapshot.raw_sha256, provenance["raw_sha256"])
        self.assertEqual(snapshot.raw, raw)
        with self.assertRaises(TypeError):
            snapshot.provenance["region_id"] = "other"

    def test_rejects_f2_hash_and_provenance_mismatch(self):
        source = self.snapshot_dir / "source.osm"
        source.write_bytes(source.read_bytes() + b"\n")
        with self.assertRaises(F3InputError):
            load_verified_snapshot(self.snapshot_dir)

        other_snapshot = self._build_snapshot("other-snapshots")
        provenance_path = other_snapshot / "provenance.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance["counts"]["node"] += 1
        provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
        with self.assertRaises(F3InputError):
            load_verified_snapshot(other_snapshot)

    def test_rejects_each_missing_f2_artifact(self):
        for filename in ("source.osm", "provenance.json", "sha256.txt"):
            snapshot = self._build_snapshot(f"missing-{filename.replace('.', '-')}")
            (snapshot / filename).unlink()
            with self.subTest(filename=filename), self.assertRaises(F3InputError):
                load_verified_snapshot(snapshot)

    def test_parser_preserves_order_roles_and_missing_relation_members(self):
        inventory = parse_osm_inventory(SOURCE_FIXTURE, self.config["region"]["bbox"])
        self.assertEqual(tuple(node.osm_id for node in inventory.nodes), (1, 2))
        self.assertEqual(inventory.nodes[0].source_role, "node_bbox")
        self.assertEqual(inventory.nodes[1].source_role, "added_way_node")
        self.assertEqual(inventory.ways[0].ordered_node_refs, (1, 2))
        self.assertEqual(
            tuple((member.member_type, member.ref, member.role, member.present) for member in inventory.relations[0].members),
            (
                ("way", 10, "local", True),
                ("way", 999, "remote", False),
                ("node", 999, "stop", False),
                ("relation", 999, "subarea", False),
            ),
        )

    def test_parser_rejects_missing_way_reference(self):
        raw = SOURCE_FIXTURE.read_text(encoding="utf-8").replace(
            '<node id="2" lat="40.4210" lon="-3.7037" version="1"/>\n', ""
        )
        path = self.root / "missing-way-node.osm"
        path.write_text(raw, encoding="utf-8")
        with self.assertRaises(F3InputError):
            parse_osm_inventory(path, self.config["region"]["bbox"])

    def test_parser_rejects_duplicate_ids_tags_and_unjustified_external_node(self):
        original = SOURCE_FIXTURE.read_text(encoding="utf-8")
        variants = {
            "duplicate-id": original.replace('<node id="2"', '<node id="1"'),
            "duplicate-tag": original.replace(
                '<tag k="name" v="Fixture"/>',
                '<tag k="name" v="Fixture"/><tag k="name" v="Other"/>',
            ),
            "unjustified-external": original.replace(
                '<node id="2" lat="40.4210" lon="-3.7037" version="1"/>',
                '<node id="2" lat="40.4169" lon="-3.7037" version="1"/><node id="3" lat="40.4210" lon="-3.7037" version="1"/>',
            ),
        }
        for name, raw in variants.items():
            path = self.root / f"{name}.osm"
            path.write_text(raw, encoding="utf-8")
            with self.subTest(name=name), self.assertRaises(F3InputError):
                parse_osm_inventory(path, self.config["region"]["bbox"])

    def test_d049_rules_are_verified_before_loading(self):
        rules = load_d049_rules(RULES)
        self.assertEqual(rules.sha256, D049_RULES_SHA256)
        self.assertEqual(rules.policy, "way_is_area-v1")
        self.assertEqual(rules.release, "v0.9.2")
        self.assertEqual(rules.commit, "069a46416629ddbe84390c7a3ccc600fe73ee706")
        self.assertIn(("building", "all", ()), rules.rules)

        altered = self.root / "polygon-features.json"
        altered.write_bytes(RULES.read_bytes() + b"\n")
        with self.assertRaises(F3InputError):
            load_d049_rules(altered)
        with self.assertRaises(F3InputError):
            load_d049_rules(self.root / "missing-rules.json")

    def test_combined_loader_is_deterministic_and_has_no_geometry(self):
        first = load_verified_f3_inputs(
            manifest_path=self.manifest_path,
            snapshot_dir=self.snapshot_dir,
            config_path=ROOT / "config" / "madrid.yaml",
            rules_path=RULES,
        )
        second = load_verified_f3_inputs(
            manifest_path=self.manifest_path,
            snapshot_dir=self.snapshot_dir,
            config_path=ROOT / "config" / "madrid.yaml",
            rules_path=RULES,
        )
        self.assertEqual(first, second)
        self.assertFalse(hasattr(first.inventory.nodes[0], "geometry"))
        self.assertFalse(hasattr(first.inventory.ways[0], "geometry"))

    def test_combined_loader_has_no_network_path(self):
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            load_verified_f3_inputs(
                manifest_path=self.manifest_path,
                snapshot_dir=self.snapshot_dir,
                config_path=ROOT / "config" / "madrid.yaml",
                rules_path=RULES,
            )

    def test_combined_loader_rejects_source_changed_after_validation(self):
        from src.tfg_phase0.osm_snapshot import validate_local_snapshot as validate

        def validate_then_change(path):
            result = validate(path)
            source = Path(path) / "source.osm"
            source.write_bytes(source.read_bytes() + b"\n")
            return result

        with patch("src.tfg_phase0.f3_inputs.validate_local_snapshot", side_effect=validate_then_change):
            with self.assertRaises(F3InputError):
                load_verified_f3_inputs(
                    manifest_path=self.manifest_path,
                    snapshot_dir=self.snapshot_dir,
                    config_path=ROOT / "config" / "madrid.yaml",
                    rules_path=RULES,
                )

    def test_combined_loader_does_not_modify_inputs(self):
        paths = (
            self.manifest_path,
            self.snapshot_dir / "source.osm",
            self.snapshot_dir / "provenance.json",
            self.snapshot_dir / "sha256.txt",
            RULES,
        )
        before = {path: path.read_bytes() for path in paths}
        load_verified_f3_inputs(
            manifest_path=self.manifest_path,
            snapshot_dir=self.snapshot_dir,
            config_path=ROOT / "config" / "madrid.yaml",
            rules_path=RULES,
        )
        self.assertEqual(before, {path: path.read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
