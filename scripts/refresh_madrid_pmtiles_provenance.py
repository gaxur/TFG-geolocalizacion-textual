#!/usr/bin/env python3
"""Actualiza solo el sidecar PMTiles tras reproducir exactamente el mismo archive.

El archivo binario, los inputs OSM y los GeoJSON F1 nunca se modifican aquí.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def refresh_sidecar(
    *, current_archive: Path, current_sidecar: Path, candidate_archive: Path,
    candidate_sidecar: Path, backup_sidecar: Path,
) -> dict[str, str | int]:
    for path in (current_archive, current_sidecar, candidate_archive, candidate_sidecar):
        if not path.is_file():
            raise FileNotFoundError(path)
    if backup_sidecar.exists():
        raise FileExistsError(f"No se sobrescribe el backup de provenance: {backup_sidecar}")

    current_sha = sha256(current_archive)
    candidate_sha = sha256(candidate_archive)
    if current_sha != candidate_sha:
        raise ValueError("El PMTiles reproducido no es byte-idéntico al archive operativo")

    previous = json.loads(current_sidecar.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_sidecar.read_text(encoding="utf-8"))
    for document in (previous, candidate):
        if document.get("contract_version") != "madrid-osm-vector-cartography-v1":
            raise ValueError("Contract version de provenance incompatible")
        if document.get("pmtiles", {}).get("sha256") != current_sha:
            raise ValueError("El sidecar no identifica los bytes PMTiles actuales")
        if document.get("pmtiles", {}).get("size_bytes") != current_archive.stat().st_size:
            raise ValueError("Tamaño PMTiles no coincide con el sidecar")

    previous_source = previous.get("source", {})
    candidate_source = candidate.get("source", {})
    if any(previous_source.get(key) != candidate_source.get(key) for key in ("source_id", "source_pbf_sha256", "license")):
        raise ValueError("La provenance de la fuente cambió entre builds")
    previous_catalog = previous.get("catalog_lineage", {}).get("manifest_sha256")
    candidate_catalog = candidate.get("catalog_lineage", {}).get("manifest_sha256")
    if previous_catalog != candidate_catalog:
        raise ValueError("Los manifests F1 asociados cambiaron entre builds")
    destination = current_sidecar.resolve()
    stage = destination.with_name(f".{destination.name}.refresh-staging")
    if stage.exists():
        raise FileExistsError(f"No se reutiliza staging existente: {stage}")

    logical_path = candidate.get("feature_audit", {}).get("source", {}).get("path", "")
    if Path(logical_path).is_absolute() or ":\\" in logical_path:
        raise ValueError("La nueva provenance todavía contiene una ruta absoluta local")
    backup_sidecar.parent.mkdir(parents=True, exist_ok=True)
    with backup_sidecar.open("xb") as backup:
        backup.write(current_sidecar.read_bytes())
    stage.write_bytes(candidate_sidecar.read_bytes())
    stage.replace(destination)
    return {
        "pmtiles_sha256": current_sha,
        "pmtiles_size_bytes": current_archive.stat().st_size,
        "previous_sidecar_sha256": sha256(backup_sidecar),
        "updated_sidecar_sha256": sha256(destination),
        "backup_path": backup_sidecar.as_posix(),
        "sidecar_path": destination.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-archive", type=Path, default=ROOT / "data/processed/map-assets/madrid.pmtiles")
    parser.add_argument("--current-sidecar", type=Path, default=ROOT / "data/processed/map-assets/madrid.pmtiles.provenance.json")
    parser.add_argument("--candidate-archive", required=True, type=Path)
    parser.add_argument("--candidate-sidecar", required=True, type=Path)
    parser.add_argument("--backup-sidecar", type=Path, default=ROOT / "results/generated/madrid-pmtiles-provenance-before-toolchain-refresh-v1.json")
    args = parser.parse_args()
    result = refresh_sidecar(
        current_archive=args.current_archive,
        current_sidecar=args.current_sidecar,
        candidate_archive=args.candidate_archive,
        candidate_sidecar=args.candidate_sidecar,
        backup_sidecar=args.backup_sidecar,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
