"""Asociación geométrica cámara-celda explicable en EPSG:25830."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .crs import wgs84_to_epsg25830


class SpatialAssociationError(ValueError):
    pass


def circular_difference_degrees(left: float, right: float) -> float:
    if not math.isfinite(left) or not math.isfinite(right):
        raise SpatialAssociationError("ángulo no finito")
    return abs(((left - right + 180) % 360) - 180)


def bearing_degrees(origin_x: float, origin_y: float, target_x: float, target_y: float) -> float | None:
    dx, dy = target_x - origin_x, target_y - origin_y
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360


def square_metrics(camera_x: float, camera_y: float, center_x: float, center_y: float, cell_size_m: float = 50) -> dict[str, Any]:
    values = (camera_x, camera_y, center_x, center_y, cell_size_m)
    if any(not math.isfinite(value) for value in values) or cell_size_m <= 0:
        raise SpatialAssociationError("geometría no finita o celda inválida")
    half = cell_size_m / 2
    dx, dy = camera_x - center_x, camera_y - center_y
    inside_closed = abs(dx) <= half and abs(dy) <= half
    inside_interior = abs(dx) < half and abs(dy) < half
    on_boundary = inside_closed and not inside_interior
    outside_x, outside_y = max(abs(dx) - half, 0), max(abs(dy) - half, 0)
    nearest_x = min(max(camera_x, center_x - half), center_x + half)
    nearest_y = min(max(camera_y, center_y - half), center_y + half)
    return {"center_distance_m": math.hypot(dx, dy), "surface_distance_m": math.hypot(outside_x, outside_y), "nearest_cell_point": [nearest_x, nearest_y], "inside_closed": inside_closed, "inside_interior": inside_interior, "on_boundary": on_boundary, "position_relation": "interior" if inside_interior else "boundary" if on_boundary else "outside"}


def _cross(direction: tuple[float, float], point: tuple[float, float], camera: tuple[float, float]) -> float:
    vx, vy = point[0] - camera[0], point[1] - camera[1]
    return direction[0] * vy - direction[1] * vx


def _direction(angle_degrees: float) -> tuple[float, float]:
    angle = math.radians(angle_degrees)
    return math.sin(angle), math.cos(angle)


def _clip_polygon(polygon: list[tuple[float, float]], inside, intersection) -> list[tuple[float, float]]:
    if not polygon:
        return []
    output = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside != previous_inside:
            output.append(intersection(previous, current))
        if current_inside:
            output.append(current)
        previous, previous_inside = current, current_inside
    return output


def cone_square_intersection(camera_x: float, camera_y: float, heading_degrees: float, horizontal_fov_degrees: float, center_x: float, center_y: float, cell_size_m: float = 50) -> dict[str, Any]:
    if not 0 < horizontal_fov_degrees < 180:
        raise SpatialAssociationError("FOV perspectiva debe estar entre 0 y 180")
    heading = heading_degrees % 360
    left = _direction(heading - horizontal_fov_degrees / 2)
    right = _direction(heading + horizontal_fov_degrees / 2)
    camera = (camera_x, camera_y)
    half = cell_size_m / 2
    polygon = [(center_x - half, center_y - half), (center_x + half, center_y - half), (center_x + half, center_y + half), (center_x - half, center_y + half)]

    def clipping(direction, keep_nonpositive):
        def value(point): return _cross(direction, point, camera)
        def inside(point): return value(point) <= 1e-12 if keep_nonpositive else value(point) >= -1e-12
        def intersection(start, end):
            a, b = value(start), value(end)
            ratio = a / (a - b) if a != b else 0
            return start[0] + ratio * (end[0] - start[0]), start[1] + ratio * (end[1] - start[1])
        return inside, intersection

    inside, intersection = clipping(left, True)
    polygon = _clip_polygon(polygon, inside, intersection)
    inside, intersection = clipping(right, False)
    polygon = _clip_polygon(polygon, inside, intersection)
    area = abs(sum(polygon[index][0] * polygon[(index + 1) % len(polygon)][1] - polygon[(index + 1) % len(polygon)][0] * polygon[index][1] for index in range(len(polygon))) / 2) if len(polygon) >= 3 else 0.0
    return {"relation": "positive_area" if area > 1e-9 else "boundary_only" if polygon else "disjoint", "intersection_area_m2": area}


def classify_camera_candidate(camera: Mapping[str, Any], candidate: Mapping[str, Any], *, cell_size_m: float = 50, round_radius_m: float = 100, hypothetical_fov_degrees: float = 90, sensitivity_fovs: Sequence[float] = (60, 90, 120)) -> dict[str, Any]:
    camera_x, camera_y = wgs84_to_epsg25830(camera["latitude"], camera["longitude"])
    center_x = candidate.get("center_easting_m") or candidate.get("generation", {}).get("center_easting_m")
    center_y = candidate.get("center_northing_m") or candidate.get("generation", {}).get("center_northing_m")
    metrics = square_metrics(camera_x, camera_y, center_x, center_y, cell_size_m)
    bearing = bearing_degrees(camera_x, camera_y, center_x, center_y)
    heading = camera.get("orientation_degrees")
    panoramic = camera.get("camera_type") in {"equirectangular", "spherical", "cylindrical"}
    if panoramic:
        fov_basis, cone_relation, sensitivity = "omnidirectional_camera_type", "positive_area", {}
    elif heading is None:
        fov_basis, cone_relation, sensitivity = "unavailable", "unavailable", {}
    else:
        sensitivity = {str(fov): cone_square_intersection(camera_x, camera_y, heading, fov, center_x, center_y, cell_size_m)["relation"] for fov in sensitivity_fovs}
        fov_basis, cone_relation = "hypothetical_policy", sensitivity[str(hypothetical_fov_degrees)]
    angular = circular_difference_degrees(heading, bearing) if heading is not None and bearing is not None else None
    within_round = metrics["surface_distance_m"] <= round_radius_m
    if metrics["inside_closed"]:
        base_category = "camera_inside_candidate"
    elif not within_round:
        base_category = "not_eligible"
    elif cone_relation == "positive_area":
        base_category = "camera_outside_view_compatible"
    elif heading is None:
        base_category = "insufficient_orientation_metadata"
    elif cone_relation in {"disjoint", "boundary_only"}:
        base_category = "orientation_incompatible"
    else:
        base_category = "spatially_ambiguous"
    return {"camera_easting_m": camera_x, "camera_northing_m": camera_y, **metrics, "center_bearing_degrees": bearing, "heading_degrees": heading, "circular_difference_degrees": angular, "fov_basis": fov_basis, "horizontal_fov_degrees": hypothetical_fov_degrees if fov_basis == "hypothetical_policy" else 360 if panoramic else None, "cone_cell_relation": cone_relation, "fov_sensitivity": sensitivity, "round_radius_m": round_radius_m, "within_round": within_round, "base_category": base_category, "limitations": ["geometric_compatibility_not_visibility"] + (["hypothetical_fov_not_camera_metadata"] if fov_basis == "hypothetical_policy" else []) + (["camera_coordinate_accuracy_unknown"] if camera.get("horizontal_accuracy_m") is None else [])}


def annotate_ambiguity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_image = {}
    for row in rows:
        if row.get("within_round") and row.get("cone_cell_relation") == "positive_area":
            by_image.setdefault(row["global_record_id"], []).append(row["candidate_id"])
    output = []
    for row in rows:
        competing = sorted(set(by_image.get(row["global_record_id"], [])))
        ambiguous = len(competing) > 1
        output.append({**row, "competing_candidate_count": len(competing), "competing_candidate_ids": competing, "ambiguity_status": "spatially_ambiguous" if ambiguous else "spatially_unique" if competing else "no_compatible_cell", "classification": "spatially_ambiguous" if ambiguous and row["base_category"] == "camera_outside_view_compatible" else row["base_category"]})
    return output
