"""Campaña remota H26-H61 seleccionada sin rankings, GT ni salidas VLM."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .crs import wgs84_to_epsg25830
from .mapillary_visual_pilot import reject_ground_truth


D004_BBOX = {"north": 40.4200, "south": 40.4120, "east": -3.6990, "west": -3.7090}
EXPECTED_DEVELOPMENT_IDS = tuple(f"H{index:02d}" for index in range(26, 38))
EXPECTED_TEST_IDS = tuple(f"H{index:02d}" for index in range(38, 62))


class RemoteCampaignError(ValueError):
    """El plan remoto o sus activos incumplen el protocolo congelado."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _content_id(prefix: str, document: Mapping[str, Any], field: str) -> str:
    payload = {key: value for key, value in document.items() if key != field}
    return prefix + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _distance_xy(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    return math.hypot(left["easting"] - right["easting"], left["northing"] - right["northing"])


def _inside(image: Mapping[str, Any], bbox: Mapping[str, float]) -> bool:
    return (
        bbox["south"] <= image["latitude"] <= bbox["north"]
        and bbox["west"] <= image["longitude"] <= bbox["east"]
    )


def _preference(image: Mapping[str, Any], seed: str) -> tuple[Any, ...]:
    """Orden content-neutral: no usa galería, rankings, GT, píxeles ni quality_score."""
    shortest_side = min(image["width_px"], image["height_px"])
    return (
        0 if image["camera_type"] == "perspective" else 1,
        -shortest_side,
        -image["captured_at_epoch_ms"],
        hashlib.sha256(f"{seed}|{image['image_id']}".encode()).hexdigest(),
    )


def _solve_selection(images: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    development_count = sum(row["partition"] == "development" for row in images)
    test_count = sum(row["partition"] == "test_sealed" for row in images)
    if development_count < 12 or test_count < 24:
        raise RemoteCampaignError(
            f"capacidad insuficiente antes del solver: development={development_count}, test={test_count}"
        )
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    count = len(images)
    constraints: list[list[int]] = []
    lower: list[int] = []
    upper: list[int] = []
    for partition, target in (("development", 12), ("test_sealed", 24)):
        constraints.append([index for index, row in enumerate(images) if row["partition"] == partition])
        lower.append(target)
        upper.append(target)

    groups: dict[tuple[Any, ...], list[int]] = {}
    for index, row in enumerate(images):
        groups.setdefault(("sequence", row["sequence_id"]), []).append(index)
        groups.setdefault(("block", row["block_x"], row["block_y"]), []).append(index)
    for key, indices in groups.items():
        constraints.append(indices)
        lower.append(0)
        upper.append(1 if key[0] == "sequence" else 2)

    for left_index, left in enumerate(images):
        for right_index in range(left_index + 1, count):
            if _distance_xy(left, images[right_index]) < 75:
                constraints.append([left_index, right_index])
                lower.append(0)
                upper.append(1)

    matrix = lil_matrix((len(constraints), count), dtype=float)
    for row_index, indices in enumerate(constraints):
        matrix[row_index, indices] = 1
    order = sorted(range(count), key=lambda index: images[index]["preference"])
    rank = {index: value for value, index in enumerate(order)}
    objective = np.asarray([rank[index] for index in range(count)], dtype=float)
    result = milp(
        objective,
        integrality=np.ones(count),
        bounds=Bounds(np.zeros(count), np.ones(count)),
        constraints=LinearConstraint(matrix.tocsr(), np.asarray(lower), np.asarray(upper)),
        options={"time_limit": 120, "mip_rel_gap": 0.0, "presolve": True},
    )
    if not result.success:
        raise RemoteCampaignError(f"MILP no encontró selección: {result.message}")
    selected = [images[index] for index, value in enumerate(result.x) if value > 0.5]
    return selected, {
        "solver": "scipy.optimize.milp",
        "solver_status": result.message,
        "objective": float(result.fun),
        "candidate_variables": count,
        "constraint_count": len(constraints),
    }


def select_remote_campaign(
    inventory: Mapping[str, Any],
    *,
    bbox: Mapping[str, float],
    historical: Sequence[Mapping[str, Any]],
    inventory_sha256: str,
    seed: str = "madrid-d004-h26-h61-remote-v2",
) -> dict[str, Any]:
    """Selecciona referencias con metadatos regionales, nunca por rendimiento del sistema."""
    reject_ground_truth(inventory, path="inventory")
    if dict(bbox) != D004_BBOX:
        raise RemoteCampaignError("la campaña remota v2 exige la bbox D004 exacta")
    if not isinstance(inventory_sha256, str) or len(inventory_sha256) != 64:
        raise RemoteCampaignError("hash de inventario inválido")

    images: list[dict[str, Any]] = []
    for source in inventory.get("images", []):
        if (
            not _inside(source, bbox)
            or source.get("camera_type") not in {"perspective", "equirectangular"}
            or not source.get("sequence_id")
            or source.get("orientation_degrees") is None
            or source.get("width_px", 0) <= 0
            or source.get("height_px", 0) <= 0
            or source.get("captured_at_epoch_ms", 0) < 1451606400000
        ):
            continue
        easting, northing = wgs84_to_epsg25830(source["latitude"], source["longitude"])
        row = {
            **source,
            "easting": easting,
            "northing": northing,
            "block_x": math.floor(easting / 150),
            "block_y": math.floor(northing / 150),
        }
        if row["block_x"] == 2934:
            continue
        if any(math.hypot(easting - prior["easting"], northing - prior["northing"]) < 75 for prior in historical):
            continue
        row["partition"] = "development" if row["block_x"] < 2934 else "test_sealed"
        row["preference"] = _preference(row, seed)
        images.append(row)

    selected, solver = _solve_selection(images)
    selected.sort(key=lambda row: (0 if row["partition"] == "development" else 1, row["block_y"], row["block_x"], row["image_id"]))
    reference_ids = {row["image_id"] for row in selected}
    used_verification_ids: set[str] = set()
    references = []
    for index, row in enumerate(selected, 26):
        alternatives = [
            candidate
            for candidate in images
            if candidate["image_id"] not in reference_ids
            and candidate["image_id"] not in used_verification_ids
            and candidate["sequence_id"] != row["sequence_id"]
            and _distance_xy(row, candidate) <= 50
        ]
        alternatives.sort(
            key=lambda candidate: (
                _distance_xy(row, candidate),
                0 if candidate["camera_type"] == "perspective" else 1,
                hashlib.sha256(f"verify|{seed}|{candidate['image_id']}".encode()).hexdigest(),
            )
        )
        verification = []
        seen_sequences: set[str] = set()
        for candidate in alternatives:
            if candidate["sequence_id"] in seen_sequences:
                continue
            verification.append(
                {
                    "image_id": candidate["image_id"],
                    "sequence_id": candidate["sequence_id"],
                    "distance_to_reference_m": _distance_xy(row, candidate),
                    "camera_type": candidate["camera_type"],
                    "orientation_degrees": candidate["orientation_degrees"],
                    "independence_status": "metadata_distinct_image_and_sequence_pending_pixel_checks",
                }
            )
            used_verification_ids.add(candidate["image_id"])
            seen_sequences.add(candidate["sequence_id"])
            if len(verification) == 2:
                break
        coverage = {
            2: "two_distinct_provider_sequence_ids_metadata_only",
            1: "one_distinct_provider_sequence_id_metadata_only",
            0: "no_distinct_sequence_within_50m",
        }[len(verification)]
        references.append(
            {
                "query_id": f"H{index:02d}",
                "partition": row["partition"],
                "spatial_block_id": f"B150-{row['block_x']}-{row['block_y']}",
                "reference": {
                    "image_id": row["image_id"],
                    "sequence_id": row["sequence_id"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "coordinate_source": row["coordinate_source"],
                    "captured_at_epoch_ms": row["captured_at_epoch_ms"],
                    "camera_type": row["camera_type"],
                    "orientation_degrees": row["orientation_degrees"],
                    "orientation_source": row["orientation_source"],
                    "width_px": row["width_px"],
                    "height_px": row["height_px"],
                    "reported_accuracy_m": None,
                    "accuracy_status": "unknown",
                    "heading_reliability": "unknown",
                },
                "verification_plan": verification,
                "verification_coverage_status": coverage,
            }
        )

    document = {
        "schema_version": "2.0",
        "contract_version": "remote-mapillary-selection-plan-v2",
        "selection_id": "",
        "inputs": {"inventory_id": inventory["inventory_id"], "inventory_sha256": inventory_sha256},
        "policy": {
            "seed": seed,
            "bbox_wgs84": dict(bbox),
            "projected_crs": "EPSG:25830",
            "block_size_m": 150,
            "guard_block_x": 2934,
            "historical_exclusion_m": 75,
            "new_separation_m": 75,
            "max_per_block": 2,
            "one_reference_per_sequence": True,
            "rankings_used": False,
            "vlm_outputs_used": False,
            "pixels_used": False,
            "quality_score_used": False,
            "gallery_candidates_used": False,
            "baseline_errors_used": False,
            "verification_radius_m": 50,
            "verification_excludes_all_reference_ids": True,
            "verification_excludes_reference_sequence": True,
            "verification_ids_globally_unique": True,
            "optimization": solver,
        },
        "references": references,
        "summary": {
            "development": 12,
            "test_sealed": 24,
            "total": 36,
            "unique_reference_sequences": len({item["reference"]["sequence_id"] for item in references}),
            "verification_two_sequences_metadata_only": sum(len(item["verification_plan"]) == 2 for item in references),
            "verification_one_sequence_metadata_only": sum(len(item["verification_plan"]) == 1 for item in references),
            "verification_none": sum(not item["verification_plan"] for item in references),
        },
        "limitations": [
            "remote_provider_reference_not_human_in_situ",
            "camera_coordinate_unknown_accuracy",
            "heading_reliability_unknown",
            "mapillary_coverage_and_selection_bias",
            "development_test_east_west_split_bias",
            "reference_is_approximate_evaluation_position_not_centimetric_gt",
            "pixel_level_independence_pending_download_and_human_review",
            "images_not_downloaded",
        ],
    }
    document["selection_id"] = _content_id("remote-mapillary-selection-sha256-", document, "selection_id")
    validate_selection_plan(document)
    return document


def validate_selection_plan(document: Mapping[str, Any]) -> None:
    """Valida el split, las invariantes espaciales y la separación metadata-only."""
    if document.get("contract_version") != "remote-mapillary-selection-plan-v2":
        raise RemoteCampaignError("contrato de selección remota incompatible")
    if document.get("selection_id") != _content_id("remote-mapillary-selection-sha256-", document, "selection_id"):
        raise RemoteCampaignError("selection_id no corresponde al contenido")
    references = document.get("references", [])
    ids = [item.get("query_id") for item in references]
    if tuple(ids[:12]) != EXPECTED_DEVELOPMENT_IDS or tuple(ids[12:]) != EXPECTED_TEST_IDS:
        raise RemoteCampaignError("IDs o particiones H26-H61 inválidos")
    if any(item["partition"] != ("development" if item["query_id"] in EXPECTED_DEVELOPMENT_IDS else "test_sealed") for item in references):
        raise RemoteCampaignError("split H26-H61 inválido")
    reference_ids = [item["reference"]["image_id"] for item in references]
    reference_sequences = [item["reference"]["sequence_id"] for item in references]
    verification = [asset for item in references for asset in item["verification_plan"]]
    verification_ids = [asset["image_id"] for asset in verification]
    if len(reference_ids) != len(set(reference_ids)) or len(reference_sequences) != len(set(reference_sequences)):
        raise RemoteCampaignError("referencias o secuencias duplicadas")
    if set(reference_ids).intersection(verification_ids) or len(verification_ids) != len(set(verification_ids)):
        raise RemoteCampaignError("roles referencia/verificación no son globalmente disjuntos")
    for item in references:
        if any(asset["sequence_id"] == item["reference"]["sequence_id"] for asset in item["verification_plan"]):
            raise RemoteCampaignError("verificación comparte secuencia con referencia")


def validate_pixel_independence(
    selection: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
    *,
    maximum_perceptual_distance: int = 6,
) -> dict[str, Any]:
    """Gate posterior a descarga para hashes exactos y perceptuales ya calculados."""
    validate_selection_plan(selection)
    by_id = {asset.get("image_id"): asset for asset in assets}
    expected = {
        item["reference"]["image_id"] for item in selection["references"]
    } | {
        asset["image_id"] for item in selection["references"] for asset in item["verification_plan"]
    }
    if set(by_id) != expected or len(by_id) != len(assets):
        raise RemoteCampaignError("manifest de activos incompleto o duplicado")
    for asset in assets:
        if asset.get("status") != "downloaded" or not asset.get("sha256") or not asset.get("perceptual_hash"):
            raise RemoteCampaignError("activo sin hashes exacto/perceptual")
    exact_duplicates = []
    near_duplicates = []
    for item in selection["references"]:
        reference = by_id[item["reference"]["image_id"]]
        for planned in item["verification_plan"]:
            verification = by_id[planned["image_id"]]
            if reference["sha256"] == verification["sha256"]:
                exact_duplicates.append([reference["image_id"], verification["image_id"]])
            left = int(reference["perceptual_hash"], 16)
            right = int(verification["perceptual_hash"], 16)
            distance = (left ^ right).bit_count()
            if distance <= maximum_perceptual_distance:
                near_duplicates.append(
                    {"reference_image_id": reference["image_id"], "verification_image_id": verification["image_id"], "hamming_distance": distance}
                )
    return {
        "schema_version": "1.0",
        "contract_version": "remote-mapillary-pixel-independence-v1",
        "selection_id": selection["selection_id"],
        "algorithm": "caller_supplied_perceptual_hash_hamming",
        "maximum_perceptual_distance": maximum_perceptual_distance,
        "exact_duplicates": exact_duplicates,
        "near_duplicate_review_queue": near_duplicates,
        "automatic_gate_passed": not exact_duplicates and not near_duplicates,
        "human_overlap_review_required": True,
        "independence_claim": "pending_human_overlap_review" if not exact_duplicates and not near_duplicates else "failed_or_pending_resolution",
    }
