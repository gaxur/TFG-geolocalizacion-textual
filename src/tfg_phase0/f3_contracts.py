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
