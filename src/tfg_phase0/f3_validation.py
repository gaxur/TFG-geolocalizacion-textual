"""Validación integral de bundles F3 canónicos."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from .f3_contracts import F3_BUNDLE_FILES, F3_HASHED_OUTPUT_FILES
from .f3_associations import CandidateAssociationInventory
from .f3_geometry import NormalizedGeometryInventory
from .f3_identity import f3_dataset_id, identity_from_provenance, sha256_bytes
from .f3_inputs import VerifiedF3Inputs
from .f3_relations import RelationContextInventory
from .f3_serialization import (
    association_documents,
    canonical_json_bytes,
    osm_object_documents,
    relation_documents,
    serialize_jsonl,
)
from .validation import SchemaValidationError, validate_document


class F3BundleValidationError(ValueError):
    """El bundle F3 no satisface sus contratos estructurales e integrales."""


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise F3BundleValidationError(f"no se pudo abrir el fichero {path.name}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise F3BundleValidationError(f"{path.name} no es un fichero regular")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as error:
        raise F3BundleValidationError(f"no se pudo leer {path.name}") from error
    finally:
        os.close(descriptor)


def _parse_json(raw: bytes, label: str) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise F3BundleValidationError(f"{label} contiene BOM")
    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise F3BundleValidationError(f"{label} no es JSON UTF-8 estricto") from error


def _parse_jsonl(raw: bytes, label: str) -> tuple[dict[str, Any], ...]:
    if not raw:
        return ()
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n") or b"\r" in raw:
        raise F3BundleValidationError(f"{label} no tiene framing JSONL canónico")
    result = []
    for line in raw[:-1].split(b"\n"):
        if not line:
            raise F3BundleValidationError(f"{label} contiene una fila vacía")
        document = _parse_json(line, label)
        if not isinstance(document, dict) or canonical_json_bytes(document) != line:
            raise F3BundleValidationError(f"{label} contiene JSON no canónico")
        result.append(document)
    return tuple(result)


def _parse_checksums(raw: bytes) -> dict[str, str]:
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise F3BundleValidationError("sha256.txt no tiene newline canónico")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise F3BundleValidationError("sha256.txt no es ASCII") from error
    if len(lines) != len(F3_HASHED_OUTPUT_FILES):
        raise F3BundleValidationError("sha256.txt no contiene cuatro entradas")
    result = {}
    for line, filename in zip(lines, F3_HASHED_OUTPUT_FILES, strict=True):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.]+)", line)
        if match is None or match.group(2) != filename:
            raise F3BundleValidationError("sha256.txt no respeta formato u orden")
        result[filename] = match.group(1)
    return result


def _validate_rows(
    objects: tuple[dict[str, Any], ...],
    associations: tuple[dict[str, Any], ...],
    relations: tuple[dict[str, Any], ...],
    inputs: VerifiedF3Inputs,
) -> None:
    try:
        for row in objects:
            validate_document(row, "f3_osm_object")
        for row in associations:
            validate_document(row, "f3_association")
        for row in relations:
            validate_document(row, "f3_relation_context")
    except SchemaValidationError as error:
        raise F3BundleValidationError("una fila F3 incumple su contrato") from error

    object_keys = [(row["osm_type"], row["osm_id"]) for row in objects]
    expected_object_order = sorted(object_keys, key=lambda key: (0 if key[0] == "node" else 1, key[1]))
    if object_keys != expected_object_order or len(object_keys) != len(set(object_keys)):
        raise F3BundleValidationError("osm_objects no tiene orden o identidad canónica")
    object_map = {key: row for key, row in zip(object_keys, objects, strict=True)}
    source_objects = {
        **{("node", row.osm_id): row for row in inputs.inventory.nodes},
        **{("way", row.osm_id): row for row in inputs.inventory.ways},
    }
    if set(object_map) != set(source_objects):
        raise F3BundleValidationError("osm_objects no cubre exactamente F2")
    for key, row in object_map.items():
        source = source_objects[key]
        expected_role = source.source_role if key[0] == "node" else "way_bbox_intersection"
        if row["tags"] != dict(source.tags) or row["source_role"] != expected_role:
            raise F3BundleValidationError("osm_objects no conserva tags o procedencia F2")

    candidate_ids = {candidate.candidate_id for candidate in inputs.catalog.candidates}
    association_keys = [(row["candidate_id"], row["osm_type"], row["osm_id"]) for row in associations]
    expected_association_order = sorted(
        association_keys, key=lambda key: (key[0], 0 if key[1] == "node" else 1, key[2])
    )
    if association_keys != expected_association_order or len(association_keys) != len(set(association_keys)):
        raise F3BundleValidationError("associations no tiene orden o identidad canónica")
    direct = set()
    for row in associations:
        key = (row["osm_type"], row["osm_id"])
        obj = object_map.get(key)
        if (
            row["candidate_id"] not in candidate_ids
            or obj is None
            or obj["geometry_status"] != "valid"
            or obj["geometry_role"] != row["geometry_role"]
        ):
            raise F3BundleValidationError("association no está respaldada por F1/F3")
        direct.add((row["candidate_id"], *key))

    relation_source = {relation.osm_id: relation for relation in inputs.inventory.relations}
    relation_ids = [row["relation_id"] for row in relations]
    if relation_ids != sorted(relation_ids) or len(relation_ids) != len(set(relation_ids)):
        raise F3BundleValidationError("relations no tiene orden o identidad canónica")
    for row in relations:
        source = relation_source.get(row["relation_id"])
        if source is None or dict(source.tags) != row["tags"] or row["member_count"] != len(source.members):
            raise F3BundleValidationError("relation_context no corresponde a F2")
        present = Counter(member.member_type for member in source.members if member.present)
        unresolved = Counter(member.member_type for member in source.members if not member.present)
        for member_type in ("node", "way", "relation"):
            if row["present_member_counts"][member_type] != present[member_type]:
                raise F3BundleValidationError("conteos de members presentes incoherentes")
            if row["unresolved_member_counts"][member_type] != unresolved[member_type]:
                raise F3BundleValidationError("conteos de members ausentes incoherentes")
        source_members = {(member.member_type, member.ref, member.role) for member in source.members}
        member_keys = []
        for member in row["associated_members"]:
            key = (member["member_type"], member["member_id"], member["role"])
            member_keys.append(key)
            if key not in source_members:
                raise F3BundleValidationError("associated_member no existe en F2")
            expected_candidates = sorted(
                candidate_id for candidate_id, osm_type, osm_id in direct
                if (osm_type, osm_id) == key[:2]
            )
            if member["candidate_ids"] != expected_candidates:
                raise F3BundleValidationError("candidate_ids propagados no corresponden a F3.4")
        expected_member_order = sorted(member_keys, key=lambda key: (0 if key[0] == "node" else 1, key[1], key[2]))
        if member_keys != expected_member_order or len(member_keys) != len(set(member_keys)):
            raise F3BundleValidationError("associated_members no tiene orden canónico")

    directly_associated_objects = {(osm_type, osm_id) for _, osm_type, osm_id in direct}
    expected_relation_ids = {
        relation.osm_id
        for relation in inputs.inventory.relations
        if any(
            member.present
            and member.member_type in {"node", "way"}
            and (member.member_type, member.ref) in directly_associated_objects
            for member in relation.members
        )
    }
    if set(relation_ids) != expected_relation_ids:
        raise F3BundleValidationError("relation_context no contiene exactamente las relations esperadas")


def _recalculated_counts(
    objects: tuple[dict[str, Any], ...],
    associations: tuple[dict[str, Any], ...],
    relations: tuple[dict[str, Any], ...],
    inputs: VerifiedF3Inputs,
) -> dict[str, Any]:
    by_object = Counter((row["osm_type"], row["osm_id"]) for row in associations)
    present = Counter()
    unresolved = Counter()
    for relation in inputs.inventory.relations:
        for member in relation.members:
            (present if member.present else unresolved)[member.member_type] += 1
    def complete(counter: Counter[str], keys: tuple[str, ...]) -> dict[str, int]:
        return {key: counter[key] for key in keys}

    return {
        "input_objects": {
            "node": len(inputs.inventory.nodes), "way": len(inputs.inventory.ways),
            "relation": len(inputs.inventory.relations),
        },
        "objects_by_type": complete(Counter(row["osm_type"] for row in objects), ("node", "way")),
        "objects_by_source_role": complete(
            Counter(row["source_role"] for row in objects),
            ("node_bbox", "added_way_node", "way_bbox_intersection"),
        ),
        "objects_by_geometry_role": complete(
            Counter(row["geometry_role"] for row in objects), ("point", "line", "area", "none")
        ),
        "objects_by_geometry_status": complete(
            Counter(row["geometry_status"] for row in objects), ("valid", "not_associable", "invalid")
        ),
        "associations": len(associations),
        "boundary_contact_only": sum(row["boundary_contact_only"] for row in associations),
        "multi_cell_objects": sum(value > 1 for value in by_object.values()),
        "unknown_closed_way": sum(row["osm_type"] == "way" and row["geometry_status"] == "not_associable" for row in objects),
        "invalid_area": sum(bool(row["geometry_reason"] and row["geometry_reason"].startswith("invalid_area_")) for row in objects),
        "invalid_way_geometry": sum(bool(row["geometry_reason"] and row["geometry_reason"].startswith("invalid_way_geometry_")) for row in objects),
        "relations_input": len(inputs.inventory.relations),
        "relations_emitted": len(relations),
        "relations_without_associated_members": len(inputs.inventory.relations) - len(relations),
        "present_relation_members": {key: present[key] for key in ("node", "way", "relation")},
        "unresolved_relation_members": {key: unresolved[key] for key in ("node", "way", "relation")},
    }


def validate_f3_bundle(
    bundle_dir: str | Path,
    *,
    inputs: VerifiedF3Inputs,
    normalized: NormalizedGeometryInventory,
    association_inventory: CandidateAssociationInventory,
    relation_inventory: RelationContextInventory,
    expected_identity: Mapping[str, Any] | None = None,
    require_canonical_directory_name: bool = True,
) -> dict[str, Any]:
    path = Path(bundle_dir)
    try:
        if path.is_symlink() or not path.is_dir():
            raise F3BundleValidationError("el bundle F3 no es un directorio regular")
        if {item.name for item in path.iterdir()} != set(F3_BUNDLE_FILES):
            raise F3BundleValidationError("el bundle F3 no contiene exactamente cinco archivos")
    except OSError as error:
        raise F3BundleValidationError("no se pudo inspeccionar el directorio F3") from error
    raw = {filename: _read_regular(path / filename) for filename in F3_BUNDLE_FILES}
    checksums = _parse_checksums(raw["sha256.txt"])
    if any(sha256_bytes(raw[name]) != checksums[name] for name in F3_HASHED_OUTPUT_FILES):
        raise F3BundleValidationError("checksum F3 incorrecto")
    objects = _parse_jsonl(raw["osm_objects.jsonl"], "osm_objects.jsonl")
    associations = _parse_jsonl(raw["candidate_osm_associations.jsonl"], "candidate_osm_associations.jsonl")
    relations = _parse_jsonl(raw["relation_context.jsonl"], "relation_context.jsonl")
    expected_objects = osm_object_documents(normalized)
    expected_associations = association_documents(association_inventory)
    expected_relations = relation_documents(relation_inventory)
    if raw["osm_objects.jsonl"] != serialize_jsonl(expected_objects):
        raise F3BundleValidationError("osm_objects no corresponde al inventario F3.3")
    if raw["candidate_osm_associations.jsonl"] != serialize_jsonl(expected_associations):
        raise F3BundleValidationError("associations no corresponde al inventario F3.4")
    if raw["relation_context.jsonl"] != serialize_jsonl(expected_relations):
        raise F3BundleValidationError("relation_context no corresponde al inventario F3.5")
    provenance = _parse_json(raw["provenance.json"], "provenance.json")
    if not raw["provenance.json"].endswith(b"\n") or raw["provenance.json"] != canonical_json_bytes(provenance, newline=True):
        raise F3BundleValidationError("provenance.json no es canónico")
    try:
        validate_document(provenance, "f3_provenance")
    except SchemaValidationError as error:
        raise F3BundleValidationError("provenance F3 inválida") from error
    identity = identity_from_provenance(provenance)
    computed_id = f3_dataset_id(identity)
    if provenance["f3_dataset_id"] != computed_id:
        raise F3BundleValidationError("f3_dataset_id no corresponde a la identidad")
    if require_canonical_directory_name and path.name != computed_id:
        raise F3BundleValidationError("f3_dataset_id no corresponde al directorio")
    if expected_identity is not None and identity != dict(expected_identity):
        raise F3BundleValidationError("el bundle no corresponde a los inputs efectivos esperados")
    expected_input_metadata = {
        "catalog_sha256": inputs.catalog.sha256,
        "catalog_manifest_id": inputs.catalog.manifest_id,
        "catalog_size_bytes": inputs.catalog.size_bytes,
        "catalog_region_id": inputs.catalog.region_id,
        "catalog_version": inputs.catalog.catalog_version,
        "catalog_spacing_m": inputs.catalog.spacing_m,
        "catalog_cell_size_m": inputs.catalog.cell_size_m,
        "catalog_source_crs": inputs.catalog.source_crs,
        "catalog_projected_crs": inputs.catalog.projected_crs,
        "catalog_grid_hash": inputs.catalog.grid_hash,
        "osm_snapshot_id": inputs.snapshot.osm_snapshot_id,
        "osm_raw_sha256": inputs.snapshot.raw_sha256,
        "osm_raw_size_bytes": inputs.snapshot.raw_size_bytes,
        "osm_region_id": inputs.snapshot.provenance["region_id"],
        "osm_selection": dict(inputs.snapshot.provenance["selection"]),
        "osm_closure": dict(inputs.snapshot.provenance["closure"]),
        "rules_sha256": inputs.rules.sha256,
        "config_canonical_sha256": inputs.config_effective_sha256,
    }
    actual_input_metadata = {
        "catalog_sha256": provenance["inputs"]["catalog"]["sha256"],
        "catalog_manifest_id": provenance["inputs"]["catalog"]["manifest_id"],
        "catalog_size_bytes": provenance["inputs"]["catalog"]["size_bytes"],
        "catalog_region_id": provenance["inputs"]["catalog"]["region_id"],
        "catalog_version": provenance["inputs"]["catalog"]["catalog_version"],
        "catalog_spacing_m": provenance["inputs"]["catalog"]["spacing_m"],
        "catalog_cell_size_m": provenance["inputs"]["catalog"]["cell_size_m"],
        "catalog_source_crs": provenance["inputs"]["catalog"]["source_crs"],
        "catalog_projected_crs": provenance["inputs"]["catalog"]["projected_crs"],
        "catalog_grid_hash": provenance["inputs"]["catalog"]["grid_hash"],
        "osm_snapshot_id": provenance["inputs"]["osm"]["osm_snapshot_id"],
        "osm_raw_sha256": provenance["inputs"]["osm"]["raw_sha256"],
        "osm_raw_size_bytes": provenance["inputs"]["osm"]["raw_size_bytes"],
        "osm_region_id": provenance["inputs"]["osm"]["region_id"],
        "osm_selection": provenance["inputs"]["osm"]["selection"],
        "osm_closure": provenance["inputs"]["osm"]["closure"],
        "rules_sha256": provenance["inputs"]["rules"]["sha256"],
        "config_canonical_sha256": provenance["inputs"]["config"]["canonical_sha256"],
    }
    if actual_input_metadata != expected_input_metadata:
        raise F3BundleValidationError("la provenance no corresponde a los inputs verificados")
    _validate_rows(objects, associations, relations, inputs)
    if provenance["counts"] != _recalculated_counts(objects, associations, relations, inputs):
        raise F3BundleValidationError("los conteos de provenance no corresponden al bundle")
    return provenance
