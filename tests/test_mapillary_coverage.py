import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from src.tfg_phase0.mapillary_coverage import (
    MapillaryAPIError,
    MapillaryClient,
    MapillaryClientConfig,
    MapillaryCoverageError,
    MapillaryTokenMissingError,
    build_coverage,
    canonical_bytes,
    haversine_m,
    validate_coverage,
    validate_inventory,
    validate_run_manifest,
)


BBOX = {"north": 40.42, "south": 40.412, "east": -3.699, "west": -3.709}


class FakeResponse:
    def __init__(self, document):
        self.payload = canonical_bytes(document)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def image(image_id, latitude=40.4168, longitude=-3.7038, **overrides):
    row = {
        "id": str(image_id),
        "computed_geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "captured_at": 1_700_000_000_000,
        "computed_compass_angle": 10,
        "sequence": "seq-1",
        "camera_type": "perspective",
        "width": 2048,
        "height": 1536,
        "quality_score": 0.8,
    }
    row.update(overrides)
    return row


def paged_opener(pages, requests):
    iterator = iter(pages)

    def open_request(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(next(iterator))

    return open_request


def inventory_fixture():
    requests = []
    client = MapillaryClient(
        "secret-token",
        config=MapillaryClientConfig(request_interval_seconds=0, max_retries=0),
        opener=paged_opener([{"data": [image("1")]}], requests),
        sleeper=lambda _: None,
    )
    return client.inventory(BBOX, acquired_at_utc="2026-10-22T00:00:00Z")


def catalog(count, manifest_id, latitude=40.4168, longitude=-3.7038):
    return {
        "manifest_id": manifest_id,
        "candidates": [
            {"candidate_id": f"candidate-{index:04d}", "latitude": latitude, "longitude": longitude}
            for index in range(count)
        ],
    }


def rankings_fixture():
    rows = []
    ids = [f"candidate-{index:04d}" for index in range(88)]
    for query_number in range(11, 26):
        start = (query_number - 11) * 6
        selected = [ids[(start + offset) % len(ids)] for offset in range(10)]
        rows.append({
            "query_id": f"H{query_number}",
            "gallery_id": "madrid-50m",
            "kind": "en_cartographic",
            "results": [{"candidate_id": candidate_id} for candidate_id in selected],
        })
    # Fuerza que los 88 IDs aparezcan al menos una vez sin alterar 15 Top-10.
    rows[-1]["results"] = [{"candidate_id": candidate_id} for candidate_id in ids[-10:]]
    assert len({item["candidate_id"] for row in rows for item in row["results"]}) == 88
    return {"rows": rows}


class MapillaryClientTests(unittest.TestCase):
    def test_missing_token_stops_before_opener(self):
        called = False

        def opener(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("no debe haber red")

        client = MapillaryClient("", opener=opener)
        with self.assertRaisesRegex(MapillaryTokenMissingError, "no se realizó"):
            client.inventory(BBOX)
        self.assertFalse(called)

    def test_pagination_normalization_and_deduplication(self):
        requests = []
        pages = [
            {"data": [image("2"), image("1")], "paging": {"next": "https://graph.mapillary.com/images?after=x&access_token=secret-token"}},
            {"data": [image("2"), image("3", computed_compass_angle=None, compass_angle=370)]},
        ]
        client = MapillaryClient(
            "secret-token",
            config=MapillaryClientConfig(request_interval_seconds=0, max_retries=0),
            opener=paged_opener(pages, requests),
            sleeper=lambda _: None,
        )
        result = client.inventory(BBOX, acquired_at_utc="2026-10-22T00:00:00Z")
        self.assertEqual(result["image_count"], 3)
        self.assertEqual([row["image_id"] for row in result["images"]], ["1", "2", "3"])
        self.assertEqual(result["images"][2]["orientation_degrees"], 10)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request.headers["Authorization"] == "OAuth secret-token" for request, _ in requests))
        self.assertNotIn("secret-token", json.dumps(result))
        validate_inventory(result)

    def test_http_error_redacts_token(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(b"{}"))

        client = MapillaryClient(
            "secret-token",
            config=MapillaryClientConfig(max_retries=0),
            opener=opener,
            sleeper=lambda _: None,
        )
        with self.assertRaises(MapillaryAPIError) as caught:
            client.inventory(BBOX)
        self.assertNotIn("secret-token", str(caught.exception))

    def test_retryable_api_error_retries(self):
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise HTTPError(request.full_url, 429, "limited", {}, io.BytesIO(b"{}"))
            return FakeResponse({"data": []})

        client = MapillaryClient(
            "token",
            config=MapillaryClientConfig(max_retries=1, request_interval_seconds=0),
            opener=opener,
            sleeper=lambda _: None,
        )
        self.assertEqual(client.inventory(BBOX)["image_count"], 0)
        self.assertEqual(calls, 2)

    def test_invalid_coordinates_are_rejected(self):
        client = MapillaryClient(
            "token",
            config=MapillaryClientConfig(max_retries=0),
            opener=paged_opener([{"data": [image("1", latitude=91)]}], []),
        )
        with self.assertRaisesRegex(MapillaryCoverageError, "fuera de rango"):
            client.inventory(BBOX)


class CoverageTests(unittest.TestCase):
    def test_haversine_and_radius_boundaries(self):
        self.assertAlmostEqual(haversine_m(40.4168, -3.7038, 40.4168, -3.7038), 0)
        inventory = inventory_fixture()
        catalogs = {
            "madrid-25m": catalog(1115, "manifest-25"),
            "madrid-50m": catalog(253, "manifest-50"),
        }
        result = build_coverage(inventory, catalogs, rankings_fixture(), input_hashes={"inventory": "0" * 64})
        for gallery in ("madrid-25m", "madrid-50m"):
            self.assertEqual(result["galleries"][gallery]["summary"]["10"]["covered_fraction"], 1.0)
        self.assertEqual(result["h11_h25_top10"]["summary"]["10"]["top10_slots_covered"], 150)
        self.assertFalse(result["protocol"]["ground_truth_used"])
        validate_coverage(result)

    def test_distinct_positions_orientations_and_no_coverage(self):
        requests = []
        images = [
            image("1", computed_compass_angle=5, sequence="a"),
            image("2", latitude=40.4168001, computed_compass_angle=95, sequence="a"),
            image("3", latitude=40.4169, computed_compass_angle=None, compass_angle=None, sequence="b"),
        ]
        client = MapillaryClient(
            "token",
            config=MapillaryClientConfig(max_retries=0),
            opener=paged_opener([{"data": images}], requests),
        )
        inventory = client.inventory(BBOX, acquired_at_utc="2026-10-22T00:00:00Z")
        catalogs = {
            "madrid-25m": catalog(1115, "manifest-25"),
            "madrid-50m": catalog(253, "manifest-50"),
        }
        result = build_coverage(inventory, catalogs, rankings_fixture(), input_hashes={})
        row = result["galleries"]["madrid-50m"]["candidates"][0]["radii"]["25"]
        self.assertEqual(row["image_count"], 3)
        self.assertEqual(row["distinct_camera_position_count"], 2)
        self.assertEqual(row["distinct_sequence_count"], 2)
        self.assertEqual(row["orientation_diversity"]["bin_count"], 2)

    def test_inventory_and_coverage_integrity_detect_tampering(self):
        inventory = inventory_fixture()
        changed = copy.deepcopy(inventory)
        changed["images"][0]["latitude"] += 0.001
        with self.assertRaisesRegex(MapillaryCoverageError, "inventory_id"):
            validate_inventory(changed)
        coverage = build_coverage(
            inventory,
            {"madrid-25m": catalog(1115, "manifest-25"), "madrid-50m": catalog(253, "manifest-50")},
            rankings_fixture(),
            input_hashes={},
        )
        changed_coverage = copy.deepcopy(coverage)
        changed_coverage["limitations"].append("tampered")
        with self.assertRaisesRegex(MapillaryCoverageError, "coverage_id"):
            validate_coverage(changed_coverage)

    def test_catalog_and_ranking_contract_counts_are_enforced(self):
        inventory = inventory_fixture()
        with self.assertRaisesRegex(MapillaryCoverageError, "1115"):
            build_coverage(
                inventory,
                {"madrid-25m": catalog(1, "bad"), "madrid-50m": catalog(253, "ok")},
                rankings_fixture(),
                input_hashes={},
            )

    def test_run_manifest_verifies_paths_sizes_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "coverage.json"
            artifact.write_bytes(b"{}\n")
            from src.tfg_phase0.mapillary_coverage import sha256_file
            manifest = {
                "schema_version": "1.0",
                "contract_version": "mapillary-d004-coverage-manifest-v1",
                "coverage_id": "fixture",
                "ground_truth_used": False,
                "images_downloaded": False,
                "artifacts": {
                    "coverage": {
                        "logical_path": "coverage.json",
                        "sha256": sha256_file(artifact),
                        "size_bytes": artifact.stat().st_size,
                    }
                },
            }
            validate_run_manifest(manifest, root)
            artifact.write_bytes(b"tampered\n")
            with self.assertRaisesRegex(MapillaryCoverageError, "integridad"):
                validate_run_manifest(manifest, root)


if __name__ == "__main__":
    unittest.main()
