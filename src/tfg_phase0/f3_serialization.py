"""Serialización canónica en memoria de los outputs F3."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import json
import math
from typing import Any, Iterable, Mapping

from .f3_associations import CandidateAssociationInventory
from .f3_contracts import F3_HASHED_OUTPUT_FILES
from .f3_geometry import MetricBBox, NormalizedGeometryInventory
from .f3_identity import build_f3_provenance, sha256_bytes
from .f3_inputs import VerifiedF3Inputs
from .f3_relations import RelationContextInventory


class F3SerializationError(ValueError):
    """Un valor F3 no admite representación canónica."""


def canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise F3SerializationError("documento F3 no serializable") from error
    return (text + ("\n" if newline else "")).encode("utf-8")


def normalize_metric(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise F3SerializationError("magnitud métrica no finita")
    try:
        rounded = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError) as error:
        raise F3SerializationError("magnitud métrica no representable") from error
    return 0.0 if rounded == 0 else float(rounded)


def serialize_jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    serialized = [canonical_json_bytes(dict(row)) for row in rows]
    return b"" if not serialized else b"\n".join(serialized) + b"\n"


def _bbox_document(value: MetricBBox | None) -> dict[str, float] | None:
    if value is None:
        return None
    return {
        "min_easting_m": normalize_metric(value.min_easting_m),
        "min_northing_m": normalize_metric(value.min_northing_m),
        "max_easting_m": normalize_metric(value.max_easting_m),
        "max_northing_m": normalize_metric(value.max_northing_m),
    }


def osm_object_documents(normalized: NormalizedGeometryInventory) -> tuple[dict[str, Any], ...]:
    result = []
    for item in sorted(normalized.objects, key=lambda row: (0 if row.osm_type == "node" else 1, row.osm_id)):
        document = {
            "osm_type": item.osm_type,
            "osm_id": item.osm_id,
            "osm_ref": item.osm_ref,
            "tags": dict(item.tags),
            "source_role": item.source_role,
            "geometry_role": item.geometry_role,
            "geometry_status": item.geometry_status,
            "geometry_reason": item.geometry_reason,
            "metric_bbox": _bbox_document(item.metric_bbox),
        }
        if item.osm_type == "way":
            document["is_closed"] = item.is_closed
        result.append(document)
    return tuple(result)


def association_documents(inventory: CandidateAssociationInventory) -> tuple[dict[str, Any], ...]:
    rows = sorted(
        inventory.associations,
        key=lambda row: (row.candidate_id, 0 if row.osm_type == "node" else 1, row.osm_id),
    )
    return tuple({
        "candidate_id": row.candidate_id,
        "osm_type": row.osm_type,
        "osm_id": row.osm_id,
        "osm_ref": row.osm_ref,
        "geometry_role": row.geometry_role,
        "intersects": row.intersects,
        "contains": row.contains,
        "within": row.within,
        "crosses": row.crosses,
        "touches": row.touches,
        "overlaps": row.overlaps,
        "boundary_contact_only": row.boundary_contact_only,
        "center_distance_m": normalize_metric(row.center_distance_m),
    } for row in rows)


def relation_documents(inventory: RelationContextInventory) -> tuple[dict[str, Any], ...]:
    result = []
    for row in sorted(inventory.relations, key=lambda item: item.relation_id):
        members = sorted(
            row.associated_members,
            key=lambda item: (0 if item.member_type == "node" else 1, item.member_id, item.role),
        )
        result.append({
            "relation_id": row.relation_id,
            "relation_ref": row.relation_ref,
            "tags": dict(row.tags),
            "closure_status": row.closure_status,
            "member_count": row.member_count,
            "present_member_counts": {
                "node": row.present_member_counts.node,
                "way": row.present_member_counts.way,
                "relation": row.present_member_counts.relation,
            },
            "unresolved_member_counts": {
                "node": row.unresolved_member_counts.node,
                "way": row.unresolved_member_counts.way,
                "relation": row.unresolved_member_counts.relation,
            },
            "associated_members": [{
                "member_type": item.member_type,
                "member_id": item.member_id,
                "member_ref": item.member_ref,
                "role": item.role,
                "candidate_ids": sorted(set(item.candidate_ids)),
            } for item in members],
        })
    return tuple(result)


def serialize_osm_objects(normalized: NormalizedGeometryInventory) -> bytes:
    return serialize_jsonl(osm_object_documents(normalized))


def serialize_associations(inventory: CandidateAssociationInventory) -> bytes:
    return serialize_jsonl(association_documents(inventory))


def serialize_relation_context(inventory: RelationContextInventory) -> bytes:
    return serialize_jsonl(relation_documents(inventory))


def serialize_provenance(document: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(document), newline=True)


def checksum_bytes(outputs: Mapping[str, bytes]) -> bytes:
    return "".join(
        f"{sha256_bytes(outputs[name])}  {name}\n" for name in F3_HASHED_OUTPUT_FILES
    ).encode("ascii")


def build_f3_bundle_bytes(
    inputs: VerifiedF3Inputs,
    normalized: NormalizedGeometryInventory,
    associations: CandidateAssociationInventory,
    relations: RelationContextInventory,
    *,
    project_root: str | Path,
) -> tuple[str, dict[str, bytes], dict[str, Any]]:
    provenance = build_f3_provenance(
        inputs, normalized, associations, relations, project_root=project_root
    )
    outputs = {
        "osm_objects.jsonl": serialize_osm_objects(normalized),
        "candidate_osm_associations.jsonl": serialize_associations(associations),
        "relation_context.jsonl": serialize_relation_context(relations),
        "provenance.json": serialize_provenance(provenance),
    }
    outputs["sha256.txt"] = checksum_bytes(outputs)
    return provenance["f3_dataset_id"], outputs, provenance
