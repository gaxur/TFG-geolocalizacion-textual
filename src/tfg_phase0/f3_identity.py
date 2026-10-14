"""Identidad y provenance canónicas del bundle F3 conforme a D052."""

from __future__ import annotations

import hashlib
import json
import platform
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .f3_associations import CandidateAssociationInventory
from .f3_contracts import (
    F3_CONFIG_POLICY,
    F3_CONTRACT_VERSION,
    F3_GENERATOR_SOURCE_FILES,
    F3_GENERATOR_VERSION,
    F3_SERIALIZATION_VERSION,
    F3_SOURCE_MANIFEST_VERSION,
)
from .f3_geometry import NormalizedGeometryInventory, geometry_software_versions
from .f3_inputs import VerifiedF3Inputs
from .f3_relations import RelationContextInventory


IDENTITY_PREFIX = "f3-madrid-pilot-associations-sha256-"


class F3IdentityError(ValueError):
    """No puede construirse una identidad F3 canónica."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise F3IdentityError("identidad F3 no serializable") from error


def generator_source_manifest(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    files = []
    for logical_path in F3_GENERATOR_SOURCE_FILES:
        path = root / logical_path
        if not path.is_file():
            raise F3IdentityError(f"falta código efectivo F3: {logical_path}")
        files.append({"path": logical_path, "sha256": sha256_bytes(path.read_bytes())})
    return {"version": F3_SOURCE_MANIFEST_VERSION, "files": files}


def generator_source_sha256(project_root: str | Path) -> str:
    return sha256_bytes(_identity_json(generator_source_manifest(project_root)))


def logical_path(path: Path, project_root: Path) -> str:
    try:
        value = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError as error:
        raise F3IdentityError(f"path fuera del proyecto: {path}") from error
    if not value or value == "." or any(part in {"", ".", ".."} for part in Path(value).parts):
        raise F3IdentityError(f"path lógico no válido: {path}")
    return value


def build_f3_identity(
    inputs: VerifiedF3Inputs,
    *,
    generator_hash: str,
    transform_hash: str,
    python_version: str,
    numpy_version: str,
    shapely_version: str,
    geos_version: str,
) -> dict[str, Any]:
    """Construye el preimage exacto definido por D052."""
    return {
        "contract_version": F3_CONTRACT_VERSION,
        "generator_version": F3_GENERATOR_VERSION,
        "catalog": {
            "manifest_sha256": inputs.catalog.sha256,
            "manifest_id": inputs.catalog.manifest_id,
        },
        "osm": {
            "osm_snapshot_id": inputs.snapshot.osm_snapshot_id,
            "raw_sha256": inputs.snapshot.raw_sha256,
        },
        "rules": {"policy": inputs.rules.policy, "sha256": inputs.rules.sha256},
        "config": {
            "policy": F3_CONFIG_POLICY,
            "canonical_sha256": inputs.config_effective_sha256,
        },
        "geometry": {
            "projected_crs": inputs.catalog.projected_crs,
            "transform_version": "phase1-crs-v1",
            "transform_source_sha256": transform_hash,
            "association_predicate": "intersects",
            "predicate_direction": "osm_geometry_to_candidate_cell",
            "boundary_contact_policy": "touches",
            "relation_policy": "present_associated_members_one_hop",
            "invalid_geometry_policy": "reject_without_repair",
            "direct_node_policy": "node_bbox_only",
        },
        "software": {
            "generator_source_sha256": generator_hash,
            "python_version": python_version,
            "numpy_version": numpy_version,
            "shapely_version": shapely_version,
            "geos_version": geos_version,
        },
        "serialization_version": F3_SERIALIZATION_VERSION,
    }


def f3_dataset_id(identity: Mapping[str, Any]) -> str:
    digest = sha256_bytes(_identity_json(identity))
    return IDENTITY_PREFIX + digest


def identity_from_provenance(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": document["contract_version"],
        "generator_version": document["generator_version"],
        "catalog": {
            "manifest_sha256": document["inputs"]["catalog"]["sha256"],
            "manifest_id": document["inputs"]["catalog"]["manifest_id"],
        },
        "osm": {
            "osm_snapshot_id": document["inputs"]["osm"]["osm_snapshot_id"],
            "raw_sha256": document["inputs"]["osm"]["raw_sha256"],
        },
        "rules": {
            "policy": document["inputs"]["rules"]["policy"],
            "sha256": document["inputs"]["rules"]["sha256"],
        },
        "config": {
            "policy": document["inputs"]["config"]["canonical_policy"],
            "canonical_sha256": document["inputs"]["config"]["canonical_sha256"],
        },
        "geometry": {
            field: document["geometry"][field]
            for field in (
                "projected_crs", "transform_version", "transform_source_sha256",
                "association_predicate", "predicate_direction",
                "boundary_contact_policy", "relation_policy",
                "invalid_geometry_policy", "direct_node_policy",
            )
        },
        "software": {
            field: document["software"][field]
            for field in (
                "generator_source_sha256", "python_version", "numpy_version",
                "shapely_version", "geos_version",
            )
        },
        "serialization_version": document["serialization"]["version"],
    }


def build_f3_counts(
    inputs: VerifiedF3Inputs,
    normalized: NormalizedGeometryInventory,
    associations: CandidateAssociationInventory,
    relations: RelationContextInventory,
) -> dict[str, Any]:
    objects = normalized.objects
    association_counts = Counter((row.osm_type, row.osm_id) for row in associations.associations)
    def complete(counter: Counter[str], keys: tuple[str, ...]) -> dict[str, int]:
        return {key: counter[key] for key in keys}

    return {
        "input_objects": {
            "node": len(inputs.inventory.nodes),
            "way": len(inputs.inventory.ways),
            "relation": len(inputs.inventory.relations),
        },
        "objects_by_type": complete(Counter(row.osm_type for row in objects), ("node", "way")),
        "objects_by_source_role": complete(
            Counter(row.source_role for row in objects),
            ("node_bbox", "added_way_node", "way_bbox_intersection"),
        ),
        "objects_by_geometry_role": complete(
            Counter(row.geometry_role for row in objects), ("point", "line", "area", "none")
        ),
        "objects_by_geometry_status": complete(
            Counter(row.geometry_status for row in objects), ("valid", "not_associable", "invalid")
        ),
        "associations": len(associations.associations),
        "boundary_contact_only": sum(row.boundary_contact_only for row in associations.associations),
        "multi_cell_objects": sum(value > 1 for value in association_counts.values()),
        "unknown_closed_way": sum(
            row.osm_type == "way" and row.geometry_status == "not_associable"
            for row in objects
        ),
        "invalid_area": sum(
            bool(row.geometry_reason and row.geometry_reason.startswith("invalid_area_"))
            for row in objects
        ),
        "invalid_way_geometry": sum(
            bool(row.geometry_reason and row.geometry_reason.startswith("invalid_way_geometry_"))
            for row in objects
        ),
        "relations_input": relations.relations_input,
        "relations_emitted": relations.relations_emitted,
        "relations_without_associated_members": relations.relations_without_associated_members,
        "present_relation_members": {
            "node": relations.present_member_counts.node,
            "way": relations.present_member_counts.way,
            "relation": relations.present_member_counts.relation,
        },
        "unresolved_relation_members": {
            "node": relations.unresolved_member_counts.node,
            "way": relations.unresolved_member_counts.way,
            "relation": relations.unresolved_member_counts.relation,
        },
    }


def build_f3_provenance(
    inputs: VerifiedF3Inputs,
    normalized: NormalizedGeometryInventory,
    associations: CandidateAssociationInventory,
    relations: RelationContextInventory,
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    root = Path(project_root)
    versions = geometry_software_versions()
    generator_hash = generator_source_sha256(root)
    transform_hash = sha256_bytes((root / "src/tfg_phase0/crs.py").read_bytes())
    identity = build_f3_identity(
        inputs,
        generator_hash=generator_hash,
        transform_hash=transform_hash,
        python_version=platform.python_version(),
        numpy_version=versions["numpy_version"],
        shapely_version=versions["shapely_version"],
        geos_version=versions["geos_version"],
    )
    return {
        "schema_version": "1.0",
        "f3_dataset_id": f3_dataset_id(identity),
        "generator_version": F3_GENERATOR_VERSION,
        "contract_version": F3_CONTRACT_VERSION,
        "inputs": {
            "catalog": {
                "logical_path": logical_path(inputs.catalog.path, root),
                "size_bytes": inputs.catalog.size_bytes,
                "sha256": inputs.catalog.sha256,
                "schema_version": "1.0",
                "manifest_id": inputs.catalog.manifest_id,
                "region_id": inputs.catalog.region_id,
                "catalog_version": inputs.catalog.catalog_version,
                "spacing_m": inputs.catalog.spacing_m,
                "cell_size_m": inputs.catalog.cell_size_m,
                "source_crs": inputs.catalog.source_crs,
                "projected_crs": inputs.catalog.projected_crs,
                "grid_hash": inputs.catalog.grid_hash,
                "generator_version": "phase1-grid-v1",
            },
            "osm": {
                "logical_path": logical_path(inputs.snapshot.source_path, root),
                "provenance_logical_path": logical_path(inputs.snapshot.provenance_path, root),
                "osm_snapshot_id": inputs.snapshot.osm_snapshot_id,
                "raw_sha256": inputs.snapshot.raw_sha256,
                "raw_size_bytes": inputs.snapshot.raw_size_bytes,
                "schema_version": inputs.snapshot.provenance["schema_version"],
                "region_id": inputs.snapshot.provenance["region_id"],
                "selection": dict(inputs.snapshot.provenance["selection"]),
                "closure": dict(inputs.snapshot.provenance["closure"]),
            },
            "rules": {
                "decision": "D049",
                "policy": inputs.rules.policy,
                "repository": "https://github.com/tyrasd/osm-polygon-features",
                "release": inputs.rules.release,
                "commit": inputs.rules.commit,
                "file": "polygon-features.json",
                "size_bytes": inputs.rules.size_bytes,
                "sha256": inputs.rules.sha256,
                "license": "CC0-1.0",
            },
            "config": {
                "logical_path": logical_path(inputs.config_path, root),
                "schema_version": "1.0",
                "file_sha256": inputs.config_sha256,
                "canonical_policy": F3_CONFIG_POLICY,
                "canonical_sha256": inputs.config_effective_sha256,
            },
        },
        "geometry": {
            "source_crs": "EPSG:4326",
            **identity["geometry"],
            "transform_name": "tfg_phase0.crs.wgs84_to_epsg25830",
        },
        "software": {
            **identity["software"],
            "python_implementation": platform.python_implementation(),
            "platform_system": platform.system(),
            "platform_machine": platform.machine(),
        },
        "serialization": {
            "version": F3_SERIALIZATION_VERSION,
            "encoding": "UTF-8",
            "ensure_ascii": False,
            "allow_nan": False,
            "separators": [",", ":"],
            "key_order": "lexicographic",
            "row_order": {
                "osm_objects": "osm_type_node_way_then_osm_id_numeric",
                "associations": "candidate_id_then_osm_type_node_way_then_osm_id_numeric",
                "relations": "relation_id_numeric",
                "members": "member_type_node_way_relation_then_member_id_numeric_then_role",
                "candidate_ids": "lexicographic_unique",
            },
            "metric_rounding_digits": 6,
            "negative_zero_policy": "normalize_to_positive_zero",
            "final_newline": True,
        },
        "counts": build_f3_counts(inputs, normalized, associations, relations),
    }
