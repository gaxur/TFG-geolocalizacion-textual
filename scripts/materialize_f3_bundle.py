#!/usr/bin/env python3
"""Materializa y valida un bundle F3 desde inputs locales ya verificados."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "results/generated/f3"
REPORT_FORMAT_VERSION = "f3-materialization-report-v1"
ENTRYPOINT_PATH = Path(__file__).resolve()
AT_EMPTY_PATH = 0x1000
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f3_associations import (
    associate_candidates_with_index,
    build_osm_spatial_index,
)
from src.tfg_phase0.f3_bundle import publish_f3_bundle
from src.tfg_phase0.f3_contracts import F3_BUNDLE_FILES
from src.tfg_phase0.f3_geometry import geometry_software_versions, normalize_osm_geometries
from src.tfg_phase0.f3_inputs import load_verified_f3_inputs
from src.tfg_phase0.f3_relations import build_relation_context
from src.tfg_phase0.f3_validation import validate_f3_bundle


class F3ReportError(RuntimeError):
    """El bundle terminó, pero no pudo publicarse su informe operativo."""

    def __init__(
        self,
        message: str,
        *,
        bundle_path: Path,
        cache_hit: bool,
        report_path: Path,
        report_published: bool,
        durability_unknown: bool,
    ):
        super().__init__(message)
        self.bundle_path = bundle_path
        self.cache_hit = cache_hit
        self.report_path = report_path
        self.report_published = report_published
        self.durability_unknown = durability_unknown


class _ReportPublicationError(RuntimeError):
    def __init__(self, message: str, *, report_published: bool, durability_unknown: bool):
        super().__init__(message)
        self.report_published = report_published
        self.durability_unknown = durability_unknown


@dataclass
class ReportDestination:
    path: Path
    name: str
    directory_fd: int

    def close(self) -> None:
        if self.directory_fd >= 0:
            os.close(self.directory_fd)
            self.directory_fd = -1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/madrid.yaml")
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "third_party/osm-polygon-features/v0.9.2/polygon-features.json",
    )
    parser.add_argument(
        "--processed-osm-root", type=Path, default=ROOT / "data/processed/osm"
    )
    parser.add_argument("--report-json", type=Path)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state() -> dict[str, object]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return {"commit": commit, "dirty": bool(status.strip())}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _open_directory_no_symlinks(path: Path) -> int:
    absolute = Path(os.path.abspath(path))
    descriptor = os.open("/", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _name_exists(name: str, directory_fd: int) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _prepare_report_destination(args: argparse.Namespace) -> ReportDestination | None:
    report_path = args.report_json
    if report_path is None:
        return None
    report_path = Path(report_path)
    absolute = Path(os.path.abspath(report_path))
    report_root = Path(os.path.abspath(REPORT_ROOT))
    if absolute.parent != report_root:
        raise ValueError("el informe operativo debe estar bajo results/generated/f3")
    if (
        absolute.name in {"", ".", ".."}
        or "/" in absolute.name
        or os.sep in absolute.name
        or absolute.suffix != ".json"
    ):
        raise ValueError("el informe operativo debe usar extensión .json")

    resolved = absolute.resolve()
    protected_files = {
        Path(args.manifest).resolve(),
        Path(args.config).resolve(),
        Path(args.rules).resolve(),
    }
    snapshot_root = Path(args.snapshot_dir).resolve()
    processed_root = Path(args.processed_osm_root).resolve()
    if (
        resolved in protected_files
        or _is_relative_to(resolved, snapshot_root)
        or _is_relative_to(resolved, processed_root)
    ):
        raise ValueError("el informe operativo no puede coincidir con inputs u outputs F3")
    directory_fd = _open_directory_no_symlinks(report_root)
    try:
        if not os.access(f"/proc/self/fd/{directory_fd}", os.W_OK | os.X_OK):
            raise PermissionError(f"sin permisos para escribir informes bajo: {report_root}")
        if _name_exists(absolute.name, directory_fd):
            raise FileExistsError(f"el informe operativo ya existe: {absolute}")
        return ReportDestination(absolute, absolute.name, directory_fd)
    except BaseException:
        os.close(directory_fd)
        raise


def _fsync_report_directory(descriptor: int) -> None:
    os.fsync(descriptor)


def _link_fd_noreplace(source_fd: int, directory_fd: int, destination_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    linkat = getattr(libc, "linkat", None)
    if linkat is None:
        raise OSError(errno.ENOSYS, "linkat no está disponible")
    linkat.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    linkat.restype = ctypes.c_int
    if linkat(source_fd, b"", directory_fd, os.fsencode(destination_name), AT_EMPTY_PATH) == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination_name)
    raise OSError(error, os.strerror(error), destination_name)


def _close_report_fd(descriptor: int) -> None:
    os.close(descriptor)


def _publish_report(destination: ReportDestination, report: dict) -> None:
    raw = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(
        ".",
        os.O_RDWR | getattr(os, "O_TMPFILE", 0),
        0o600,
        dir_fd=destination.directory_fd,
    )
    primary_error: BaseException | None = None
    published = False
    durability_unknown = False
    try:
        try:
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("escritura parcial sin progreso en informe F3")
                view = view[written:]
            os.fsync(descriptor)
            _link_fd_noreplace(descriptor, destination.directory_fd, destination.name)
            published = True
        except BaseException as error:
            primary_error = error
        try:
            _close_report_fd(descriptor)
            descriptor = -1
        except OSError as cleanup_error:
            if primary_error is None:
                primary_error = cleanup_error
            else:
                primary_error.add_note(f"falló el cleanup del temporal F3: {cleanup_error}")
        if published:
            try:
                _fsync_report_directory(destination.directory_fd)
            except OSError as error:
                durability_unknown = True
                if primary_error is None:
                    primary_error = error
                else:
                    primary_error.add_note(f"falló fsync del directorio de informes: {error}")
        if primary_error is not None:
            state = (
                "informe visible con durabilidad no confirmada"
                if published and durability_unknown
                else "informe visible; falló el cleanup"
                if published
                else "informe no publicado"
            )
            raise _ReportPublicationError(
                f"{state}: {primary_error}",
                report_published=published,
                durability_unknown=durability_unknown,
            ) from primary_error
    finally:
        if descriptor >= 0:
            try:
                _close_report_fd(descriptor)
            except OSError:
                pass


def _timed(durations: dict[str, float], name: str, operation):
    started = time.perf_counter()
    result = operation()
    durations[name] = time.perf_counter() - started
    return result


def materialize(args: argparse.Namespace) -> dict:
    started_at = datetime.now(timezone.utc)
    git_state_at_start = _git_state()
    entrypoint_sha256_at_start = _sha256(ENTRYPOINT_PATH)
    report_destination = _prepare_report_destination(args)
    try:
        result = _materialize(
            args,
            started_at=started_at,
            git_state_at_start=git_state_at_start,
            entrypoint_sha256_at_start=entrypoint_sha256_at_start,
            report_destination=report_destination,
        )
    except BaseException as primary_error:
        if report_destination is not None:
            try:
                report_destination.close()
            except OSError as cleanup_error:
                primary_error.add_note(f"falló el cierre del directorio de informes: {cleanup_error}")
        raise
    if report_destination is not None:
        try:
            report_destination.close()
        except OSError as error:
            raise F3ReportError(
                f"bundle publicado y validado en {result['bundle_path']}; informe publicado, pero falló el cierre del directorio: {error}",
                bundle_path=Path(result["bundle_path"]),
                cache_hit=bool(result["cache_hit"]),
                report_path=report_destination.path,
                report_published=True,
                durability_unknown=False,
            ) from error
    return result


def _materialize(
    args: argparse.Namespace,
    *,
    started_at: datetime,
    git_state_at_start: dict[str, object],
    entrypoint_sha256_at_start: str,
    report_destination: ReportDestination | None,
) -> dict:
    total_started = time.perf_counter()
    durations: dict[str, float] = {}

    inputs = _timed(
        durations,
        "load_and_validate_inputs_seconds",
        lambda: load_verified_f3_inputs(
            manifest_path=args.manifest,
            snapshot_dir=args.snapshot_dir,
            config_path=args.config,
            rules_path=args.rules,
        ),
    )
    normalized = _timed(
        durations, "normalize_geometries_seconds", lambda: normalize_osm_geometries(inputs)
    )
    index = _timed(
        durations, "build_strtree_seconds", lambda: build_osm_spatial_index(normalized)
    )
    associations = _timed(
        durations,
        "associate_candidates_seconds",
        lambda: associate_candidates_with_index(inputs.catalog, index),
    )
    relations = _timed(
        durations,
        "build_relations_seconds",
        lambda: build_relation_context(inputs, normalized, associations),
    )
    destination, cache_hit = _timed(
        durations,
        "publish_seconds",
        lambda: publish_f3_bundle(
            inputs,
            normalized,
            associations,
            relations,
            project_root=ROOT,
            processed_osm_root=args.processed_osm_root,
        ),
    )
    provenance = _timed(
        durations,
        "post_publish_validate_seconds",
        lambda: validate_f3_bundle(
            destination,
            inputs=inputs,
            normalized=normalized,
            association_inventory=associations,
            relation_inventory=relations,
        ),
    )
    durations["total_seconds"] = time.perf_counter() - total_started

    file_sizes = {name: (destination / name).stat().st_size for name in F3_BUNDLE_FILES}
    file_hashes = {name: _sha256(destination / name) for name in F3_BUNDLE_FILES}
    associated_members = sum(len(relation.associated_members) for relation in relations.relations)
    candidate_id_occurrences = sum(
        len(member.candidate_ids)
        for relation in relations.relations
        for member in relation.associated_members
    )
    report = {
        "schema_version": "1.0",
        "report_format_version": REPORT_FORMAT_VERSION,
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "traceability_captured_at": "start",
        "git_commit": git_state_at_start["commit"],
        "git_dirty": git_state_at_start["dirty"],
        "entrypoint": {
            "logical_path": ENTRYPOINT_PATH.relative_to(ROOT).as_posix(),
            "sha256": entrypoint_sha256_at_start,
        },
        "command": sys.argv,
        "manifest": {
            "path": str(Path(args.manifest)),
            "sha256": inputs.catalog.sha256,
            "manifest_id": inputs.catalog.manifest_id,
            "spacing_m": inputs.catalog.spacing_m,
            "cell_size_m": inputs.catalog.cell_size_m,
            "candidate_count": len(inputs.catalog.candidates),
        },
        "osm_snapshot_id": inputs.snapshot.osm_snapshot_id,
        "f3_dataset_id": provenance["f3_dataset_id"],
        "bundle_path": str(destination),
        "cache_hit": cache_hit,
        "software": {
            "python_version": sys.version.split()[0],
            **dict(geometry_software_versions()),
        },
        "counts": {
            **provenance["counts"],
            "indexed_objects": associations.indexed_object_count,
            "associated_relation_members": associated_members,
            "relation_candidate_id_occurrences": candidate_id_occurrences,
        },
        "durations_seconds": durations,
        "file_sizes_bytes": file_sizes,
        "bundle_size_bytes": sum(file_sizes.values()),
        "file_sha256": file_hashes,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "validation_status": "PASS",
    }

    if report_destination is not None:
        try:
            _publish_report(report_destination, report)
        except _ReportPublicationError as error:
            raise F3ReportError(
                f"bundle publicado y validado en {destination}; falló el informe operativo: {error}",
                bundle_path=destination,
                cache_hit=cache_hit,
                report_path=report_destination.path,
                report_published=error.report_published,
                durability_unknown=error.durability_unknown,
            ) from error
        except Exception as error:
            raise F3ReportError(
                f"bundle publicado y validado en {destination}; falló el informe operativo antes de publicarse: {error}",
                bundle_path=destination,
                cache_hit=cache_hit,
                report_path=report_destination.path,
                report_published=False,
                durability_unknown=False,
            ) from error
    return report


def main() -> None:
    report = materialize(build_parser().parse_args())
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
