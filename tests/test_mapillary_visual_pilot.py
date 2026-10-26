import json
from email.message import Message
from pathlib import Path
import tempfile
import unittest

from src.tfg_phase0.mapillary_coverage import expand_bbox_projected, verify_expanded_bbox
from src.tfg_phase0.mapillary_coverage import MapillaryClient, MapillaryClientConfig, MapillaryCoverageError
from src.tfg_phase0.mapillary_visual_pilot import (
    MapillaryPilotError,
    annotation_template,
    image_dimensions,
    render_html,
    reject_ground_truth,
    select_candidate_images,
    select_pilot_candidates,
    summarize_annotations,
    validate_annotations,
    validate_image_plan,
    validate_vlm,
    vlm_template,
)
from tests.test_mapillary_coverage import BBOX, image, inventory_fixture, rankings_fixture


def coverage_fixture(rankings=None):
    rankings = rankings or realish_rankings()
    unique = {}
    for row in rankings["rows"]:
        for result in row["results"]:
            unique[result["candidate_id"]] = result
    rows = []
    for index, result in enumerate(sorted(unique.values(), key=lambda row: row["candidate_id"])):
        distance = 12.0 if index < 18 else 35.0 if index < 37 else 75.0 if index < 71 else None
        rows.append({"candidate_id": result["candidate_id"], "latitude": result["latitude"], "longitude": result["longitude"], "radii": {"100": {"nearest_image_distance_m": distance}}})
    return {"coverage_id": "fixture", "h11_h25_top10": {"unique_candidates": rows}}


def plan_fixture():
    return {
        "controls": [
            {"query_id": f"H{number}", "kind": "en_cartographic", "text": f"Description <{number}>", "language": "en"}
            for number in range(11, 26)
        ]
    }


def realish_rankings():
    rankings = rankings_fixture()
    for row in rankings["rows"]:
        for index, result in enumerate(row["results"]):
            number = int(result["candidate_id"].split("-")[-1])
            result.update({"rank": index + 1, "latitude": 40.414 + number * 0.00001, "longitude": -3.706 + number * 0.00001})
    return rankings


def make_inventory(rankings):
    from src.tfg_phase0.mapillary_coverage import MapillaryClient, MapillaryClientConfig
    from tests.test_mapillary_coverage import paged_opener
    unique = {}
    for row in rankings["rows"]:
        for result in row["results"]:
            unique[result["candidate_id"]] = result
    images = []
    for index, result in enumerate(sorted(unique.values(), key=lambda row: row["candidate_id"])):
        if index < 18:
            delta = 0.00010
        elif index < 37:
            delta = 0.00032
        elif index < 71:
            delta = 0.00065
        else:
            continue
        images.append(image(str(2000 + index), latitude=result["latitude"] + delta, longitude=result["longitude"], sequence=f"seq-{index}", computed_compass_angle=(index * 53) % 360))
    client = MapillaryClient("token", config=MapillaryClientConfig(max_retries=0), opener=paged_opener([{"data": images}], []))
    return client.inventory(BBOX, acquired_at_utc="2026-10-22T00:00:00Z")


class ExpansionTests(unittest.TestCase):
    def test_projected_expansion_contains_edges_and_corners(self):
        expansion = expand_bbox_projected(BBOX, 100)
        self.assertTrue(expansion["sufficiency_verified"])
        self.assertEqual(expansion["margin_m"], 100)
        self.assertLess(expansion["query_bbox_wgs84"]["west"], BBOX["west"])
        self.assertGreater(expansion["query_bbox_wgs84"]["north"], BBOX["north"])
        verify_expanded_bbox(expansion)

    def test_zero_margin_still_contains_original(self):
        expansion = expand_bbox_projected(BBOX, 0)
        verify_expanded_bbox(expansion)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.rankings = realish_rankings()
        self.inventory = make_inventory(self.rankings)

    def test_selection_is_deterministic_and_stratified(self):
        first = select_pilot_candidates(self.inventory, coverage_fixture(self.rankings), self.rankings, plan_fixture(), input_hashes={})
        second = select_pilot_candidates(self.inventory, coverage_fixture(self.rankings), self.rankings, plan_fixture(), input_hashes={})
        self.assertEqual(first, second)
        counts = {band: sum(row["distance_band"] == band for row in first["candidates"]) for band in ("lt25", "25_50", "50_100", "none")}
        self.assertEqual(counts, {"lt25": 3, "25_50": 3, "50_100": 2, "none": 2})
        self.assertFalse(first["policy"]["ground_truth_used"])
        self.assertNotIn("ground_truth_candidate_id", json.dumps(first))
        self.assertNotIn("distance_to_gt", json.dumps(first))

    def test_ground_truth_sentinel_is_rejected(self):
        coverage = coverage_fixture(self.rankings)
        coverage["ground_truth"] = {"latitude": 40.0, "longitude": -3.0}
        with self.assertRaisesRegex(MapillaryPilotError, "GT"):
            select_pilot_candidates(self.inventory, coverage, self.rankings, plan_fixture(), input_hashes={})
        with self.assertRaisesRegex(MapillaryPilotError, "reference"):
            reject_ground_truth({"candidate_id": "x", "reference": {"latitude": 40.0}})

    def test_image_plan_deduplicates_and_limits(self):
        selection = select_pilot_candidates(self.inventory, coverage_fixture(self.rankings), self.rankings, plan_fixture(), input_hashes={})
        image_plan = select_candidate_images(selection, self.inventory)
        ids = [image["image_id"] for row in image_plan["candidates"] for image in row["images"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLessEqual(len(ids), 24)
        self.assertTrue(all(len(row["images"]) <= 3 for row in image_plan["candidates"]))
        validate_image_plan(image_plan)

    def test_annotations_and_vlm_keep_absence_unverifiable(self):
        selection = select_pilot_candidates(self.inventory, coverage_fixture(self.rankings), self.rankings, plan_fixture(), input_hashes={})
        image_plan = select_candidate_images(selection, self.inventory)
        annotations = annotation_template(selection, image_plan)
        validate_annotations(annotations)
        no_image = [row for row in annotations["records"] if row["image_id"] is None]
        self.assertTrue(no_image)
        self.assertTrue(all(not row["contradictions"] for row in no_image))
        vlm = vlm_template(selection, image_plan)
        validate_vlm(vlm)
        self.assertFalse(vlm["reranking_performed"])
        summary = summarize_annotations(annotations, {"photos": []})
        self.assertFalse(summary["quantitative_results_available"])
        self.assertEqual(summary["reviewed_image_count"], 0)

    def test_html_escapes_text_and_marks_missing(self):
        selection = select_pilot_candidates(self.inventory, coverage_fixture(self.rankings), self.rankings, plan_fixture(), input_hashes={})
        image_plan = select_candidate_images(selection, self.inventory)
        annotations = annotation_template(selection, image_plan)
        photo_manifest = {"photos": [{"candidate_id": candidate["candidate_id"], "image_id": image["image_id"], "status": "failed", "logical_path": None, "distance_to_candidate_m": image["distance_to_candidate_m"], "orientation_degrees": image.get("orientation_degrees"), "angular_difference_degrees": image.get("angular_difference_degrees"), "captured_at": None, "downloaded_resolution": None, "quality_score": image.get("quality_score"), "creator": None, "creator_profile_url": None, "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "modifications": None, "attribution": None, "source_page_url": f"https://www.mapillary.com/app/?pKey={image['image_id']}"} for candidate in image_plan["candidates"] for image in candidate["images"]]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            render_html(selection, photo_manifest, annotations, output)
            html = output.read_text()
            self.assertIn("sin evidencia visual disponible", html)
            self.assertNotIn("Description <", html)
            self.assertIn("Description &lt;", html)
            self.assertEqual(html.count('class="utility"'), image_plan["planned_image_count"])
            self.assertIn("Exportar annotations.json", html)
            self.assertIn("annotation-data", html)


class ImageValidationTests(unittest.TestCase):
    def test_png_dimensions(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (20).to_bytes(4, "big") + (10).to_bytes(4, "big")
        self.assertEqual(image_dimensions(raw), ("image/png", 20, 10))

    def test_invalid_image_is_rejected(self):
        with self.assertRaises(MapillaryPilotError):
            image_dimensions(b"not an image")

    def test_annotation_absence_cannot_contradict(self):
        document = {"contract_version": "mapillary-visual-annotation-v1", "records": [{"review_status": "not_applicable", "utility": None, "image_id": None, "matches": [], "contradictions": ["x"], "unverifiable": [], "limitations": []}]}
        with self.assertRaisesRegex(MapillaryPilotError, "ausencia"):
            validate_annotations(document)

    def test_download_rejects_host_and_size(self):
        client = MapillaryClient("token", opener=lambda *args, **kwargs: None)
        with self.assertRaisesRegex(MapillaryCoverageError, "host"):
            client.download_bytes("https://example.com/image.jpg")

        class Response:
            def __init__(self):
                self.headers = Message()
                self.headers["Content-Length"] = "1000"
                self.headers["Content-Type"] = "image/jpeg"
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, count): return b"x" * min(count, 1000)

        client = MapillaryClient("token", config=MapillaryClientConfig(max_retries=0), opener=lambda *args, **kwargs: Response())
        with self.assertRaisesRegex(Exception, "límite"):
            client.download_bytes("https://scontent.xx.fbcdn.net/image.jpg", max_bytes=100)


if __name__ == "__main__":
    unittest.main()
