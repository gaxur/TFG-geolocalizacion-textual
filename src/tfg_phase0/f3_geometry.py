"""Normalización geométrica F3.3 conforme a D049, sin asociaciones."""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping

import numpy
import shapely
from shapely import LineString, Point, Polygon
from shapely.errors import GEOSException
from shapely.geometry.base import BaseGeometry

from .crs import wgs84_to_epsg25830
from .f3_contracts import F3_GEOS_VERSION, F3_NUMPY_VERSION, F3_SHAPELY_VERSION
from .f3_inputs import (
    D049RulesInput,
    OSMNodeInput,
    OSMRelationInput,
    OSMWayInput,
    VerifiedF3Inputs,
)


GEOMETRY_POLICY = "way_is_area-v1"


class F3GeometryError(ValueError):
    """Los inputs no permiten aplicar de forma segura el contrato geométrico."""


@dataclass(frozen=True)
class MetricBBox:
    min_easting_m: float
    min_northing_m: float
    max_easting_m: float
    max_northing_m: float


@dataclass(frozen=True)
class NormalizedOSMObject:
    osm_type: str
    osm_id: int
    osm_ref: str
    tags: tuple[tuple[str, str], ...]
    source_role: str
    geometry_role: str
    geometry_status: str
    geometry_reason: str | None
    classification_diagnostic: str | None
    is_closed: bool | None
    metric_bbox: MetricBBox | None
    geometry: BaseGeometry | None

    @property
    def associable(self) -> bool:
        return self.geometry_status == "valid"


@dataclass(frozen=True)
class NormalizedGeometryInventory:
    objects: tuple[NormalizedOSMObject, ...]
    relations: tuple[OSMRelationInput, ...]
    shapely_version: str
    geos_version: str
    geometry_policy: str


def geometry_software_versions() -> Mapping[str, str]:
    """Devuelve las versiones exactas que deberá registrar provenance."""
    return MappingProxyType({
        "numpy_version": numpy.__version__,
        "shapely_version": shapely.__version__,
        "geos_version": shapely.geos_version_string,
    })


def validate_geometry_runtime() -> None:
    """Rechaza un entorno distinto del preflight aprobado para F3.3."""
    if numpy.__version__ != F3_NUMPY_VERSION:
        raise F3GeometryError(
            f"NumPy {F3_NUMPY_VERSION} requerido; encontrado {numpy.__version__}"
        )
    if shapely.__version__ != F3_SHAPELY_VERSION:
        raise F3GeometryError(
            f"Shapely {F3_SHAPELY_VERSION} requerido; encontrado {shapely.__version__}"
        )
    if shapely.geos_version_string != F3_GEOS_VERSION:
        raise F3GeometryError(
            f"GEOS {F3_GEOS_VERSION} requerido; encontrado {shapely.geos_version_string}"
        )


def _metric_bbox(geometry: BaseGeometry) -> MetricBBox:
    bounds = geometry.bounds
    if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
        raise F3GeometryError("la geometría no tiene una bbox métrica finita")
    return MetricBBox(*bounds)


def _project_node(node: OSMNodeInput) -> tuple[float, float]:
    if not math.isfinite(node.latitude) or not math.isfinite(node.longitude):
        raise F3GeometryError(f"node/{node.osm_id} tiene coordenadas no finitas")
    projected = wgs84_to_epsg25830(node.latitude, node.longitude)
    if not all(math.isfinite(value) for value in projected):
        raise F3GeometryError(f"node/{node.osm_id} no se pudo proyectar")
    return projected


def _normalize_node(node: OSMNodeInput) -> NormalizedOSMObject:
    if node.source_role not in {"node_bbox", "added_way_node"}:
        raise F3GeometryError(f"node/{node.osm_id} tiene un source_role inválido")
    geometry = Point(_project_node(node))
    associable = node.source_role == "node_bbox"
    return NormalizedOSMObject(
        osm_type="node",
        osm_id=node.osm_id,
        osm_ref=f"node/{node.osm_id}",
        tags=node.tags,
        source_role=node.source_role,
        geometry_role="point",
        geometry_status="valid" if associable else "not_associable",
        geometry_reason=(
            None if associable else "added_way_node_direct_association_forbidden"
        ),
        classification_diagnostic=None,
        is_closed=None,
        metric_bbox=_metric_bbox(geometry),
        geometry=geometry,
    )


def _rule_votes(tags: Mapping[str, str], rules: D049RulesInput) -> tuple[bool, bool]:
    area_vote = False
    line_vote = False
    for key, policy, values in rules.rules:
        if key == "area" or key not in tags or tags[key] == "no":
            continue
        value = tags[key]
        if policy == "all":
            area_vote = True
        elif policy == "whitelist":
            if value in values:
                area_vote = True
            else:
                line_vote = True
        elif policy == "blacklist":
            if value in values:
                line_vote = True
            else:
                area_vote = True
        else:
            raise F3GeometryError(f"política D049 desconocida para {key!r}")
    return area_vote, line_vote


def _way_result(
    way: OSMWayInput,
    *,
    is_closed: bool,
    geometry_role: str,
    geometry_status: str,
    geometry_reason: str | None,
    classification_diagnostic: str | None = None,
    geometry: BaseGeometry | None,
) -> NormalizedOSMObject:
    return NormalizedOSMObject(
        osm_type="way",
        osm_id=way.osm_id,
        osm_ref=f"way/{way.osm_id}",
        tags=way.tags,
        source_role="way_bbox_intersection",
        geometry_role=geometry_role,
        geometry_status=geometry_status,
        geometry_reason=geometry_reason,
        classification_diagnostic=classification_diagnostic,
        is_closed=is_closed,
        metric_bbox=None if geometry is None else _metric_bbox(geometry),
        geometry=geometry,
    )


def _invalid_way(
    way: OSMWayInput, *, is_closed: bool, reason: str,
) -> NormalizedOSMObject:
    return _way_result(
        way,
        is_closed=is_closed,
        geometry_role="none",
        geometry_status="invalid",
        geometry_reason=reason,
        geometry=None,
    )


def _unknown_way(way: OSMWayInput, *, reason: str) -> NormalizedOSMObject:
    return _way_result(
        way,
        is_closed=True,
        geometry_role="none",
        geometry_status="not_associable",
        geometry_reason=reason,
        geometry=None,
    )


def _line_way(
    way: OSMWayInput,
    *,
    coordinates: tuple[tuple[float, float], ...],
    is_closed: bool,
    classification_diagnostic: str | None = None,
) -> NormalizedOSMObject:
    if len(coordinates) < 2 or len(set(coordinates)) < 2:
        return _invalid_way(
            way,
            is_closed=is_closed,
            reason="invalid_way_geometry_too_few_positions",
        )
    try:
        geometry = LineString(coordinates)
    except (TypeError, ValueError, GEOSException):
        return _invalid_way(
            way,
            is_closed=is_closed,
            reason="invalid_way_geometry_too_few_positions",
        )
    if geometry.is_empty or not geometry.is_valid:
        return _invalid_way(
            way,
            is_closed=is_closed,
            reason="invalid_way_geometry_too_few_positions",
        )
    return _way_result(
        way,
        is_closed=is_closed,
        geometry_role="line",
        geometry_status="valid",
        geometry_reason=None,
        classification_diagnostic=classification_diagnostic,
        geometry=geometry,
    )


def _area_way(
    way: OSMWayInput,
    *,
    coordinates: tuple[tuple[float, float], ...],
    is_closed: bool,
) -> NormalizedOSMObject:
    if not is_closed:
        return _invalid_way(way, is_closed=False, reason="invalid_area_open_way")
    try:
        geometry = Polygon(coordinates)
    except (TypeError, ValueError, GEOSException):
        return _invalid_way(
            way, is_closed=True, reason="invalid_area_invalid_polygon"
        )
    if geometry.is_empty:
        return _invalid_way(way, is_closed=True, reason="invalid_area_empty")
    if not math.isfinite(geometry.area) or geometry.area <= 0:
        return _invalid_way(way, is_closed=True, reason="invalid_area_non_positive")
    if not geometry.is_valid:
        return _invalid_way(
            way, is_closed=True, reason="invalid_area_invalid_polygon"
        )
    return _way_result(
        way,
        is_closed=True,
        geometry_role="area",
        geometry_status="valid",
        geometry_reason=None,
        geometry=geometry,
    )


def _normalize_way(
    way: OSMWayInput,
    *,
    nodes_by_id: Mapping[int, OSMNodeInput],
    rules: D049RulesInput,
) -> NormalizedOSMObject:
    refs = way.ordered_node_refs
    is_closed = len(refs) >= 2 and refs[0] == refs[-1]
    if len(refs) < 2:
        return _invalid_way(
            way,
            is_closed=is_closed,
            reason="invalid_way_geometry_too_few_positions",
        )
    try:
        nodes = tuple(nodes_by_id[ref] for ref in refs)
    except KeyError:
        return _invalid_way(
            way, is_closed=is_closed, reason="invalid_way_geometry_missing_node"
        )
    try:
        coordinates = tuple(_project_node(node) for node in nodes)
    except F3GeometryError:
        return _invalid_way(
            way,
            is_closed=is_closed,
            reason="invalid_way_geometry_non_finite_coordinate",
        )

    tags = dict(way.tags)
    if len(tags) != len(way.tags):
        raise F3GeometryError(f"way/{way.osm_id} contiene tags duplicados")
    area_value = tags.get("area")
    if area_value == "no":
        return _line_way(way, coordinates=coordinates, is_closed=is_closed)
    if area_value == "yes":
        return _area_way(way, coordinates=coordinates, is_closed=is_closed)
    if area_value is not None:
        if is_closed:
            return _unknown_way(
                way, reason="unknown_closed_way_unrecognized_area_value"
            )
        return _line_way(
            way,
            coordinates=coordinates,
            is_closed=False,
            classification_diagnostic="unrecognized_area_value",
        )
    if not is_closed:
        return _line_way(way, coordinates=coordinates, is_closed=False)

    area_vote, line_vote = _rule_votes(tags, rules)
    if area_vote and line_vote:
        return _unknown_way(way, reason="unknown_closed_way_conflict")
    if not area_vote and not line_vote:
        return _unknown_way(way, reason="unknown_closed_way_no_votes")
    if line_vote:
        return _line_way(way, coordinates=coordinates, is_closed=True)
    return _area_way(way, coordinates=coordinates, is_closed=True)


def normalize_osm_geometries(inputs: VerifiedF3Inputs) -> NormalizedGeometryInventory:
    """Normaliza los inputs F3.2 sin crear índices, asociaciones ni outputs."""
    validate_geometry_runtime()
    inventory = inputs.inventory
    nodes_by_id = {node.osm_id: node for node in inventory.nodes}
    if len(nodes_by_id) != len(inventory.nodes):
        raise F3GeometryError("el inventario contiene IDs de node duplicados")
    if len({way.osm_id for way in inventory.ways}) != len(inventory.ways):
        raise F3GeometryError("el inventario contiene IDs de way duplicados")
    objects = [
        _normalize_node(node)
        for node in sorted(inventory.nodes, key=lambda item: item.osm_id)
    ]
    objects.extend(
        _normalize_way(way, nodes_by_id=nodes_by_id, rules=inputs.rules)
        for way in sorted(inventory.ways, key=lambda item: item.osm_id)
    )
    versions = geometry_software_versions()
    return NormalizedGeometryInventory(
        objects=tuple(objects),
        relations=inventory.relations,
        shapely_version=versions["shapely_version"],
        geos_version=versions["geos_version"],
        geometry_policy=GEOMETRY_POLICY,
    )
