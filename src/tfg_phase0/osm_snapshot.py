"""Adquisición reproducible y validación de snapshots OSM según D043-D048."""

from __future__ import annotations

import email.utils
import hashlib
import http.client
import json
import math
import os
import shutil
import socket
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .provenance import canonical_json
from .validation import SchemaValidationError, validate_document


OSM_ATTRIBUTION = (
    "© OpenStreetMap contributors. Datos disponibles bajo la Open Database "
    "License (ODbL). https://www.openstreetmap.org/copyright"
)
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


class SnapshotError(RuntimeError):
    """Error de adquisición, validación o publicación de snapshot."""


class SnapshotValidationError(SnapshotError):
    """El raw no cumple el contrato OSM XML de D048."""


class SnapshotConflictError(SnapshotError):
    """Existe un snapshot incompatible que no debe sobrescribirse."""


class RawSizeLimitError(SnapshotValidationError):
    """El raw supera el límite configurado."""


class NetworkTransportError(SnapshotError):
    """Fallo de conexión o streaming que D048 permite reintentar."""


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    chunks: Iterable[bytes]


Transport = Callable[[str, bytes, Mapping[str, str], float, float], TransportResponse]
Sleep = Callable[[float], None]


def build_overpass_query(bbox: Mapping[str, float], server_timeout_seconds: int) -> str:
    """Serializa de forma determinista la consulta canónica de D048."""
    south = f"{bbox['south']:.4f}"
    west = f"{bbox['west']:.4f}"
    north = f"{bbox['north']:.4f}"
    east = f"{bbox['east']:.4f}"
    area = f"{south},{west},{north},{east}"
    return (
        f"[out:xml][timeout:{server_timeout_seconds}];\n"
        "(\n"
        f"  node({area});\n"
        f"  way({area});\n"
        ")->.local;\n"
        "(\n"
        "  .local;\n"
        "  node(w.local);\n"
        "  rel(bn.local);\n"
        "  rel(bw.local);\n"
        ");\n"
        "out meta qt;\n"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def snapshot_id(region_id: str, raw_format: str, raw_sha256: str) -> str:
    if region_id != "madrid_pilot" or raw_format != "osmxml":
        raise ValueError("región o formato no soportado por D048")
    if len(raw_sha256) != 64 or any(character not in "0123456789abcdef" for character in raw_sha256):
        raise ValueError("raw_sha256 no es válido")
    return f"osm-madrid-pilot-osmxml-sha256-{raw_sha256}"


def snapshot_hash_from_id(value: str) -> str:
    prefix = "osm-madrid-pilot-osmxml-sha256-"
    if not value.startswith(prefix):
        raise ValueError("osm_snapshot_id no es válido")
    digest = value.removeprefix(prefix)
    snapshot_id("madrid_pilot", "osmxml", digest)
    return digest


def validate_endpoint(endpoint: str) -> None:
    parsed = urllib.parse.urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SnapshotValidationError("endpoint HTTPS inválido o con credenciales/parámetros")


def _safe_xml_bytes(raw: bytes) -> None:
    sample = raw[:4096].lstrip().lower()
    if not raw:
        raise SnapshotValidationError("el raw está vacío")
    if sample.startswith(b"<html") or b"<!doctype html" in sample:
        raise SnapshotValidationError("la respuesta es HTML, no OSM XML")
    if b"<!doctype" in raw.lower() or b"<!entity" in raw.lower():
        raise SnapshotValidationError("DOCTYPE y entidades XML no están permitidos")


def _inside_bbox(latitude: float, longitude: float, bbox: Mapping[str, float]) -> bool:
    return bbox["south"] <= latitude <= bbox["north"] and bbox["west"] <= longitude <= bbox["east"]


def validate_osm_xml(
    raw: bytes, max_raw_bytes: int, bbox: Mapping[str, float] | None = None
) -> dict[str, Any]:
    """Valida sintaxis, estructura y clausura de referencias de un OSM XML."""
    if len(raw) > max_raw_bytes:
        raise RawSizeLimitError("el raw supera max_raw_bytes")
    _safe_xml_bytes(raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise SnapshotValidationError("OSM XML truncado o mal formado") from error
    if root.tag != "osm" or root.attrib.get("version") != "0.6":
        raise SnapshotValidationError("la raíz debe ser <osm version='0.6'>")
    if root.findall(".//remark"):
        raise SnapshotValidationError("Overpass devolvió un remark de error")

    elements: dict[str, dict[int, ET.Element]] = {"node": {}, "way": {}, "relation": {}}
    for kind in elements:
        for element in root.findall(kind):
            try:
                identifier = int(element.attrib["id"])
            except (KeyError, ValueError) as error:
                raise SnapshotValidationError(f"{kind} sin ID entero") from error
            if identifier <= 0 or identifier in elements[kind]:
                raise SnapshotValidationError(f"ID inválido o duplicado en {kind}: {identifier}")
            elements[kind][identifier] = element
            if kind == "node":
                try:
                    latitude = float(element.attrib["lat"])
                    longitude = float(element.attrib["lon"])
                except (KeyError, ValueError) as error:
                    raise SnapshotValidationError("node sin coordenadas válidas") from error
                if not math.isfinite(latitude) or not math.isfinite(longitude):
                    raise SnapshotValidationError("coordenadas node no finitas")
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    raise SnapshotValidationError("coordenadas node fuera de rango")

    counts: dict[str, Any] = {kind: len(values) for kind, values in elements.items()}
    if any(value < 1 for value in counts.values()):
        raise SnapshotValidationError("el snapshot debe contener node, way y relation")
    for way in elements["way"].values():
        for nd in way.findall("nd"):
            try:
                reference = int(nd.attrib["ref"])
            except (KeyError, ValueError) as error:
                raise SnapshotValidationError("nd ref no es entero") from error
            if reference not in elements["node"]:
                raise SnapshotValidationError(f"nd ref ausente: {reference}")
    unresolved = {"node": 0, "way": 0, "relation": 0}
    resolved = {"node": 0, "way": 0, "relation": 0}
    for relation in elements["relation"].values():
        for member in relation.findall("member"):
            kind = member.attrib.get("type")
            role = member.attrib.get("role")
            if kind not in elements or role is None:
                raise SnapshotValidationError("member de relation sin type/role válido")
            try:
                reference = int(member.attrib["ref"])
            except (KeyError, ValueError) as error:
                raise SnapshotValidationError("member ref no es entero") from error
            if reference <= 0:
                raise SnapshotValidationError("member ref debe ser positivo")
            if reference in elements[kind]:
                resolved[kind] += 1
            else:
                unresolved[kind] += 1
    counts["resolved_relation_members"] = resolved
    counts["unresolved_relation_members"] = unresolved
    if bbox is not None:
        local_nodes = sum(
            _inside_bbox(float(node.attrib["lat"]), float(node.attrib["lon"]), bbox)
            for node in elements["node"].values()
        )
        nodes_referenced_by_ways = {
            int(nd.attrib["ref"])
            for way in elements["way"].values()
            for nd in way.findall("nd")
        }
        counts["selected_objects"] = {
            "node_bbox": local_nodes,
            "way_bbox_intersection": counts["way"],
            "relation_context": counts["relation"],
        }
        counts["added_way_nodes"] = sum(
            reference in elements["node"]
            and not _inside_bbox(
                float(elements["node"][reference].attrib["lat"]),
                float(elements["node"][reference].attrib["lon"]),
                bbox,
            )
            for reference in nodes_referenced_by_ways
        )
    return counts


def _default_transport(
    endpoint: str,
    body: bytes,
    headers: Mapping[str, str],
    connect_timeout: float,
    total_timeout: float,
) -> TransportResponse:
    started = time.monotonic()
    parsed = urllib.parse.urlsplit(endpoint)
    connection = http.client.HTTPSConnection(
        parsed.hostname,
        parsed.port or 443,
        timeout=min(connect_timeout, total_timeout),
    )
    try:
        connection.request("POST", parsed.path or "/", body=body, headers=dict(headers))
        response = connection.getresponse()
    except (OSError, http.client.HTTPException) as error:
        connection.close()
        raise NetworkTransportError("fallo al establecer conexión HTTP") from error

    def chunks() -> Iterable[bytes]:
        try:
            while True:
                remaining = total_timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("timeout HTTP total")
                try:
                    if connection.sock is not None:
                        connection.sock.settimeout(min(connect_timeout, remaining))
                    chunk = response.read(64 * 1024)
                except (OSError, http.client.HTTPException) as error:
                    raise NetworkTransportError("fallo durante el streaming HTTP") from error
                if not chunk:
                    break
                yield chunk
        finally:
            connection.close()

    return TransportResponse(response.status, dict(response.getheaders()), chunks())


def _retry_after_seconds(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (parsed - now).total_seconds())


def acquire_raw(
    acquisition: Mapping[str, Any],
    query: str,
    destination: Path,
    *,
    transport: Transport = _default_transport,
    sleep: Sleep = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> tuple[int, dict[str, str], int]:
    """Descarga a un `.part` aplicando exactamente la política de D048."""
    validate_endpoint(acquisition["endpoint"])
    body = urllib.parse.urlencode({"data": query}).encode("ascii")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/xml,text/xml",
        "User-Agent": acquisition["user_agent"],
    }
    max_attempts = 1 + acquisition["max_retries"]
    backoffs = acquisition["backoff_seconds"]
    for attempt in range(1, max_attempts + 1):
        try:
            response = transport(
                acquisition["endpoint"], body, headers,
                acquisition["connect_timeout_seconds"],
                acquisition["http_total_timeout_seconds"],
            )
            if response.status >= 400:
                error = urllib.error.HTTPError(
                    acquisition["endpoint"], response.status, "Overpass HTTP error",
                    response.headers, None,
                )
                raise error
            total = 0
            with destination.open("xb") as output:
                for chunk in response.chunks:
                    total += len(chunk)
                    if total > acquisition["max_raw_bytes"]:
                        raise RawSizeLimitError("el raw supera max_raw_bytes")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            return response.status, dict(response.headers), attempt
        except RawSizeLimitError:
            destination.unlink(missing_ok=True)
            raise
        except (
            TimeoutError, socket.timeout, ssl.SSLError, ConnectionError,
            http.client.IncompleteRead, NetworkTransportError,
            urllib.error.URLError, urllib.error.HTTPError,
        ) as error:
            destination.unlink(missing_ok=True)
            status = error.code if isinstance(error, urllib.error.HTTPError) else None
            retryable = status in RETRYABLE_STATUS_CODES or not isinstance(error, urllib.error.HTTPError)
            if not retryable or attempt == max_attempts:
                raise SnapshotError(f"adquisición Overpass fallida tras {attempt} intento(s)") from error
            retry_after = None
            if isinstance(error, urllib.error.HTTPError):
                retry_after = _retry_after_seconds(error.headers.get("Retry-After"), now())
            delay = min(retry_after, acquisition["retry_after_max_seconds"]) if retry_after is not None else backoffs[attempt - 1]
            sleep(delay)
    raise AssertionError("bucle de reintentos inalcanzable")


def build_snapshot_provenance(
    *, config: Mapping[str, Any], query: str, raw: bytes, counts: Mapping[str, int],
    acquired_at: datetime, attempts: int, http_status: int, content_type: str | None,
) -> dict[str, Any]:
    raw_hash = sha256_bytes(raw)
    document = {
        "schema_version": "1.0",
        "osm_snapshot_id": snapshot_id(config["region"]["name"], "osmxml", raw_hash),
        "region_id": config["region"]["name"],
        "provider": config["osm_acquisition"]["provider"],
        "endpoint": config["osm_acquisition"]["endpoint"],
        "acquired_at_utc": acquired_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "bbox": dict(config["region"]["bbox"]),
        "query": query,
        "query_sha256": sha256_bytes(query.encode("utf-8")),
        "raw_format": "osmxml",
        "raw_size_bytes": len(raw),
        "raw_sha256": raw_hash,
        "acquirer_version": config["osm_acquisition"]["acquirer_version"],
        "counts": dict(counts),
        "attempts": attempts,
        "http": {"status": http_status, "content_type": content_type},
        "license": "ODbL-1.0",
        "attribution": OSM_ATTRIBUTION,
        "selection": {
            "nodes": "bbox",
            "ways": "bbox_intersection",
            "relations": "direct_parent_of_local_node_or_way",
        },
        "closure": {
            "ways": "all_referenced_nodes",
            "relations": "not_expanded",
        },
    }
    validate_document(document, "osm_snapshot")
    return document


def _validate_existing_content(
    snapshot_dir: Path, expected_hash: str, raw: bytes
) -> dict[str, Any]:
    source = snapshot_dir / "source.osm"
    provenance_path = snapshot_dir / "provenance.json"
    checksum_path = snapshot_dir / "sha256.txt"
    if not source.is_file() or not provenance_path.is_file() or not checksum_path.is_file():
        raise SnapshotConflictError("snapshot existente incompleto")
    actual = sha256_bytes(raw)
    if actual != expected_hash or checksum_path.read_text(encoding="ascii").strip() != expected_hash:
        raise SnapshotConflictError("snapshot existente con hash inconsistente")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        validate_document(provenance, "osm_snapshot")
    except (OSError, json.JSONDecodeError, SchemaValidationError) as error:
        raise SnapshotConflictError("provenance existente inválida") from error
    if provenance["raw_sha256"] != expected_hash or provenance["raw_size_bytes"] != len(raw):
        raise SnapshotConflictError("provenance existente no corresponde al raw")
    if provenance["osm_snapshot_id"] != snapshot_dir.name:
        raise SnapshotConflictError("osm_snapshot_id existente no corresponde al directorio")
    if snapshot_hash_from_id(snapshot_dir.name) != expected_hash:
        raise SnapshotConflictError("directorio existente no corresponde al hash raw")
    if sha256_bytes(provenance["query"].encode("utf-8")) != provenance["query_sha256"]:
        raise SnapshotConflictError("hash de consulta existente inconsistente")
    try:
        counts = validate_osm_xml(raw, len(raw), provenance["bbox"])
    except SnapshotValidationError as error:
        raise SnapshotConflictError("raw existente estructuralmente inválido") from error
    if counts != provenance["counts"]:
        raise SnapshotConflictError("conteos de provenance inconsistentes")
    return provenance


def _validate_existing(snapshot_dir: Path, expected_hash: str) -> bool:
    source = snapshot_dir / "source.osm"
    if not source.is_file():
        raise SnapshotConflictError("snapshot existente incompleto")
    _validate_existing_content(snapshot_dir, expected_hash, source.read_bytes())
    return True


def validate_local_snapshot(snapshot_dir: str | Path) -> tuple[dict[str, Any], bytes]:
    """Valida un snapshot F2 local y devuelve los mismos bytes comprobados."""
    path = Path(snapshot_dir)
    try:
        expected_hash = snapshot_hash_from_id(path.name)
    except ValueError as error:
        raise SnapshotConflictError("el directorio no tiene un osm_snapshot_id válido") from error
    source = path / "source.osm"
    if not source.is_file():
        raise SnapshotConflictError("snapshot existente incompleto")
    raw = source.read_bytes()
    provenance = _validate_existing_content(path, expected_hash, raw)
    return provenance, raw


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_snapshot(
    *, raw_part: Path, snapshots_root: Path, provenance: Mapping[str, Any]
) -> tuple[Path, bool]:
    """Publica un snapshot sin reemplazar destinos existentes."""
    validate_document(provenance, "osm_snapshot")
    raw = raw_part.read_bytes()
    actual_hash = sha256_bytes(raw)
    if actual_hash != provenance["raw_sha256"] or len(raw) != provenance["raw_size_bytes"]:
        raise SnapshotConflictError("raw temporal no corresponde a la provenance")
    if snapshot_hash_from_id(provenance["osm_snapshot_id"]) != actual_hash:
        raise SnapshotConflictError("osm_snapshot_id no corresponde al raw temporal")
    if validate_osm_xml(raw, len(raw), provenance["bbox"]) != provenance["counts"]:
        raise SnapshotConflictError("conteos de provenance no corresponden al raw temporal")
    snapshot_name = provenance["osm_snapshot_id"]
    final_dir = snapshots_root / snapshot_name
    if final_dir.exists():
        return final_dir, _validate_existing(final_dir, provenance["raw_sha256"])
    snapshots_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=snapshots_root))
    lock_dir = snapshots_root / f".{snapshot_name}.lock"
    lock_acquired = False
    try:
        source = temp_dir / "source.osm"
        os.replace(raw_part, source)
        provenance_path = temp_dir / "provenance.json"
        checksum_path = temp_dir / "sha256.txt"
        provenance_path.write_text(canonical_json(provenance) + "\n", encoding="utf-8")
        checksum_path.write_text(provenance["raw_sha256"] + "\n", encoding="ascii")
        for path in (source, provenance_path, checksum_path):
            with path.open("rb") as file:
                os.fsync(file.fileno())
        _fsync_directory(temp_dir)
        try:
            lock_dir.mkdir()
        except FileExistsError:
            raise SnapshotConflictError("otra publicación del snapshot está en curso")
        lock_acquired = True
        if final_dir.exists():
            _validate_existing(final_dir, provenance["raw_sha256"])
            shutil.rmtree(temp_dir)
            return final_dir, True
        temp_dir.rename(final_dir)
        _fsync_directory(snapshots_root)
        return final_dir, False
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        if lock_acquired:
            lock_dir.rmdir()


def acquire_snapshot(
    config: Mapping[str, Any], snapshots_root: Path, *,
    expected_snapshot_id: str | None = None,
    transport: Transport = _default_transport,
    sleep: Sleep = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> tuple[Path, bool]:
    """Adquiere, valida y publica un snapshot. Los tests inyectan el transporte."""
    acquisition = config["osm_acquisition"]
    if expected_snapshot_id is not None:
        expected_hash = snapshot_hash_from_id(expected_snapshot_id)
        existing = snapshots_root / expected_snapshot_id
        if not existing.exists():
            raise SnapshotConflictError("el snapshot solicitado no existe en caché")
        _validate_existing(existing, expected_hash)
        return existing, True
    query = build_overpass_query(config["region"]["bbox"], acquisition["server_timeout_seconds"])
    snapshots_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=".acquire-", dir=snapshots_root))
    part = work_dir / "source.osm.part"
    try:
        status, headers, attempts = acquire_raw(
            acquisition, query, part, transport=transport, sleep=sleep, now=now
        )
        raw = part.read_bytes()
        counts = validate_osm_xml(
            raw, acquisition["max_raw_bytes"], config["region"]["bbox"]
        )
        provenance = build_snapshot_provenance(
            config=config, query=query, raw=raw, counts=counts,
            acquired_at=now(), attempts=attempts, http_status=status,
            content_type=headers.get("Content-Type"),
        )
        result = publish_snapshot(raw_part=part, snapshots_root=snapshots_root, provenance=provenance)
        return result
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
