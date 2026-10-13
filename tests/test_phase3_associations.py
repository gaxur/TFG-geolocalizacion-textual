import unittest
from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shapely import LineString, Point, Polygon, STRtree

from src.tfg_phase0.f3_associations import (
    F3AssociationError,
    associate_candidates_with_index,
    associate_candidates_with_osm,
    build_candidate_cell,
    build_osm_spatial_index,
)
from src.tfg_phase0.f3_geometry import (
    GEOMETRY_POLICY,
    NormalizedGeometryInventory,
    NormalizedOSMObject,
)
from src.tfg_phase0.f3_inputs import CandidateInput
from src.tfg_phase0.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]


def candidate(candidate_id, x, y):
    return CandidateInput(candidate_id, 0.0, 0.0, x, y, 0, 0, ())


def catalog(*candidates, cell_size=10, spacing=10):
    return SimpleNamespace(
        candidates=tuple(candidates),
        cell_size_m=cell_size,
        spacing_m=spacing,
        projected_crs="EPSG:25830",
    )


def osm_object(osm_id, geometry, *, osm_type="way", role=None, status="valid", reason=None):
    geometry_role = role or {
        "Point": "point", "LineString": "line", "Polygon": "area",
    }.get(geometry.geom_type if geometry is not None else "", "none")
    return NormalizedOSMObject(
        osm_type=osm_type,
        osm_id=osm_id,
        osm_ref=f"{osm_type}/{osm_id}",
        tags=(),
        source_role="node_bbox" if osm_type == "node" else "way_bbox_intersection",
        geometry_role=geometry_role,
        geometry_status=status,
        geometry_reason=reason,
        classification_diagnostic=None,
        is_closed=None if osm_type == "node" else False,
        metric_bbox=None,
        geometry=geometry,
    )


def inventory(*objects):
    return NormalizedGeometryInventory(
        objects=tuple(objects),
        relations=(),
        shapely_version="2.1.2",
        geos_version="3.13.1",
        geometry_policy=GEOMETRY_POLICY,
    )


def exhaustive(catalog_input, normalized):
    rows = []
    objects = sorted(
        (item for item in normalized.objects if item.associable),
        key=lambda item: (0 if item.osm_type == "node" else 1, item.osm_id),
    )
    for item_candidate in sorted(catalog_input.candidates, key=lambda item: item.candidate_id):
        cell = build_candidate_cell(item_candidate, catalog_input.cell_size_m)
        for item in objects:
            geometry = item.geometry
            if geometry is not None and geometry.intersects(cell.geometry):
                touches = bool(geometry.touches(cell.geometry))
                distance = round(cell.center.distance(geometry), 6)
                rows.append((
                    item_candidate.candidate_id, item.osm_type, item.osm_id,
                    True, bool(geometry.contains(cell.geometry)),
                    bool(geometry.within(cell.geometry)), bool(geometry.crosses(cell.geometry)),
                    touches, bool(geometry.overlaps(cell.geometry)), touches,
                    0.0 if distance == 0 else distance,
                ))
    return tuple(rows)


def compact(rows):
    return tuple((
        row.candidate_id, row.osm_type, row.osm_id, row.intersects,
        row.contains, row.within, row.crosses, row.touches, row.overlaps,
        row.boundary_contact_only, row.center_distance_m,
    ) for row in rows)


class Phase3AssociationTests(unittest.TestCase):
    def setUp(self):
        self.candidate = candidate("C01", 100.0, 200.0)

    def test_candidate_cell_uses_metric_center_size_and_exact_bounds(self):
        cell = build_candidate_cell(self.candidate, 10)
        self.assertEqual(cell.center.coords[0], (100.0, 200.0))
        self.assertEqual(cell.geometry.bounds, (95.0, 195.0, 105.0, 205.0))
        self.assertEqual(cell.geometry.area, 100.0)
        self.assertTrue(cell.geometry.is_valid)

    def test_candidate_cell_ignores_wgs84_ring_and_spacing(self):
        changed = replace(self.candidate, cell_ring_wgs84=((999.0, 999.0),))
        result = associate_candidates_with_osm(
            catalog(changed, cell_size=10, spacing=99),
            inventory(osm_object(1, Point(100, 200), osm_type="node")),
        )
        self.assertEqual(len(result.associations), 1)

    def test_points_inside_outside_and_on_boundary(self):
        normalized = inventory(
            osm_object(1, Point(100, 200), osm_type="node"),
            osm_object(2, Point(105, 200), osm_type="node"),
            osm_object(3, Point(106, 200), osm_type="node"),
            osm_object(4, Point(105, 205), osm_type="node"),
        )
        rows = associate_candidates_with_osm(catalog(self.candidate), normalized).associations
        self.assertEqual(tuple(row.osm_id for row in rows), (1, 2, 4))
        self.assertTrue(rows[0].within)
        self.assertFalse(rows[0].touches)
        self.assertEqual(rows[0].center_distance_m, 0.0)
        self.assertFalse(rows[1].within)
        self.assertTrue(rows[1].touches)
        self.assertTrue(rows[1].boundary_contact_only)
        self.assertEqual(rows[1].center_distance_m, 5.0)
        self.assertTrue(rows[2].touches)

    def test_no_tolerance_is_applied_outside_boundary(self):
        just_outside = math.nextafter(105.0, math.inf)
        result = associate_candidates_with_osm(
            catalog(self.candidate),
            inventory(osm_object(1, Point(just_outside, 200), osm_type="node")),
        )
        self.assertEqual(result.associations, ())

    def test_line_predicates_and_distance_use_complete_geometry(self):
        normalized = inventory(
            osm_object(10, LineString(((90, 200), (110, 200)))),
            osm_object(11, LineString(((90, 205), (95, 205)))),
            osm_object(12, LineString(((95, 204), (95, 206)))),
            osm_object(13, LineString(((106, 200), (110, 200)))),
            osm_object(14, LineString(((94, 204.5), (96, 206.5)))),
        )
        rows = associate_candidates_with_osm(catalog(self.candidate), normalized).associations
        by_id = {row.osm_id: row for row in rows}
        self.assertEqual(set(by_id), {10, 11, 12})
        self.assertTrue(by_id[10].crosses)
        self.assertEqual(by_id[10].center_distance_m, 0.0)
        self.assertTrue(by_id[11].touches)
        self.assertEqual(by_id[11].center_distance_m, 7.071068)
        self.assertTrue(by_id[12].touches)

    def test_polygon_predicates_and_boundary_contacts(self):
        normalized = inventory(
            osm_object(20, Polygon(((99, 199), (101, 199), (101, 201), (99, 201)))),
            osm_object(21, Polygon(((90, 190), (110, 190), (110, 210), (90, 210)))),
            osm_object(22, Polygon(((103, 203), (108, 203), (108, 208), (103, 208)))),
            osm_object(23, Polygon(((105, 199), (108, 199), (108, 201), (105, 201)))),
            osm_object(24, Polygon(((106, 206), (108, 206), (108, 208), (106, 208)))),
        )
        rows = associate_candidates_with_osm(catalog(self.candidate), normalized).associations
        by_id = {row.osm_id: row for row in rows}
        self.assertEqual(set(by_id), {20, 21, 22, 23})
        self.assertTrue(by_id[20].within)
        self.assertTrue(by_id[21].contains)
        self.assertTrue(by_id[22].overlaps)
        self.assertTrue(by_id[23].touches)

    def test_excludes_non_associable_invalid_missing_and_relations(self):
        allowed = osm_object(1, Point(100, 200), osm_type="node")
        added = replace(
            osm_object(2, Point(100, 200), osm_type="node"),
            source_role="added_way_node", geometry_status="not_associable",
            geometry_reason="added_way_node_direct_association_forbidden",
        )
        unknown = osm_object(
            3, None, role="none", status="not_associable",
            reason="unknown_closed_way_no_votes",
        )
        invalid = osm_object(
            4, None, role="none", status="invalid",
            reason="invalid_way_geometry_too_few_positions",
        )
        normalized = replace(inventory(allowed, added, unknown, invalid), relations=(object(),))
        result = associate_candidates_with_osm(catalog(self.candidate), normalized)
        self.assertEqual(result.indexed_object_count, 1)
        self.assertEqual(tuple(row.osm_id for row in result.associations), (1,))

    def test_rejects_incoherent_associable_geometry(self):
        inconsistent = osm_object(1, None, role="line", status="valid")
        with self.assertRaises(F3AssociationError):
            build_osm_spatial_index(inventory(inconsistent))
        added_marked_valid = replace(
            osm_object(2, Point(100, 200), osm_type="node"),
            source_role="added_way_node",
        )
        with self.assertRaises(F3AssociationError):
            build_osm_spatial_index(inventory(added_marked_valid))
        wrong_geometry_type = osm_object(
            3, Polygon(((99, 199), (101, 199), (101, 201), (99, 201))),
            role="line",
        )
        with self.assertRaises(F3AssociationError):
            build_osm_spatial_index(inventory(wrong_geometry_type))

    def test_rejects_invalid_identity_versions_and_misaligned_index(self):
        invalid_id = replace(osm_object(1, Point(100, 200), osm_type="node"), osm_id=0, osm_ref="node/0")
        with self.assertRaises(F3AssociationError):
            build_osm_spatial_index(inventory(invalid_id))

        wrong_version = replace(inventory(), shapely_version="0.0.0")
        with self.assertRaises(F3AssociationError):
            build_osm_spatial_index(wrong_version)

        first = osm_object(1, Point(100, 200), osm_type="node")
        second = osm_object(2, Point(101, 200), osm_type="node")
        valid_index = build_osm_spatial_index(inventory(first, second))
        misaligned = replace(valid_index, tree=STRtree((second.geometry, first.geometry)))
        with self.assertRaises(F3AssociationError):
            associate_candidates_with_index(catalog(self.candidate), misaligned)

        invalid_candidate = replace(self.candidate, candidate_id="")
        with self.assertRaises(F3AssociationError):
            associate_candidates_with_index(catalog(invalid_candidate), valid_index)

    def test_schema_compatible_rows_and_rounding(self):
        line = LineString(((100.1234567, 199), (100.1234567, 201)))
        row = associate_candidates_with_osm(
            catalog(self.candidate), inventory(osm_object(10, line))
        ).associations[0]
        document = dict(row.__dict__)
        validate_document(document, "f3_association")
        self.assertEqual(row.center_distance_m, 0.123457)

    def test_determinism_duplicates_and_exhaustive_baseline(self):
        candidates = (
            candidate("C02", 110, 200),
            candidate("C01", 100, 200),
            candidate("C03", 130, 200),
        )
        objects = (
            osm_object(20, Polygon(((104, 198), (111, 198), (111, 202), (104, 202)))),
            osm_object(2, Point(100, 200), osm_type="node"),
            osm_object(10, LineString(((95, 200), (115, 200)))),
            osm_object(1, Point(100, 200), osm_type="node"),
        )
        first_catalog = catalog(*candidates)
        first_inventory = inventory(*objects)
        first = associate_candidates_with_osm(first_catalog, first_inventory)
        second = associate_candidates_with_osm(
            catalog(*reversed(candidates)), inventory(*reversed(objects))
        )
        self.assertEqual(first.associations, second.associations)
        self.assertEqual(compact(first.associations), exhaustive(first_catalog, first_inventory))
        for row in first.associations:
            validate_document(dict(row.__dict__), "f3_association")
        self.assertEqual(len(first.associations), len({
            (row.candidate_id, row.osm_type, row.osm_id) for row in first.associations
        }))
        self.assertEqual(
            tuple((row.candidate_id, row.osm_type, row.osm_id) for row in first.associations),
            tuple(sorted(
                ((row.candidate_id, row.osm_type, row.osm_id) for row in first.associations),
                key=lambda value: (value[0], 0 if value[1] == "node" else 1, value[2]),
            )),
        )

    def test_distinct_objects_with_identical_geometry_are_preserved(self):
        geometry = Point(100, 200)
        result = associate_candidates_with_osm(
            catalog(self.candidate),
            inventory(
                osm_object(1, geometry, osm_type="node"),
                osm_object(2, Point(100, 200), osm_type="node"),
            ),
        )
        self.assertEqual(tuple(row.osm_id for row in result.associations), (1, 2))

    def test_strtree_indices_are_deduplicated_and_exactly_filtered(self):
        inside = osm_object(1, Point(100, 200), osm_type="node")
        outside = osm_object(2, Point(120, 200), osm_type="node")
        index = build_osm_spatial_index(inventory(inside, outside))
        with patch.object(type(index.tree), "query", return_value=[1, 0, 0]):
            result = associate_candidates_with_index(catalog(self.candidate), index)
        self.assertEqual(tuple(row.osm_id for row in result.associations), (1,))

    def test_empty_index_and_invalid_catalog_are_handled(self):
        empty = associate_candidates_with_osm(catalog(self.candidate), inventory())
        self.assertEqual(empty.associations, ())
        self.assertEqual(empty.indexed_object_count, 0)
        empty_catalog = associate_candidates_with_osm(
            catalog(), inventory(osm_object(1, Point(100, 200), osm_type="node"))
        )
        self.assertEqual(empty_catalog.associations, ())
        self.assertEqual(empty_catalog.candidate_count, 0)
        self.assertEqual(empty_catalog.indexed_object_count, 1)
        with self.assertRaises(F3AssociationError):
            associate_candidates_with_osm(
                SimpleNamespace(candidates=(self.candidate,), cell_size_m=10, projected_crs="EPSG:4326"),
                inventory(),
            )


if __name__ == "__main__":
    unittest.main()
