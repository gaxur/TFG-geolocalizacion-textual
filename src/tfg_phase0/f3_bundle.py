"""Construcción y publicación atómica Linux de bundles F3."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from .config import load_region_config
from .f3_associations import CandidateAssociationInventory
from .f3_geometry import NormalizedGeometryInventory
from .f3_identity import (
    generator_source_sha256,
    identity_from_provenance,
)
from .f3_inputs import VerifiedF3Inputs
from .f3_inputs import f3_config_input
from .f3_relations import RelationContextInventory
from .f3_serialization import (
    build_f3_bundle_bytes,
)
from .f3_validation import F3BundleValidationError, validate_f3_bundle
from .provenance import sha256_json


AT_FDCWD = -100
RENAME_NOREPLACE = 1


class F3BundleError(RuntimeError):
    """Error al construir o publicar un bundle F3."""


class F3BundleConflictError(F3BundleError):
    """Existe un bundle incompatible o una publicación concurrente."""


class F3PublicationUnsupportedError(F3BundleError):
    """El sistema no ofrece publicación atómica no-replace."""


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(source: Path, destination: Path) -> None:
    if os.name != "posix":
        raise F3PublicationUnsupportedError("F3.6 requiere Linux")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise F3PublicationUnsupportedError("renameat2 no está disponible")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        AT_FDCWD, os.fsencode(source), AT_FDCWD, os.fsencode(destination), RENAME_NOREPLACE
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination)
    if error in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV}:
        raise F3PublicationUnsupportedError(os.strerror(error))
    raise OSError(error, os.strerror(error), destination)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise F3BundleConflictError(f"no se pudo revalidar el input {path}") from error
    return digest.hexdigest()


def _revalidate_input_files(
    inputs: VerifiedF3Inputs, *, require_exact_config: bool
) -> None:
    expected = (
        (inputs.catalog.path, inputs.catalog.sha256),
        (inputs.snapshot.source_path, inputs.snapshot.raw_sha256),
        (inputs.rules.path, inputs.rules.sha256),
    )
    for path, digest in expected:
        if not path.is_file() or _file_sha256(path) != digest:
            raise F3BundleConflictError(f"el input cambió durante F3.6: {path}")
    try:
        config = load_region_config(inputs.config_path)
    except Exception as error:
        raise F3BundleConflictError("no se pudo revalidar la configuración F3") from error
    if sha256_json(f3_config_input(config)) != inputs.config_effective_sha256:
        raise F3BundleConflictError("la configuración cambió durante F3.6")
    if require_exact_config and _file_sha256(inputs.config_path) != inputs.config_sha256:
        raise F3BundleConflictError("los bytes de configuración cambiaron durante F3.6")


def publish_f3_bundle(
    inputs: VerifiedF3Inputs,
    normalized: NormalizedGeometryInventory,
    associations: CandidateAssociationInventory,
    relations: RelationContextInventory,
    *,
    project_root: str | Path,
    processed_osm_root: str | Path,
) -> tuple[Path, bool]:
    root = Path(project_root)
    dataset_id, outputs, provenance = build_f3_bundle_bytes(
        inputs, normalized, associations, relations, project_root=root
    )
    identity = identity_from_provenance(provenance)
    expected_generator_hash = identity["software"]["generator_source_sha256"]
    parent = Path(processed_osm_root) / inputs.snapshot.osm_snapshot_id
    final_dir = parent / dataset_id
    if final_dir.exists():
        _revalidate_input_files(inputs, require_exact_config=False)
        try:
            validate_f3_bundle(
                final_dir, inputs=inputs, normalized=normalized,
                association_inventory=associations, relation_inventory=relations,
                expected_identity=identity,
            )
        except F3BundleValidationError as error:
            raise F3BundleConflictError("bundle F3 existente incompatible") from error
        return final_dir, True

    _revalidate_input_files(inputs, require_exact_config=True)
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{dataset_id}.tmp-", dir=parent))
    lock_dir = parent / f".{dataset_id}.lock"
    lock_acquired = False
    published = False
    try:
        for filename, content in outputs.items():
            path = temp_dir / filename
            with path.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
        _fsync_directory(temp_dir)
        validate_f3_bundle(
            temp_dir,
            inputs=inputs,
            normalized=normalized,
            association_inventory=associations,
            relation_inventory=relations,
            expected_identity=identity,
            require_canonical_directory_name=False,
        )
        try:
            lock_dir.mkdir()
        except FileExistsError as error:
            raise F3BundleConflictError("otra publicación F3 está en curso") from error
        lock_acquired = True
        _revalidate_input_files(inputs, require_exact_config=True)
        if generator_source_sha256(root) != expected_generator_hash:
            raise F3BundleConflictError("el código efectivo cambió durante F3.6")
        if final_dir.exists():
            validate_f3_bundle(
                final_dir, inputs=inputs, normalized=normalized,
                association_inventory=associations, relation_inventory=relations,
                expected_identity=identity,
            )
            return final_dir, True
        try:
            _rename_noreplace(temp_dir, final_dir)
            published = True
        except FileExistsError:
            validate_f3_bundle(
                final_dir, inputs=inputs, normalized=normalized,
                association_inventory=associations, relation_inventory=relations,
                expected_identity=identity,
            )
            return final_dir, True
        _fsync_directory(parent)
        return final_dir, False
    except F3BundleValidationError as error:
        raise F3BundleConflictError("bundle F3 inválido") from error
    finally:
        if not published:
            shutil.rmtree(temp_dir, ignore_errors=True)
        if lock_acquired:
            try:
                lock_dir.rmdir()
            except OSError as error:
                raise F3BundleError("no se pudo retirar el lock propio") from error
