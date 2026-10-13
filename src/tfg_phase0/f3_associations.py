"""Asociaciones espaciales F3.4 en memoria conforme a D050."""

from __future__ import annotations

from dataclasses import dataclass
import math

from shapely import Point, Polygon, STRtree
from shapely.geometry.base import BaseGeometry

from .f3_geometry import (
    GEOMETRY_POLICY,
    NormalizedGeometryInventory,
    NormalizedOSMObject,
    geometry_software_versions,
    validate_geometry_runtime,
)
from .f3_inputs import CandidateInput, CatalogInput


class F3AssociationError(ValueError):
    """Los inputs no permiten construir asociaciones F3.4 seguras."""


@dataclass(frozen=True)
class CandidateCell:
    candidate_id: str
    center: Point
    geometry: Polygon


@dataclass(frozen=True)
class CandidateOSMAssociation:
    candidate_id: str
    osm_type: str
    osm_id: int
    osm_ref: str
    geometry_role: str
    intersects: bool
    contains: bool
    within: bool
    crosses: bool
    touches: bool
    overlaps: bool
    boundary_contact_only: bool
    center_distance_m: float


@dataclass(frozen=True)
class OSMSpatialIndex:
    objects: tuple[NormalizedOSMObject, ...]
    tree: STRtree


@dataclass(frozen=True)
class CandidateAssociationInventory:
    associations: tuple[CandidateOSMAssociation, ...]
    candidate_count: int
    indexed_object_count: int


def build_candidate_cell(candidate: CandidateInput, cell_size_m: int) -> CandidateCell:
    """Reconstruye una celda F1 desde su centro autoritativo en EPSG:25830."""
    if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id:
        raise F3AssociationError("candidate_id debe ser texto no vacío")
    if isinstance(cell_size_m, bool) or not isinstance(cell_size_m, int) or cell_size_m <= 0:
        raise F3AssociationError("cell_size_m debe ser un entero positivo")
    easting = candidate.center_easting_m
    northing = candidate.center_northing_m
    if not math.isfinite(easting) or not math.isfinite(northing):
        raise F3AssociationError(f"{candidate.candidate_id} tiene un centro no finito")
    half = cell_size_m / 2.0
    geometry = Polygon((
        (easting - half, northing - half),
        (easting + half, northing - half),
        (easting + half, northing + half),
        (easting - half, northing + half),
        (easting - half, northing - half),
    ))
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise F3AssociationError(f"{candidate.candidate_id} produce una celda inválida")
    return CandidateCell(
        candidate_id=candidate.candidate_id,
        center=Point(easting, northing),
        geometry=geometry,
    )


def build_osm_spatial_index(
    normalized: NormalizedGeometryInventory,
) -> OSMSpatialIndex:
    """Indexa solo geometrías OSM asociables y conserva su posición estable."""
    validate_geometry_runtime()
    if normalized.geometry_policy != GEOMETRY_POLICY:
        raise F3AssociationError("la política geométrica normalizada no es compatible")
    versions = geometry_software_versions()
    if (
        normalized.shapely_version != versions["shapely_version"]
        or normalized.geos_version != versions["geos_version"]
    ):
        raise F3AssociationError("las versiones del inventario no coinciden con el runtime")
    objects = []
    seen = set()
    for item in normalized.objects:
        key = (item.osm_type, item.osm_id)
        if key in seen:
            raise F3AssociationError(f"objeto OSM duplicado: {item.osm_ref}")
        seen.add(key)
        if not item.associable:
            continue
        geometry = item.geometry
        if (
            isinstance(item.osm_id, bool)
            or not isinstance(item.osm_id, int)
            or item.osm_id <= 0
            or item.osm_ref != f"{item.osm_type}/{item.osm_id}"
            or item.source_role == "added_way_node"
            or geometry is None
            or geometry.is_empty
            or not geometry.is_valid
            or item.geometry_role not in {"point", "line", "area"}
            or item.osm_type not in {"node", "way"}
            or (
                item.osm_type == "node"
                and item.source_role != "node_bbox"
            )
            or (
                item.osm_type == "way"
                and item.source_role != "way_bbox_intersection"
            )
            or (item.osm_type == "node" and item.geometry_role != "point")
            or (item.osm_type == "way" and item.geometry_role == "point")
            or geometry.geom_type != {
                "point": "Point",
                "line": "LineString",
                "area": "Polygon",
            }[item.geometry_role]
            or len(geometry.bounds) != 4
            or not all(math.isfinite(value) for value in geometry.bounds)
        ):
            raise F3AssociationError(
                f"objeto asociable con geometría incoherente: {item.osm_ref}"
            )
        objects.append(item)
    objects.sort(key=lambda item: (0 if item.osm_type == "node" else 1, item.osm_id))
    return OSMSpatialIndex(
        objects=tuple(objects),
        tree=STRtree(tuple(item.geometry for item in objects)),
    )


def _rounded_distance(center: Point, geometry: BaseGeometry) -> float:
    distance = center.distance(geometry)
    if not math.isfinite(distance) or distance < 0:
        raise F3AssociationError("GEOS produjo una distancia no válida")
    rounded = round(distance, 6)
    return 0.0 if rounded == 0 else rounded


def _association(
    cell: CandidateCell, item: NormalizedOSMObject
) -> CandidateOSMAssociation | None:
    geometry = item.geometry
    if geometry is None or not geometry.intersects(cell.geometry):
        return None
    touches = bool(geometry.touches(cell.geometry))
    return CandidateOSMAssociation(
        candidate_id=cell.candidate_id,
        osm_type=item.osm_type,
        osm_id=item.osm_id,
        osm_ref=item.osm_ref,
        geometry_role=item.geometry_role,
        intersects=True,
        contains=bool(geometry.contains(cell.geometry)),
        within=bool(geometry.within(cell.geometry)),
        crosses=bool(geometry.crosses(cell.geometry)),
        touches=touches,
        overlaps=bool(geometry.overlaps(cell.geometry)),
        boundary_contact_only=touches,
        center_distance_m=_rounded_distance(cell.center, geometry),
    )


def associate_candidates_with_index(
    catalog: CatalogInput, index: OSMSpatialIndex
) -> CandidateAssociationInventory:
    """Consulta un índice F3.4 y devuelve asociaciones en orden canónico."""
    validate_geometry_runtime()
    if catalog.projected_crs != "EPSG:25830":
        raise F3AssociationError("F3.4 requiere un catálogo en EPSG:25830")
    indexed_geometries = index.tree.geometries
    if len(indexed_geometries) != len(index.objects) or any(
        item.geometry is None or indexed_geometries[position].wkb != item.geometry.wkb
        for position, item in enumerate(index.objects)
    ):
        raise F3AssociationError("STRtree y objetos indexados no corresponden")
    candidate_ids = [candidate.candidate_id for candidate in catalog.candidates]
    if any(not isinstance(value, str) or not value for value in candidate_ids):
        raise F3AssociationError("el catálogo contiene candidate_id inválidos")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise F3AssociationError("el catálogo contiene candidate_id duplicados")

    associations = []
    for candidate in sorted(catalog.candidates, key=lambda item: item.candidate_id):
        cell = build_candidate_cell(candidate, catalog.cell_size_m)
        indices = {int(index_value) for index_value in index.tree.query(cell.geometry)}
        if any(value < 0 or value >= len(index.objects) for value in indices):
            raise F3AssociationError("STRtree devolvió un índice fuera de rango")
        objects = sorted(
            (index.objects[value] for value in indices),
            key=lambda item: (0 if item.osm_type == "node" else 1, item.osm_id),
        )
        for item in objects:
            association = _association(cell, item)
            if association is not None:
                associations.append(association)
    return CandidateAssociationInventory(
        associations=tuple(associations),
        candidate_count=len(catalog.candidates),
        indexed_object_count=len(index.objects),
    )


def associate_candidates_with_osm(
    catalog: CatalogInput, normalized: NormalizedGeometryInventory
) -> CandidateAssociationInventory:
    """Construye el STRtree y asocia candidatos con objetos OSM en memoria."""
    return associate_candidates_with_index(catalog, build_osm_spatial_index(normalized))
