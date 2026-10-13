"""Contexto parcial de relations F3.5, sin geometría ni serialización."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .f3_associations import CandidateAssociationInventory
from .f3_contracts import F3_INVALID_REASONS, F3_NOT_ASSOCIABLE_REASONS
from .f3_geometry import (
    GEOMETRY_POLICY,
    MetricBBox,
    NormalizedGeometryInventory,
    geometry_software_versions,
)
from .f3_inputs import OSMRelationInput, VerifiedF3Inputs


class F3RelationError(ValueError):
    """Los inventarios F3 no permiten propagar relations de forma segura."""


@dataclass(frozen=True)
class RelationMemberCounts:
    node: int
    way: int
    relation: int


@dataclass(frozen=True)
class AssociatedRelationMember:
    member_type: str
    member_id: int
    member_ref: str
    role: str
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class RelationContext:
    relation_id: int
    relation_ref: str
    tags: tuple[tuple[str, str], ...]
    closure_status: str
    member_count: int
    present_member_counts: RelationMemberCounts
    unresolved_member_counts: RelationMemberCounts
    associated_members: tuple[AssociatedRelationMember, ...]


@dataclass(frozen=True)
class RelationContextInventory:
    relations: tuple[RelationContext, ...]
    relations_input: int
    relations_emitted: int
    relations_without_associated_members: int
    present_member_counts: RelationMemberCounts
    unresolved_member_counts: RelationMemberCounts
    duplicate_members_grouped: int


def _counts(values: dict[str, int]) -> RelationMemberCounts:
    return RelationMemberCounts(
        node=values["node"],
        way=values["way"],
        relation=values["relation"],
    )


def _relation_index(
    relations: tuple[OSMRelationInput, ...], label: str
) -> dict[int, OSMRelationInput]:
    result = {}
    for relation in relations:
        if (
            isinstance(relation.osm_id, bool)
            or not isinstance(relation.osm_id, int)
            or relation.osm_id <= 0
            or relation.osm_id in result
        ):
            raise F3RelationError(f"{label} contiene IDs de relation inválidos o duplicados")
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in relation.tags
        ):
            raise F3RelationError(f"relation/{relation.osm_id} contiene tags inválidos")
        result[relation.osm_id] = relation
    return result


def _source_object_index(inputs: VerifiedF3Inputs) -> dict[tuple[str, int], object]:
    result = {}
    for osm_type, objects in (
        ("node", inputs.inventory.nodes),
        ("way", inputs.inventory.ways),
    ):
        for item in objects:
            if (
                isinstance(item.osm_id, bool)
                or not isinstance(item.osm_id, int)
                or item.osm_id <= 0
                or (osm_type, item.osm_id) in result
            ):
                raise F3RelationError("F3.2 contiene identidades OSM inválidas o duplicadas")
            result[(osm_type, item.osm_id)] = item
    return result


def _normalized_state_is_coherent(item: object) -> bool:
    geometry = item.geometry
    valid_geometry = geometry is not None and not geometry.is_empty and geometry.is_valid
    expected_bbox = MetricBBox(*geometry.bounds) if geometry is not None else None
    if item.metric_bbox != expected_bbox:
        return False
    if item.osm_type == "node":
        return (
            item.is_closed is None
            and item.classification_diagnostic is None
            and item.geometry_role == "point"
            and valid_geometry
            and geometry.geom_type == "Point"
            and (
                (
                    item.source_role == "node_bbox"
                    and item.geometry_status == "valid"
                    and item.geometry_reason is None
                )
                or (
                    item.source_role == "added_way_node"
                    and item.geometry_status == "not_associable"
                    and item.geometry_reason
                    == "added_way_node_direct_association_forbidden"
                )
            )
        )
    if item.osm_type != "way" or item.source_role != "way_bbox_intersection":
        return False
    if item.geometry_status == "valid":
        return (
            item.geometry_reason is None
            and item.geometry_role in {"line", "area"}
            and isinstance(item.is_closed, bool)
            and (item.geometry_role != "area" or item.is_closed is True)
            and (
                item.classification_diagnostic is None
                or (
                    item.geometry_role == "line"
                    and item.is_closed is False
                    and item.classification_diagnostic == "unrecognized_area_value"
                )
            )
            and valid_geometry
            and geometry.geom_type
            == {"line": "LineString", "area": "Polygon"}[item.geometry_role]
        )
    if item.geometry_status == "not_associable":
        return (
            item.geometry_reason in F3_NOT_ASSOCIABLE_REASONS[1:]
            and item.classification_diagnostic is None
            and item.geometry_role == "none"
            and item.is_closed is True
            and geometry is None
        )
    if item.geometry_status == "invalid":
        area_closed_reasons = {
            "invalid_area_empty",
            "invalid_area_non_positive",
            "invalid_area_invalid_polygon",
        }
        return (
            item.geometry_reason in F3_INVALID_REASONS
            and item.classification_diagnostic is None
            and item.geometry_role == "none"
            and isinstance(item.is_closed, bool)
            and geometry is None
            and (
                item.geometry_reason != "invalid_area_open_way"
                or item.is_closed is False
            )
            and (
                item.geometry_reason not in area_closed_reasons
                or item.is_closed is True
            )
        )
    return False


def _validate_inputs(
    inputs: VerifiedF3Inputs,
    normalized: NormalizedGeometryInventory,
    associations: CandidateAssociationInventory,
) -> dict[tuple[str, int], set[str]]:
    candidate_ids = [item.candidate_id for item in inputs.catalog.candidates]
    if any(not isinstance(value, str) or not value for value in candidate_ids):
        raise F3RelationError("el catálogo contiene candidate_id inválidos")
    candidates = set(candidate_ids)
    if len(candidates) != len(inputs.catalog.candidates):
        raise F3RelationError("el catálogo contiene candidate_id duplicados")
    if associations.candidate_count != len(candidates):
        raise F3RelationError("candidate_count de F3.4 no coincide con el catálogo")

    versions = geometry_software_versions()
    if (
        normalized.geometry_policy != GEOMETRY_POLICY
        or normalized.shapely_version != versions["shapely_version"]
        or normalized.geos_version != versions["geos_version"]
    ):
        raise F3RelationError("el inventario F3.3 no coincide con el runtime y la política")

    source_objects = _source_object_index(inputs)
    normalized_objects = {}
    for item in normalized.objects:
        if (
            item.osm_type not in {"node", "way"}
            or isinstance(item.osm_id, bool)
            or not isinstance(item.osm_id, int)
            or item.osm_id <= 0
        ):
            raise F3RelationError("F3.3 contiene una identidad OSM inválida")
        key = (item.osm_type, item.osm_id)
        if key in normalized_objects:
            raise F3RelationError("F3.3 contiene identidades OSM duplicadas")
        normalized_objects[key] = item
    if set(normalized_objects) != set(source_objects):
        raise F3RelationError("los objetos F3.2 y F3.3 no coinciden")
    for key, item in normalized_objects.items():
        source = source_objects[key]
        expected_source_role = (
            source.source_role if item.osm_type == "node" else "way_bbox_intersection"
        )
        if (
            item.osm_ref != f"{item.osm_type}/{item.osm_id}"
            or item.tags != source.tags
            or item.source_role != expected_source_role
            or not _normalized_state_is_coherent(item)
        ):
            raise F3RelationError(f"F3.3 no conserva el objeto {item.osm_ref}")

    input_relations = _relation_index(inputs.inventory.relations, "F3.2")
    normalized_relations = _relation_index(normalized.relations, "F3.3")
    if input_relations != normalized_relations:
        raise F3RelationError("las relations F3.2 y F3.3 no coinciden")

    present_ids = {
        "node": {item.osm_id for item in inputs.inventory.nodes},
        "way": {item.osm_id for item in inputs.inventory.ways},
        "relation": set(input_relations),
    }
    for relation in inputs.inventory.relations:
        for member in relation.members:
            if (
                member.member_type not in present_ids
                or isinstance(member.ref, bool)
                or not isinstance(member.ref, int)
                or member.ref <= 0
                or not isinstance(member.role, str)
                or not isinstance(member.present, bool)
            ):
                raise F3RelationError(f"relation/{relation.osm_id} contiene un member inválido")
            if member.present != (member.ref in present_ids[member.member_type]):
                raise F3RelationError(
                    f"relation/{relation.osm_id} declara una presencia de member incoherente"
                )

    expected_indexed = sum(item.associable for item in normalized.objects)
    if associations.indexed_object_count != expected_indexed:
        raise F3RelationError("indexed_object_count de F3.4 no coincide con F3.3")

    candidates_by_object: dict[tuple[str, int], set[str]] = {}
    seen_associations = set()
    for association in associations.associations:
        if (
            association.osm_type not in {"node", "way"}
            or isinstance(association.osm_id, bool)
            or not isinstance(association.osm_id, int)
            or association.osm_id <= 0
        ):
            raise F3RelationError("F3.4 contiene una identidad OSM inválida")
        key = (association.osm_type, association.osm_id)
        association_key = (association.candidate_id, *key)
        if association_key in seen_associations:
            raise F3RelationError("F3.4 contiene una asociación duplicada")
        seen_associations.add(association_key)
        if association.candidate_id not in candidates:
            raise F3RelationError("F3.4 referencia un candidate_id inexistente")
        item = normalized_objects.get(key)
        if item is None:
            raise F3RelationError("F3.4 referencia un objeto OSM inexistente")
        if not item.associable:
            raise F3RelationError("F3.4 referencia un objeto OSM no asociable")
        if (
            association.osm_ref != item.osm_ref
            or association.geometry_role != item.geometry_role
            or association.intersects is not True
            or any(
                not isinstance(value, bool)
                for value in (
                    association.contains,
                    association.within,
                    association.crosses,
                    association.touches,
                    association.overlaps,
                    association.boundary_contact_only,
                )
            )
            or association.boundary_contact_only != association.touches
            or isinstance(association.center_distance_m, bool)
            or not isinstance(association.center_distance_m, (int, float))
            or not math.isfinite(association.center_distance_m)
            or association.center_distance_m < 0
        ):
            raise F3RelationError("F3.4 contiene una asociación incoherente")
        candidates_by_object.setdefault(key, set()).add(association.candidate_id)
    return candidates_by_object


def build_relation_context(
    inputs: VerifiedF3Inputs,
    normalized: NormalizedGeometryInventory,
    associations: CandidateAssociationInventory,
) -> RelationContextInventory:
    """Propaga candidatos a relations padre directas de members node/way."""
    candidates_by_object = _validate_inputs(inputs, normalized, associations)
    present_totals = {"node": 0, "way": 0, "relation": 0}
    unresolved_totals = {"node": 0, "way": 0, "relation": 0}
    rows = []
    duplicate_members_grouped = 0

    for relation in sorted(inputs.inventory.relations, key=lambda item: item.osm_id):
        tags = dict(relation.tags)
        if len(tags) != len(relation.tags) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in relation.tags
        ):
            raise F3RelationError(f"relation/{relation.osm_id} contiene tags duplicados")
        present = {"node": 0, "way": 0, "relation": 0}
        unresolved = {"node": 0, "way": 0, "relation": 0}
        grouped: dict[tuple[str, int, str], set[str]] = {}

        for member in relation.members:
            if (
                member.member_type not in present
                or isinstance(member.ref, bool)
                or not isinstance(member.ref, int)
                or member.ref <= 0
                or not isinstance(member.role, str)
                or not isinstance(member.present, bool)
            ):
                raise F3RelationError(f"relation/{relation.osm_id} contiene un member inválido")
            counter = present if member.present else unresolved
            counter[member.member_type] += 1
            if not member.present or member.member_type == "relation":
                continue
            candidate_ids = candidates_by_object.get((member.member_type, member.ref))
            if not candidate_ids:
                continue
            member_key = (member.member_type, member.ref, member.role)
            if member_key in grouped:
                duplicate_members_grouped += 1
            grouped.setdefault(member_key, set()).update(candidate_ids)

        for member_type in present:
            present_totals[member_type] += present[member_type]
            unresolved_totals[member_type] += unresolved[member_type]
        if not grouped:
            continue

        associated_members = tuple(
            AssociatedRelationMember(
                member_type=member_type,
                member_id=member_id,
                member_ref=f"{member_type}/{member_id}",
                role=role,
                candidate_ids=tuple(sorted(grouped[(member_type, member_id, role)])),
            )
            for member_type, member_id, role in sorted(
                grouped,
                key=lambda item: (0 if item[0] == "node" else 1, item[1], item[2]),
            )
        )
        rows.append(RelationContext(
            relation_id=relation.osm_id,
            relation_ref=f"relation/{relation.osm_id}",
            tags=tuple(sorted(tags.items())),
            closure_status="not_expanded",
            member_count=len(relation.members),
            present_member_counts=_counts(present),
            unresolved_member_counts=_counts(unresolved),
            associated_members=associated_members,
        ))

    relations_input = len(inputs.inventory.relations)
    return RelationContextInventory(
        relations=tuple(rows),
        relations_input=relations_input,
        relations_emitted=len(rows),
        relations_without_associated_members=relations_input - len(rows),
        present_member_counts=_counts(present_totals),
        unresolved_member_counts=_counts(unresolved_totals),
        duplicate_members_grouped=duplicate_members_grouped,
    )
