"""Constantes estructurales del contrato F3, sin operaciones geométricas."""

F3_NOT_ASSOCIABLE_REASONS = (
    "added_way_node_direct_association_forbidden",
    "unknown_closed_way_no_votes",
    "unknown_closed_way_conflict",
    "unknown_closed_way_unrecognized_area_value",
)

F3_INVALID_REASONS = (
    "invalid_area_open_way",
    "invalid_area_empty",
    "invalid_area_non_positive",
    "invalid_area_invalid_polygon",
    "invalid_way_geometry_missing_node",
    "invalid_way_geometry_too_few_positions",
    "invalid_way_geometry_non_finite_coordinate",
)

F3_GEOMETRY_REASONS = F3_NOT_ASSOCIABLE_REASONS + F3_INVALID_REASONS

F3_IDENTITY_SOFTWARE_FIELDS = (
    "generator_source_sha256",
    "python_version",
    "numpy_version",
    "shapely_version",
    "geos_version",
)

F3_PROVENANCE_ONLY_SOFTWARE_FIELDS = (
    "python_implementation",
    "platform_system",
    "platform_machine",
)

F3_NUMPY_VERSION = "2.5.4"
F3_SHAPELY_VERSION = "2.1.2"
F3_GEOS_VERSION = "3.13.1"

F3_CONTRACT_VERSION = "f3-associations-v1"
F3_GENERATOR_VERSION = "phase3-geometric-associations-v1"
F3_SERIALIZATION_VERSION = "f3-jsonl-v1"
F3_CONFIG_POLICY = "f3-config-v1"
F3_SOURCE_MANIFEST_VERSION = "f3-generator-source-v1"

F3_GENERATOR_SOURCE_FILES = (
    "schemas/f3_association.schema.json",
    "schemas/f3_osm_object.schema.json",
    "schemas/f3_provenance.schema.json",
    "schemas/f3_relation_context.schema.json",
    "src/tfg_phase0/catalog.py",
    "src/tfg_phase0/config.py",
    "src/tfg_phase0/crs.py",
    "src/tfg_phase0/f3_associations.py",
    "src/tfg_phase0/f3_contracts.py",
    "src/tfg_phase0/f3_geometry.py",
    "src/tfg_phase0/f3_identity.py",
    "src/tfg_phase0/f3_inputs.py",
    "src/tfg_phase0/f3_relations.py",
    "src/tfg_phase0/f3_serialization.py",
    "src/tfg_phase0/f3_validation.py",
    "src/tfg_phase0/osm_snapshot.py",
    "src/tfg_phase0/provenance.py",
    "src/tfg_phase0/validation.py",
)

F3_HASHED_OUTPUT_FILES = (
    "osm_objects.jsonl",
    "candidate_osm_associations.jsonl",
    "relation_context.jsonl",
    "provenance.json",
)
F3_BUNDLE_FILES = F3_HASHED_OUTPUT_FILES + ("sha256.txt",)
