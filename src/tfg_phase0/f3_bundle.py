"""Construcción y publicación atómica Linux de bundles F3."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
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
from .validation import validate_document


AT_FDCWD = -100
RENAME_NOREPLACE = 1


class F3BundleError(RuntimeError):
    """Error al construir o publicar un bundle F3."""


class F3BundleConflictError(F3BundleError):
    """Existe un bundle incompatible o una publicación concurrente."""


class F3PublicationUnsupportedError(F3BundleError):
    """El sistema no ofrece publicación atómica no-replace."""


_UNSUPPORTED_FILESYSTEM_ERRORS = {
    errno.ENOSYS,
    errno.EINVAL,
    errno.EOPNOTSUPP,
    getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
}


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as error:
        if error.errno in _UNSUPPORTED_FILESYSTEM_ERRORS:
            raise F3PublicationUnsupportedError(
                f"el filesystem no permite abrir directorios para fsync: {path}"
            ) from error
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno in _UNSUPPORTED_FILESYSTEM_ERRORS:
                raise F3PublicationUnsupportedError(
                    f"el filesystem no soporta fsync de directorio: {path}"
                ) from error
            raise
    finally:
        os.close(descriptor)


def _write_all(output, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = output.write(view)
        if not isinstance(written, int) or written <= 0:
            raise OSError("escritura parcial sin progreso en bundle F3")
        view = view[written:]


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


def _read_input_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise F3BundleConflictError(f"no se pudo revalidar el input {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise F3BundleConflictError(f"el input no es un fichero regular: {path}")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as error:
        raise F3BundleConflictError(f"no se pudo revalidar el input {path}") from error
    finally:
        os.close(descriptor)


def _load_config_bytes(raw: bytes) -> dict:
    document = json.loads(raw.decode("utf-8"))
    validate_document(document, "region_config")
    bbox = document["region"]["bbox"]
    if bbox["south"] >= bbox["north"] or bbox["west"] >= bbox["east"]:
        raise ValueError("bbox de configuración no válida")
    return document


def _revalidate_input_files(
    inputs: VerifiedF3Inputs, *, require_exact_config: bool
) -> None:
    expected = (
        (inputs.catalog.path, inputs.catalog.sha256),
        (inputs.snapshot.source_path, inputs.snapshot.raw_sha256),
        (inputs.rules.path, inputs.rules.sha256),
    )
    for path, digest in expected:
        raw = _read_input_file(path)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise F3BundleConflictError(f"el input cambió durante F3.6: {path}")
    try:
        config_raw = _read_input_file(inputs.config_path)
        config = _load_config_bytes(config_raw)
    except Exception as error:
        if isinstance(error, F3BundleConflictError):
            raise
        raise F3BundleConflictError("no se pudo revalidar la configuración F3") from error
    if sha256_json(f3_config_input(config)) != inputs.config_effective_sha256:
        raise F3BundleConflictError("la configuración cambió durante F3.6")
    if require_exact_config and hashlib.sha256(config_raw).hexdigest() != inputs.config_sha256:
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
    temp_dir: Path | None = None
    lock_dir = parent / f".{dataset_id}.lock"
    lock_acquired = False
    published = False
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{dataset_id}.tmp-", dir=parent))
        for filename, content in outputs.items():
            path = temp_dir / filename
            with path.open("xb") as output:
                _write_all(output, content)
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
        active_error = sys.exc_info()[1]
        cleanup_errors = []
        if not published and temp_dir is not None:
            try:
                shutil.rmtree(temp_dir)
            except OSError as error:
                cleanup_errors.append(("temporal", error))
        if lock_acquired:
            try:
                lock_dir.rmdir()
            except OSError as error:
                cleanup_errors.append(("lock", error))
        if cleanup_errors:
            details = "; ".join(f"{kind}: {error}" for kind, error in cleanup_errors)
            if active_error is not None:
                active_error.add_note(f"falló el cleanup F3 ({details})")
            else:
                message = (
                    "no se pudo retirar el lock propio"
                    if len(cleanup_errors) == 1 and cleanup_errors[0][0] == "lock"
                    else f"no se pudo completar el cleanup F3 ({details})"
                )
                raise F3BundleError(message) from cleanup_errors[0][1]
