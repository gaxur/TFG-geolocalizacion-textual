import copy
import hashlib
import json
import socket
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.osm_snapshot import (
    RawSizeLimitError,
    SnapshotConflictError,
    SnapshotError,
    SnapshotValidationError,
    TransportResponse,
    acquire_raw,
    acquire_snapshot,
    build_overpass_query,
    build_snapshot_provenance,
    publish_snapshot,
    sha256_bytes,
    snapshot_id,
    validate_osm_xml,
)
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/osm/valid.osm"
FIXED_NOW = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, endpoint, body, headers, connect_timeout, total_timeout):
        self.calls.append((endpoint, body, dict(headers), connect_timeout, total_timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(raw, status=200, headers=None):
    return TransportResponse(status, headers or {"Content-Type": "application/xml"}, [raw])


def replace(raw, old, new):
    return raw.replace(old.encode(), new.encode())


class Phase2SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_region_config(ROOT / "config/madrid.yaml")
        cls.raw = FIXTURE.read_bytes()
        cls.query = build_overpass_query(
            cls.config["region"]["bbox"],
            cls.config["osm_acquisition"]["server_timeout_seconds"],
        )

    def test_query_is_exact_and_deterministic(self):
        expected = """[out:xml][timeout:60];
(
  node(40.4120,-3.7090,40.4200,-3.6990);
  way(40.4120,-3.7090,40.4200,-3.6990);
)->.local;
(
  .local;
  node(w.local);
  rel(bn.local);
  rel(bw.local);
);
out meta qt;
"""
        self.assertEqual(self.query, expected)
        self.assertEqual(build_overpass_query(self.config["region"]["bbox"], 60), expected)
        self.assertEqual(hashlib.sha256(expected.encode()).hexdigest(), sha256_bytes(self.query.encode()))

    def test_snapshot_id_is_content_addressed(self):
        digest = sha256_bytes(self.raw)
        expected = f"osm-madrid-pilot-osmxml-sha256-{digest}"
        self.assertEqual(snapshot_id("madrid_pilot", "osmxml", digest), expected)
        self.assertEqual(snapshot_id("madrid_pilot", "osmxml", digest), expected)
        self.assertNotEqual(
            snapshot_id("madrid_pilot", "osmxml", sha256_bytes(self.raw + b"\n")), expected
        )

    def test_valid_xml_and_nested_relation_counts(self):
        counts = validate_osm_xml(self.raw, 1_000_000, self.config["region"]["bbox"])
        self.assertEqual(counts["node"], 2)
        self.assertEqual(counts["way"], 1)
        self.assertEqual(counts["relation"], 2)
        self.assertEqual(
            counts["selected_objects"],
            {"node_bbox": 1, "way_bbox_intersection": 1, "relation_context": 2},
        )
        self.assertEqual(counts["added_way_nodes"], 1)
        self.assertEqual(counts["resolved_relation_members"], {"node": 0, "way": 1, "relation": 1})
        self.assertEqual(counts["unresolved_relation_members"], {"node": 1, "way": 1, "relation": 1})

    def test_rejects_truncated_html_remark_and_entities(self):
        invalid = (
            self.raw[:-10],
            b"<html><body>error</body></html>",
            b'<osm version="0.6"><remark>runtime error</remark></osm>',
            b'<!DOCTYPE osm [<!ENTITY x SYSTEM "file:///etc/passwd">]><osm version="0.6"></osm>',
        )
        for raw in invalid:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(SnapshotValidationError):
                    validate_osm_xml(raw, 1_000_000, self.config["region"]["bbox"])

    def test_rejects_duplicate_ids_and_invalid_coordinates(self):
        duplicate = self.raw.replace(b'<node id="2"', b'<node id="1"')
        invalid_coordinate = self.raw.replace(b'lat="40.4168"', b'lat="95"')
        not_finite = self.raw.replace(b'lat="40.4168"', b'lat="NaN"')
        for raw in (duplicate, invalid_coordinate, not_finite):
            with self.assertRaises(SnapshotValidationError):
                validate_osm_xml(raw, 1_000_000, self.config["region"]["bbox"])

    def test_rejects_missing_way_and_relation_members(self):
        missing_node = self.raw.replace(b'<node id="2" lat="40.4210" lon="-3.7037" version="1"/>\n', b"")
        missing_way = self.raw.replace(b'<way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="service"/></way>\n', b"")
        for raw in (missing_node, missing_way):
            with self.assertRaises(SnapshotValidationError):
                validate_osm_xml(raw, 1_000_000, self.config["region"]["bbox"])

    def test_unresolved_relation_members_are_allowed(self):
        counts = validate_osm_xml(self.raw, 1_000_000, self.config["region"]["bbox"])
        self.assertEqual(counts["unresolved_relation_members"], {"node": 1, "way": 1, "relation": 1})

    def test_relation_member_with_invalid_type_or_ref_fails(self):
        invalid_type = self.raw.replace(b'type="way" ref="999"', b'type="area" ref="999"')
        invalid_ref = self.raw.replace(b'type="way" ref="999"', b'type="way" ref="invalid"')
        missing_role = self.raw.replace(b'type="way" ref="999" role="remote"', b'type="way" ref="999"')
        for raw in (invalid_type, invalid_ref, missing_role):
            with self.assertRaises(SnapshotValidationError):
                validate_osm_xml(raw, 1_000_000, self.config["region"]["bbox"])

    def test_rejects_size_limit(self):
        with self.assertRaises(RawSizeLimitError):
            validate_osm_xml(self.raw, len(self.raw) - 1, self.config["region"]["bbox"])

    def test_streaming_size_limit_removes_partial_file(self):
        config = copy.deepcopy(self.config["osm_acquisition"])
        config["max_raw_bytes"] = len(self.raw) - 1
        with tempfile.TemporaryDirectory() as directory:
            part = Path(directory) / "raw.part"
            with self.assertRaises(RawSizeLimitError):
                acquire_raw(
                    config, self.query, part, transport=FakeTransport([response(self.raw)]),
                    sleep=lambda _: None, now=lambda: FIXED_NOW,
                )
            self.assertFalse(part.exists())

    def test_retryable_statuses_and_backoff(self):
        for status in (429, 502, 503, 504):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                first = urllib.error.HTTPError("https://test", status, "error", {}, None)
                transport = FakeTransport([first, response(self.raw)])
                sleeps = []
                result = acquire_raw(
                    self.config["osm_acquisition"], self.query, Path(directory) / "raw.part",
                    transport=transport, sleep=sleeps.append, now=lambda: FIXED_NOW,
                )
                self.assertEqual(result[2], 2)
                self.assertEqual(sleeps, [5])

    def test_retry_after_is_capped(self):
        with tempfile.TemporaryDirectory() as directory:
            error = urllib.error.HTTPError("https://test", 429, "error", {"Retry-After": "600"}, None)
            transport = FakeTransport([error, response(self.raw)])
            sleeps = []
            acquire_raw(
                self.config["osm_acquisition"], self.query, Path(directory) / "raw.part",
                transport=transport, sleep=sleeps.append, now=lambda: FIXED_NOW,
            )
            self.assertEqual(sleeps, [60])

    def test_timeout_retries_at_most_three_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = FakeTransport([socket.timeout(), socket.timeout(), socket.timeout()])
            sleeps = []
            with self.assertRaises(SnapshotError):
                acquire_raw(
                    self.config["osm_acquisition"], self.query, Path(directory) / "raw.part",
                    transport=transport, sleep=sleeps.append, now=lambda: FIXED_NOW,
                )
            self.assertEqual(len(transport.calls), 3)
            self.assertEqual(sleeps, [5, 15])

    def test_streaming_connection_failure_retries(self):
        def broken_chunks():
            yield self.raw[:10]
            raise ConnectionResetError("reset")

        with tempfile.TemporaryDirectory() as directory:
            transport = FakeTransport([
                TransportResponse(200, {"Content-Type": "application/xml"}, broken_chunks()),
                response(self.raw),
            ])
            sleeps = []
            result = acquire_raw(
                self.config["osm_acquisition"], self.query, Path(directory) / "raw.part",
                transport=transport, sleep=sleeps.append, now=lambda: FIXED_NOW,
            )
            self.assertEqual(result[2], 2)
            self.assertEqual(sleeps, [5])

    def test_non_retryable_4xx_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            error = urllib.error.HTTPError("https://test", 400, "bad query", {}, None)
            transport = FakeTransport([error])
            with self.assertRaises(SnapshotError):
                acquire_raw(
                    self.config["osm_acquisition"], self.query, Path(directory) / "raw.part",
                    transport=transport, sleep=lambda _: None, now=lambda: FIXED_NOW,
                )
            self.assertEqual(len(transport.calls), 1)

    def test_endpoint_rejects_credentials_or_query_secrets(self):
        for endpoint in (
            "https://user:secret@example.test/api",
            "https://example.test/api?token=secret",
        ):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as directory:
                config = copy.deepcopy(self.config["osm_acquisition"])
                config["endpoint"] = endpoint
                with self.assertRaises(SnapshotValidationError):
                    acquire_raw(
                        config, self.query, Path(directory) / "raw.part",
                        transport=FakeTransport([response(self.raw)]), sleep=lambda _: None,
                    )

    def test_provenance_is_valid_and_has_no_secrets(self):
        counts = validate_osm_xml(self.raw, 1_000_000, self.config["region"]["bbox"])
        provenance = build_snapshot_provenance(
            config=self.config, query=self.query, raw=self.raw, counts=counts,
            acquired_at=FIXED_NOW, attempts=1, http_status=200,
            content_type="application/xml",
        )
        validate_document(provenance, "osm_snapshot")
        schema = json.loads((ROOT / "schemas/osm_snapshot.schema.json").read_text())
        jsonschema.validate(provenance, schema)
        serialized = json.dumps(provenance).lower()
        for forbidden in ("authorization", "cookie", "token", "password"):
            self.assertNotIn(forbidden, serialized)

    def test_provenance_rejects_secret_endpoint(self):
        counts = validate_osm_xml(self.raw, 1_000_000, self.config["region"]["bbox"])
        provenance = build_snapshot_provenance(
            config=self.config, query=self.query, raw=self.raw, counts=counts,
            acquired_at=FIXED_NOW, attempts=1, http_status=200,
            content_type="application/xml",
        )
        provenance["endpoint"] = "https://example.test/api?token=secret"
        with self.assertRaises(SchemaValidationError):
            validate_document(provenance, "osm_snapshot")

    def test_atomic_publish_cache_hit_and_corruption(self):
        counts = validate_osm_xml(self.raw, 1_000_000, self.config["region"]["bbox"])
        provenance = build_snapshot_provenance(
            config=self.config, query=self.query, raw=self.raw, counts=counts,
            acquired_at=FIXED_NOW, attempts=1, http_status=200,
            content_type="application/xml",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "raw" / "osm" / "snapshots"
            part = Path(directory) / "first.part"
            part.write_bytes(self.raw)
            destination, cache_hit = publish_snapshot(raw_part=part, snapshots_root=root, provenance=provenance)
            self.assertFalse(cache_hit)
            self.assertTrue((destination / "source.osm").is_file())
            self.assertFalse(part.exists())

            second = Path(directory) / "second.part"
            second.write_bytes(self.raw)
            same, cache_hit = publish_snapshot(raw_part=second, snapshots_root=root, provenance=provenance)
            self.assertEqual(same, destination)
            self.assertTrue(cache_hit)
            self.assertTrue(second.exists())

            (destination / "sha256.txt").write_text("0" * 64 + "\n")
            with self.assertRaises(SnapshotConflictError):
                publish_snapshot(raw_part=second, snapshots_root=root, provenance=provenance)

    def test_publish_rejects_raw_provenance_mismatch(self):
        counts = validate_osm_xml(self.raw, 1_000_000, self.config["region"]["bbox"])
        provenance = build_snapshot_provenance(
            config=self.config, query=self.query, raw=self.raw, counts=counts,
            acquired_at=FIXED_NOW, attempts=1, http_status=200,
            content_type="application/xml",
        )
        with tempfile.TemporaryDirectory() as directory:
            part = Path(directory) / "wrong.part"
            part.write_bytes(self.raw + b"\n")
            with self.assertRaises(SnapshotConflictError):
                publish_snapshot(
                    raw_part=part,
                    snapshots_root=Path(directory) / "snapshots",
                    provenance=provenance,
                )

    def test_failed_validation_never_publishes(self):
        transport = FakeTransport([response(self.raw[:-10])])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "raw" / "osm" / "snapshots"
            with self.assertRaises(SnapshotValidationError):
                acquire_snapshot(
                    self.config, root, transport=transport,
                    sleep=lambda _: None, now=lambda: FIXED_NOW,
                )
            published = [path for path in root.iterdir() if not path.name.startswith(".")]
            self.assertEqual(published, [])

    def test_acquisition_uses_injected_transport_only(self):
        transport = FakeTransport([response(self.raw)])
        with tempfile.TemporaryDirectory() as directory:
            destination, cache_hit = acquire_snapshot(
                self.config, Path(directory) / "raw" / "osm" / "snapshots",
                transport=transport, sleep=lambda _: None, now=lambda: FIXED_NOW,
            )
            self.assertFalse(cache_hit)
            self.assertEqual(len(transport.calls), 1)
            self.assertIn(b"data=", transport.calls[0][1])
            self.assertTrue(destination.is_dir())

    def test_expected_snapshot_id_is_cache_hit_without_transport(self):
        transport = FakeTransport([response(self.raw)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "snapshots"
            destination, _ = acquire_snapshot(
                self.config, root, transport=transport,
                sleep=lambda _: None, now=lambda: FIXED_NOW,
            )
            calls_after_publish = len(transport.calls)

            def forbidden_transport(*args):
                raise AssertionError("no debe acceder a red para cache hit")

            cached, cache_hit = acquire_snapshot(
                self.config, root, expected_snapshot_id=destination.name,
                transport=forbidden_transport,
            )
            self.assertEqual(cached, destination)
            self.assertTrue(cache_hit)
            self.assertEqual(len(transport.calls), calls_after_publish)

    def test_existing_provenance_corruption_is_rejected(self):
        transport = FakeTransport([response(self.raw)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "snapshots"
            destination, _ = acquire_snapshot(
                self.config, root, transport=transport,
                sleep=lambda _: None, now=lambda: FIXED_NOW,
            )
            provenance_path = destination / "provenance.json"
            provenance = json.loads(provenance_path.read_text())
            provenance["raw_size_bytes"] += 1
            provenance_path.write_text(json.dumps(provenance))
            with self.assertRaises(SnapshotConflictError):
                acquire_snapshot(
                    self.config, root, expected_snapshot_id=destination.name,
                    transport=lambda *args: (_ for _ in ()).throw(AssertionError("sin red")),
                )


if __name__ == "__main__":
    unittest.main()
