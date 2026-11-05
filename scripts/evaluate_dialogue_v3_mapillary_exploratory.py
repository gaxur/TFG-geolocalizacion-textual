#!/usr/bin/env python3
"""Evalúa rankings DialogueVPR congelados con una referencia de cámara Mapillary."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f4_evaluation import assign_reference, haversine_m
from src.tfg_phase0.f4_validation import load_verified_f1_50m


EXPECTED = {
    "reference": "bd7edc74346b8fea1537c7cd2c84485303c85efde6205b8e03a711dd7a1bf180",
    "metadata": "155316445f399ce8e23f22f16af3e1e1b417f6e0624fb133209babd8640b3c7e",
    "catalog": "ad35d5cb3b602a9ce313e06e10f913f169430d62a948c0f5e77b396bc810f2aa",
    "state": "c1404aeb1f92c953359883dc7953385049f34723c5d1dbeed425fff5f99dcd8c",
    "snapshot": "c60e95b2cc4c708e3d6539f694184992594492102c8ba038c253c798c5e2737a",
    "R0": "dfea9eba61bf16d233d4ba3c7ef7338588dd1f36fba1214f28ae4bb42ce3830d",
    "R1": "b5f5f6a1e1f0aa81cebb8230f5bba77f4d5a2b393231a0362fdd53189f5ce828",
    "R2": "69b66338eec65ec8c23d53b65bda9c7182d30baa0529800b5d6cbebab272a0b1",
    "R3": "b7f154456258996906ed9e8f80c870adc734ab436677c992f59b8924cab45ad5",
}
CHECKPOINTS = {
    "R0": "dialogue-retrieval-checkpoint-sha256-c5ea6e7f08781883bdcfc3d08cc900fd205f69d2c6f57b1c6c54e0a80189bc7d.json",
    "R1": "dialogue-retrieval-checkpoint-sha256-0feeb759abd9e2e8ac21f9e0c092b12c4c9de786b3356ab95d121e4fe8b3c31d.json",
    "R2": "dialogue-retrieval-checkpoint-sha256-3865f6c16a421dd96056773f4813398c1938156df84e0a6d9f524c0435edf756.json",
    "R3": "dialogue-retrieval-checkpoint-sha256-5d6ce8df094a7d1b505f5bd8f3356108880eeced31cbf1ea8df16739dff00566.json",
}
KS = (1, 5, 10)
THRESHOLDS = (25, 50, 100, 500)
REFERENCE_CANDIDATE = "MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0007_C0002"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_ranking(ranking: dict[str, Any], common_ids: set[str] | None) -> set[str]:
    results = ranking["results"]
    ids = [row["candidate_id"] for row in results]
    if ranking["gallery_id"] != "madrid-50m" or len(ids) != 253 or len(set(ids)) != 253:
        raise ValueError("ranking incompatible con madrid-50m exhaustivo")
    if [row["rank"] for row in results] != list(range(1, 254)):
        raise ValueError("ranks no consecutivos")
    if any(not math.isfinite(row["cosine_similarity"]) for row in results):
        raise ValueError("score no finito")
    current = set(ids)
    if common_ids is not None and current != common_ids:
        raise ValueError("universo de candidatos distinto")
    return current


def metrics(ranking: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
    results = ranking["results"]
    distances = [haversine_m(latitude, longitude, row["latitude"], row["longitude"]) for row in results]
    reference_rank = next(row["rank"] for row in results if row["candidate_id"] == REFERENCE_CANDIDATE)
    minimums = {str(k): min(distances[:k]) for k in KS}
    return {
        "top1_candidate_id": results[0]["candidate_id"],
        "top1_error_m": distances[0],
        "minimum_error_at_k_m": minimums,
        "geo_recall_at_k": {
            str(k): {str(t): int(minimums[str(k)] <= t) for t in THRESHOLDS} for k in KS
        },
        "reference_candidate_id": REFERENCE_CANDIDATE,
        "reference_candidate_rank": reference_rank,
        "point_assignment_hit_at_k": {str(k): int(reference_rank <= k) for k in KS},
        "exploratory_point_assignment_only": True,
        "official_f54_recall": False,
    }


def delta(final: dict[str, Any], initial: dict[str, Any]) -> dict[str, Any]:
    return {
        "delta_error_m": final["top1_error_m"] - initial["top1_error_m"],
        "delta_reference_candidate_rank": final["reference_candidate_rank"] - initial["reference_candidate_rank"],
        "delta_geo_recall_at_k": {
            str(k): {
                str(t): final["geo_recall_at_k"][str(k)][str(t)] - initial["geo_recall_at_k"][str(k)][str(t)]
                for t in THRESHOLDS
            }
            for k in KS
        },
        "delta_point_assignment_hit_at_k": {
            str(k): final["point_assignment_hit_at_k"][str(k)] - initial["point_assignment_hit_at_k"][str(k)]
            for k in KS
        },
    }


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "reference", "round", "top1_candidate_id", "top1_error_m", "reference_candidate_rank",
        "point_hit_at_1", "point_hit_at_5", "point_hit_at_10",
        "geo_1_25", "geo_1_50", "geo_1_100", "geo_1_500",
        "geo_5_25", "geo_5_50", "geo_5_100", "geo_5_500",
        "geo_10_25", "geo_10_50", "geo_10_100", "geo_10_500",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for reference in ("geometry", "computed_geometry"):
            for label in ("R0", "R1", "R2", "R3"):
                row = rows_by_label(rows)[reference][label]
                flat = {
                    "reference": reference, "round": label,
                    "top1_candidate_id": row["top1_candidate_id"], "top1_error_m": row["top1_error_m"],
                    "reference_candidate_rank": row["reference_candidate_rank"],
                }
                flat.update({f"point_hit_at_{k}": row["point_assignment_hit_at_k"][str(k)] for k in KS})
                flat.update({f"geo_{k}_{t}": row["geo_recall_at_k"][str(k)][str(t)] for k in KS for t in THRESHOLDS})
                writer.writerow(flat)


def rows_by_label(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        reference: {row["round"]: row for row in rows if row["reference"] == reference}
        for reference in ("geometry", "computed_geometry")
    }


def save_markdown(path: Path, primary: dict[str, dict[str, Any]]) -> None:
    lines = [
        "# Evaluación exploratoria DialogueVPR v3 con cámara Mapillary",
        "",
        "| Ronda | Error Top-1 (m) | Rank celda ref. | Hit@1 | Hit@5 | Hit@10 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label in ("R0", "R1", "R2", "R3"):
        row = primary[label]
        hit = row["point_assignment_hit_at_k"]
        lines.append(f"| {label} | {row['top1_error_m']:.6f} | {row['reference_candidate_rank']} | {hit['1']} | {hit['5']} | {hit['10']} |")
    lines.extend([
        "",
        "Referencia: posición de cámara Mapillary, no ground truth humano F5.4.",
        "Los cuatro rankings proceden de una sola consulta y no permiten inferencia estadística general.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_figures(output: Path, primary: dict[str, dict[str, Any]]) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["R0", "R1", "R2", "R3"]
    figures = []
    for filename, ylabel, values in (
        ("top1-error-evolution.png", "Error Top-1 (m)", [primary[x]["top1_error_m"] for x in labels]),
        ("reference-cell-rank-evolution.png", "Rank de la celda de referencia", [primary[x]["reference_candidate_rank"] for x in labels]),
    ):
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        ax.plot(labels, values, marker="o", linewidth=2, color="#245c73")
        ax.set_xlabel("Ronda")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        if "rank" in filename:
            ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(output / filename, dpi=180)
        plt.close(fig)
        figures.append(filename)
    return figures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    run, reference_path, metadata_path, catalog_path, output = (
        args.run_root.resolve(), args.reference_manifest.resolve(), args.metadata.resolve(),
        args.catalog.resolve(), args.output_root.resolve(),
    )
    if output.exists():
        raise ValueError("output-root ya existe")
    if output.parent != (ROOT / "results/generated").resolve():
        raise ValueError("output-root debe estar bajo results/generated")

    input_paths = {"reference": reference_path, "metadata": metadata_path, "catalog": catalog_path, "state": run / "state.json"}
    for key, path in input_paths.items():
        if sha256(path) != EXPECTED[key]:
            raise ValueError(f"SHA-256 inesperado: {key}")
    state = read_json(run / "state.json")
    if (state["phase"], state["generation"], state["next_action"]) != ("completed", 18, "none"):
        raise ValueError("run no terminal")
    snapshot_path = run / state["session_snapshot"]
    if sha256(snapshot_path) != EXPECTED["snapshot"]:
        raise ValueError("snapshot terminal inesperado")
    for label, filename in CHECKPOINTS.items():
        if sha256(run / "checkpoints" / filename) != EXPECTED[label]:
            raise ValueError(f"checkpoint inesperado: {label}")

    snapshot = read_json(snapshot_path)
    rankings = [snapshot["initial_ranking"]] + [turn["posterior_ranking"] for turn in snapshot["turns"]]
    common = None
    for ranking in rankings:
        common = validate_ranking(ranking, common)

    config = read_json(ROOT / "config/madrid.yaml")
    catalog = load_verified_f1_50m(catalog_path, config)
    metadata = read_json(metadata_path)
    response = metadata["response"]
    if response["id"] != "145528217588574":
        raise ValueError("image ID inesperado")
    coordinates = {
        "geometry": response["geometry"]["coordinates"],
        "computed_geometry": response["computed_geometry"]["coordinates"],
    }
    assignments = {}
    rows = []
    for reference, (longitude, latitude) in coordinates.items():
        assignments[reference] = assign_reference(latitude, longitude, catalog)
        if assignments[reference].get("candidate_id") != REFERENCE_CANDIDATE:
            raise ValueError("asignación de referencia inesperada")
        for label, ranking in zip(("R0", "R1", "R2", "R3"), rankings):
            rows.append({"reference": reference, "round": label, **metrics(ranking, latitude, longitude)})
    indexed = rows_by_label(rows)
    transitions = {}
    for start, end in (("R0", "R1"), ("R1", "R2"), ("R2", "R3"), ("R0", "R3")):
        transitions[f"{start}_to_{end}"] = delta(indexed["geometry"][end], indexed["geometry"][start])

    output.mkdir(parents=False)
    metrics_document = {
        "schema_version": "1.0", "contract_version": "dialogue-v3-mapillary-metrics-by-round-v1",
        "evaluation_type": "EXPLORATORY_MAPILLARY_CAMERA_REFERENCE", "official_f54_ground_truth": False,
        "human_observer_ground_truth": False, "ks": list(KS), "thresholds_m": list(THRESHOLDS),
        "earth_radius_m": 6371008.8, "rows": rows,
    }
    write_json(output / "metrics-by-round.json", metrics_document)
    save_csv(output / "metrics-by-round.csv", rows)
    comparison = {
        "schema_version": "1.0", "contract_version": "dialogue-v3-mapillary-r0-r3-comparison-v1",
        "primary_reference": "geometry", "transitions": transitions,
        "largest_absolute_error_transition": max(
            (key for key in transitions if key != "R0_to_R3"), key=lambda key: abs(transitions[key]["delta_error_m"])
        ),
    }
    write_json(output / "comparison-r0-r3.json", comparison)
    sensitivity_rows = []
    stable = True
    for label in ("R0", "R1", "R2", "R3"):
        original, computed = indexed["geometry"][label], indexed["computed_geometry"][label]
        row = {
            "round": label,
            "computed_minus_geometry_top1_error_m": computed["top1_error_m"] - original["top1_error_m"],
            "reference_candidate_rank_changed": computed["reference_candidate_rank"] != original["reference_candidate_rank"],
            "geo_recall_changed": computed["geo_recall_at_k"] != original["geo_recall_at_k"],
            "point_assignment_hit_changed": computed["point_assignment_hit_at_k"] != original["point_assignment_hit_at_k"],
        }
        stable &= not any(row[key] for key in ("reference_candidate_rank_changed", "geo_recall_changed", "point_assignment_hit_changed"))
        sensitivity_rows.append(row)
    write_json(output / "reference-sensitivity.json", {
        "schema_version": "1.0", "contract_version": "dialogue-v3-mapillary-reference-sensitivity-v1",
        "primary_reference": "geometry", "secondary_reference": "computed_geometry",
        "assignment_same": assignments["geometry"].get("candidate_id") == assignments["computed_geometry"].get("candidate_id"),
        "categorical_conclusions_stable": stable, "rows": sensitivity_rows,
    })
    input_hashes = {key: sha256(path) for key, path in input_paths.items()}
    input_hashes.update({label: sha256(run / "checkpoints" / filename) for label, filename in CHECKPOINTS.items()})
    integrity = {
        "schema_version": "1.0", "contract_version": "dialogue-v3-mapillary-evaluation-integrity-v1",
        "status": "PASS", "input_hashes": input_hashes, "terminal_snapshot_sha256": sha256(snapshot_path),
        "rankings": 4, "candidates_per_ranking": 253, "common_universe": True,
        "gallery_id": "madrid-50m", "catalog_manifest_id": catalog.manifest_id,
        "catalog_sha256": catalog.sha256, "rankings_recomputed": False, "inference_executed": False,
        "ground_truth_type": "mapillary_camera_position", "official_f54_ground_truth": False,
    }
    write_json(output / "integrity-report.json", integrity)
    figures = save_figures(output, indexed["geometry"])
    save_markdown(output / "tables.md", indexed["geometry"])
    manifest = {
        "schema_version": "1.0", "contract_version": "dialogue-v3-mapillary-exploratory-evaluation-v1",
        "status": "DIALOGUE_V3_MAPILLARY_EXPLORATORY_EVALUATION_PASS",
        "evaluation_type": "EXPLORATORY_MAPILLARY_CAMERA_REFERENCE", "primary_reference": "geometry",
        "secondary_reference": "computed_geometry", "official_f54_ground_truth": False,
        "human_observer_ground_truth": False, "exploratory_point_assignment_only": True,
        "reference_assignments": assignments, "outputs": [
            "metrics-by-round.json", "metrics-by-round.csv", "comparison-r0-r3.json",
            "reference-sensitivity.json", "integrity-report.json", "tables.md", *figures,
        ],
        "limitations": [
            "single query descriptive comparison", "Mapillary camera is not human observer ground truth",
            "not blind evaluation", "Mapillary positional accuracy unavailable",
            "point assignment hit is not official F5.4 Recall",
        ],
    }
    write_json(output / "evaluation-manifest.json", manifest)
    result_hashes = {path.name: sha256(path) for path in sorted(output.iterdir()) if path.is_file()}
    write_json(output / "result-hashes.json", result_hashes)
    print(json.dumps({"status": manifest["status"], "output_root": str(output), "transitions": transitions, "result_hashes": result_hashes}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
