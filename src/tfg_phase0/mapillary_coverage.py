"""Adquisición de metadatos y cobertura espacial Mapillary para D004."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .crs import epsg25830_to_wgs84, wgs84_to_epsg25830
from .f4_evaluation import haversine_m


MAPILLARY_API_ROOT = "https://graph.mapillary.com"
INVENTORY_CONTRACT = "mapillary-d004-inventory-v1"
COVERAGE_CONTRACT = "mapillary-d004-coverage-v1"
RADII_M = (10, 25, 50, 100)
FIELDS = (
    "id",
    "geometry",
    "computed_geometry",
    "captured_at",
    "compass_angle",
    "computed_compass_angle",
    "sequence",
    "camera_type",
    "width",
    "height",
    "quality_score",
)


class MapillaryCoverageError(ValueError):
    """El input o resultado de cobertura incumple el contrato local."""


class MapillaryTokenMissingError(MapillaryCoverageError):
    """No existe una credencial autorizada; no debe iniciarse ninguna petición."""


class MapillaryAPIError(MapillaryCoverageError):
    """La API no respondió de forma válida tras aplicar la política de reintentos."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _content_id(prefix: str, document: Mapping[str, Any], excluded: set[str]) -> str:
    identity = {key: value for key, value in document.items() if key not in excluded}
    return prefix + sha256_bytes(canonical_bytes(identity))


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, "REDACTED" if key == "access_token" else value) for key, value in parse_qsl(parts.query)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _safe_next_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "graph.mapillary.com":
        raise MapillaryAPIError("la paginación apunta fuera de graph.mapillary.com")
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "access_token"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _valid_coordinate(latitude: float, longitude: float) -> None:
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise MapillaryCoverageError("coordenada Mapillary no finita")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise MapillaryCoverageError("coordenada Mapillary fuera de rango")


def _perimeter_points(bbox: Mapping[str, float], steps: int = 128) -> list[tuple[float, float]]:
    if steps < 2:
        raise ValueError("steps debe ser al menos 2")
    north, south, east, west = (float(bbox[key]) for key in ("north", "south", "east", "west"))
    if not (south < north and west < east):
        raise MapillaryCoverageError("bbox D004 inválida")
    points = []
    for index in range(steps + 1):
        fraction = index / steps
        latitude = south + (north - south) * fraction
        longitude = west + (east - west) * fraction
        points.extend(((south, longitude), (north, longitude), (latitude, west), (latitude, east)))
    return points


def expand_bbox_projected(bbox: Mapping[str, float], margin_m: float) -> dict[str, Any]:
    """Expande la envolvente proyectada y devuelve una bbox WGS84 conservadora."""
    if not math.isfinite(margin_m) or margin_m < 0:
        raise MapillaryCoverageError("margen de adquisición inválido")
    projected = [wgs84_to_epsg25830(latitude, longitude) for latitude, longitude in _perimeter_points(bbox)]
    min_x = min(point[0] for point in projected) - margin_m
    max_x = max(point[0] for point in projected) + margin_m
    min_y = min(point[1] for point in projected) - margin_m
    max_y = max(point[1] for point in projected) + margin_m
    inverse = []
    for index in range(257):
        fraction = index / 256
        x = min_x + (max_x - min_x) * fraction
        y = min_y + (max_y - min_y) * fraction
        inverse.extend((
            epsg25830_to_wgs84(x, min_y),
            epsg25830_to_wgs84(x, max_y),
            epsg25830_to_wgs84(min_x, y),
            epsg25830_to_wgs84(max_x, y),
        ))
    epsilon = 1e-9
    query_bbox = {
        "north": max(point[0] for point in inverse) + epsilon,
        "south": min(point[0] for point in inverse) - epsilon,
        "east": max(point[1] for point in inverse) + epsilon,
        "west": min(point[1] for point in inverse) - epsilon,
    }
    expansion = {
        "original_bbox_wgs84": {key: float(bbox[key]) for key in ("north", "south", "east", "west")},
        "query_bbox_wgs84": query_bbox,
        "margin_m": float(margin_m),
        "method": "sample_wgs84_bbox_perimeter_to_epsg25830_envelope_expand_inverse_perimeter_v1",
        "projected_crs": "EPSG:25830",
        "projected_envelope": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "perimeter_samples": 512,
        "inverse_perimeter_samples": 1028,
        "sufficiency_verified": False,
    }
    verify_expanded_bbox(expansion)
    expansion["sufficiency_verified"] = True
    return expansion


def verify_expanded_bbox(expansion: Mapping[str, Any]) -> None:
    original = expansion["original_bbox_wgs84"]
    query = expansion["query_bbox_wgs84"]
    margin = float(expansion["margin_m"])
    for latitude, longitude in _perimeter_points(original, steps=64):
        x, y = wgs84_to_epsg25830(latitude, longitude)
        for index in range(72):
            angle = 2 * math.pi * index / 72
            sample_latitude, sample_longitude = epsg25830_to_wgs84(
                x + margin * math.cos(angle), y + margin * math.sin(angle)
            )
            if not (
                query["south"] <= sample_latitude <= query["north"]
                and query["west"] <= sample_longitude <= query["east"]
            ):
                raise MapillaryCoverageError("bbox expandida no contiene el buffer de adquisición")


@dataclass(frozen=True)
class MapillaryClientConfig:
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_seconds: tuple[float, ...] = (1.0, 2.0, 5.0)
    request_interval_seconds: float = 0.25
    max_pages: int = 100
    page_limit: int = 2000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.max_retries < 0 or self.max_pages <= 0:
            raise ValueError("configuración HTTP Mapillary inválida")
        if not 1 <= self.page_limit <= 2000 or self.request_interval_seconds < 0:
            raise ValueError("límites Mapillary inválidos")


class MapillaryClient:
    """Cliente mínimo API v4; nunca incluye el token en mensajes o artefactos."""

    def __init__(
        self,
        token: str | None = None,
        *,
        config: MapillaryClientConfig | None = None,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token = token if token is not None else os.environ.get("MAPILLARY_ACCESS_TOKEN")
        self.config = config or MapillaryClientConfig()
        self._opener = opener
        self._sleeper = sleeper

    def _require_token(self) -> str:
        if not self._token or not self._token.strip():
            raise MapillaryTokenMissingError(
                "MAPILLARY_ACCESS_TOKEN no está configurado; no se realizó ninguna solicitud"
            )
        return self._token.strip()

    def _get_json(self, url: str) -> Mapping[str, Any]:
        token = self._require_token()
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            request = Request(
                url,
                headers={
                    "Authorization": f"OAuth {token}",
                    "Accept": "application/json",
                    "User-Agent": "TFG-geolocalizacion-textual/mapillary-coverage-v1",
                },
                method="GET",
            )
            try:
                with self._opener(request, timeout=self.config.timeout_seconds) as response:
                    payload = response.read()
                document = json.loads(payload.decode("utf-8"))
                if not isinstance(document, Mapping):
                    raise MapillaryAPIError("respuesta Mapillary no es un objeto JSON")
                return document
            except HTTPError as error:
                last_error = error
                retryable = error.code == 429 or 500 <= error.code < 600
                if not retryable or attempt >= self.config.max_retries:
                    raise MapillaryAPIError(
                        f"Mapillary respondió HTTP {error.code} en {_redact_url(url)}"
                    ) from error
            except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as error:
                last_error = error
                if attempt >= self.config.max_retries:
                    raise MapillaryAPIError(
                        f"falló la solicitud Mapillary a {_redact_url(url)}"
                    ) from error
            delay = self.config.backoff_seconds[min(attempt, len(self.config.backoff_seconds) - 1)]
            self._sleeper(delay)
        raise MapillaryAPIError("falló Mapillary") from last_error

    def image_metadata(self, image_id: str, fields: Sequence[str]) -> Mapping[str, Any]:
        if not str(image_id).isdigit():
            raise MapillaryCoverageError("image_id Mapillary inválido")
        allowed = set(FIELDS) | {"creator", "thumb_1024_url", "thumb_2048_url"}
        requested = tuple(dict.fromkeys(fields))
        if not requested or any(field not in allowed for field in requested):
            raise MapillaryCoverageError("campos de imagen Mapillary no permitidos")
        url = f"{MAPILLARY_API_ROOT}/{image_id}?{urlencode({'fields': ','.join(requested)})}"
        return self._get_json(url)

    def download_bytes(self, url: str, *, max_bytes: int = 8_000_000) -> tuple[bytes, str | None]:
        self._require_token()
        parts = urlsplit(url)
        host = (parts.hostname or "").casefold()
        if parts.scheme != "https" or not (host.endswith(".fbcdn.net") or host == "scontent.xx.fbcdn.net"):
            raise MapillaryCoverageError("host de fotografía Mapillary no autorizado")
        if max_bytes <= 0:
            raise MapillaryCoverageError("límite de descarga inválido")
        request = Request(url, headers={"User-Agent": "TFG-geolocalizacion-textual/mapillary-visual-pilot-v1"}, method="GET")
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                content_length = response.headers.get("Content-Length") if hasattr(response, "headers") else None
                if content_length is not None and int(content_length) > max_bytes:
                    raise MapillaryAPIError("fotografía Mapillary supera el límite de bytes")
                media_type = response.headers.get_content_type() if hasattr(response, "headers") else None
                payload = response.read(max_bytes + 1)
        except HTTPError as error:
            raise MapillaryAPIError(f"Mapillary respondió HTTP {error.code} al descargar fotografía") from error
        except (URLError, TimeoutError) as error:
            raise MapillaryAPIError("falló la descarga de fotografía Mapillary") from error
        if len(payload) > max_bytes:
            raise MapillaryAPIError("fotografía Mapillary supera el límite de bytes")
        return payload, media_type

    def inventory(
        self,
        bbox: Mapping[str, float],
        *,
        acquired_at_utc: str | None = None,
        original_bbox: Mapping[str, float] | None = None,
        margin_m: float = 0.0,
        expansion: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._require_token()
        del token
        west, south, east, north = (float(bbox[key]) for key in ("west", "south", "east", "north"))
        if not (west < east and south < north):
            raise MapillaryCoverageError("bbox D004 inválida")
        query = {
            "bbox": f"{west},{south},{east},{north}",
            "fields": ",".join(FIELDS),
            "limit": str(self.config.page_limit),
        }
        url = f"{MAPILLARY_API_ROOT}/images?{urlencode(query)}"
        records: dict[str, dict[str, Any]] = {}
        page_count = 0
        while url is not None:
            if page_count >= self.config.max_pages:
                raise MapillaryAPIError("se alcanzó max_pages antes de terminar la paginación")
            document = self._get_json(_safe_next_url(url))
            page_count += 1
            data = document.get("data")
            if not isinstance(data, list):
                raise MapillaryAPIError("respuesta Mapillary sin lista data")
            for raw in data:
                record = normalize_image_metadata(raw)
                previous = records.get(record["image_id"])
                if previous is not None and previous != record:
                    raise MapillaryAPIError(f"image_id duplicado con metadatos distintos: {record['image_id']}")
                records[record["image_id"]] = record
            paging = document.get("paging") or {}
            if not isinstance(paging, Mapping):
                raise MapillaryAPIError("paging Mapillary inválido")
            next_url = paging.get("next")
            url = _safe_next_url(next_url) if isinstance(next_url, str) and next_url else None
            if url is not None and self.config.request_interval_seconds:
                self._sleeper(self.config.request_interval_seconds)
        acquired = acquired_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = {
            "schema_version": "1.0",
            "contract_version": INVENTORY_CONTRACT,
            "inventory_id": "",
            "provider": "Mapillary API v4",
            "acquired_at_utc": acquired,
            "query": {
                "endpoint": f"{MAPILLARY_API_ROOT}/images",
                "bbox_wgs84": {"north": north, "south": south, "east": east, "west": west},
                "spatial_scope": {
                    "original_bbox_wgs84": dict(original_bbox or bbox),
                    "query_bbox_wgs84": {"north": north, "south": south, "east": east, "west": west},
                    "margin_m": float(margin_m),
                    "expansion": dict(expansion) if expansion is not None else None,
                    "study_region_changed": False,
                    "candidate_set_changed": False,
                },
                "fields": list(FIELDS),
                "page_limit": self.config.page_limit,
                "page_count": page_count,
                "network_policy": {
                    "timeout_seconds": self.config.timeout_seconds,
                    "max_retries": self.config.max_retries,
                    "backoff_seconds": list(self.config.backoff_seconds),
                    "request_interval_seconds": self.config.request_interval_seconds,
                    "max_pages": self.config.max_pages,
                },
                "authentication": "MAPILLARY_ACCESS_TOKEN via Authorization header; not persisted",
                "images_downloaded": False,
                "ground_truth_used": False,
            },
            "license": {
                "identifier": "CC-BY-SA-4.0",
                "source": "https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data",
                "application_terms_status": "conditioned_pending_manual_review",
            },
            "image_count": len(records),
            "images": sorted(records.values(), key=lambda row: row["image_id"]),
        }
        result["inventory_id"] = _content_id("mapillary-d004-inventory-sha256-", result, {"inventory_id"})
        validate_inventory(result)
        return result

    def partitioned_inventory(
        self,
        query_bbox: Mapping[str, float],
        *,
        original_bbox: Mapping[str, float],
        margin_m: float,
        expansion: Mapping[str, Any],
        grid_size: int = 2,
    ) -> dict[str, Any]:
        if not 1 <= grid_size <= 8:
            raise MapillaryCoverageError("grid_size de inventario inválido")
        west, south, east, north = (float(query_bbox[key]) for key in ("west", "south", "east", "north"))
        records: dict[str, dict[str, Any]] = {}
        partitions = []
        for row in range(grid_size):
            for column in range(grid_size):
                tile = {
                    "west": west + (east - west) * column / grid_size,
                    "east": west + (east - west) * (column + 1) / grid_size,
                    "south": south + (north - south) * row / grid_size,
                    "north": south + (north - south) * (row + 1) / grid_size,
                }
                child = self.inventory(tile, original_bbox=original_bbox, margin_m=margin_m, expansion=expansion)
                if child["image_count"] >= self.config.page_limit and child["query"]["page_count"] == 1:
                    raise MapillaryAPIError("partición alcanza page_limit sin paginación verificable; aumente grid_size")
                for image in child["images"]:
                    previous = records.get(image["image_id"])
                    if previous is not None and previous != image:
                        raise MapillaryAPIError(f"image_id conflictivo entre particiones: {image['image_id']}")
                    records[image["image_id"]] = image
                partitions.append({"row": row, "column": column, "bbox_wgs84": tile, "image_count": child["image_count"], "page_count": child["query"]["page_count"], "inventory_id": child["inventory_id"]})
        acquired = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = {
            "schema_version": "1.0",
            "contract_version": INVENTORY_CONTRACT,
            "inventory_id": "",
            "provider": "Mapillary API v4",
            "acquired_at_utc": acquired,
            "query": {
                "endpoint": f"{MAPILLARY_API_ROOT}/images",
                "bbox_wgs84": dict(query_bbox),
                "spatial_scope": {"original_bbox_wgs84": dict(original_bbox), "query_bbox_wgs84": dict(query_bbox), "margin_m": float(margin_m), "expansion": dict(expansion), "study_region_changed": False, "candidate_set_changed": False},
                "fields": list(FIELDS),
                "page_limit": self.config.page_limit,
                "page_count": sum(item["page_count"] for item in partitions),
                "network_policy": {"timeout_seconds": self.config.timeout_seconds, "max_retries": self.config.max_retries, "backoff_seconds": list(self.config.backoff_seconds), "request_interval_seconds": self.config.request_interval_seconds, "max_pages": self.config.max_pages},
                "partitioning": {"grid_size": grid_size, "partition_count": len(partitions), "partitions": partitions, "all_partitions_below_page_limit": True},
                "authentication": "MAPILLARY_ACCESS_TOKEN via Authorization header; not persisted",
                "images_downloaded": False,
                "ground_truth_used": False,
            },
            "license": {"identifier": "CC-BY-SA-4.0", "source": "https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data", "application_terms_status": "conditioned_pending_manual_review"},
            "image_count": len(records),
            "images": sorted(records.values(), key=lambda item: item["image_id"]),
        }
        result["inventory_id"] = _content_id("mapillary-d004-inventory-sha256-", result, {"inventory_id"})
        validate_inventory(result)
        return result


def normalize_image_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or raw.get("id") is None:
        raise MapillaryAPIError("imagen Mapillary sin id")
    geometry = raw.get("computed_geometry") or raw.get("geometry")
    if not isinstance(geometry, Mapping) or geometry.get("type") != "Point":
        raise MapillaryAPIError("imagen Mapillary sin geometría Point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, Sequence) or isinstance(coordinates, (str, bytes)) or len(coordinates) < 2:
        raise MapillaryAPIError("coordenadas Mapillary inválidas")
    longitude, latitude = float(coordinates[0]), float(coordinates[1])
    _valid_coordinate(latitude, longitude)

    def finite_optional(name: str) -> float | None:
        value = raw.get(name)
        if value is None:
            return None
        parsed = float(value)
        if not math.isfinite(parsed):
            raise MapillaryAPIError(f"{name} no finito")
        return parsed

    angle = finite_optional("computed_compass_angle")
    angle_source = "computed_compass_angle"
    if angle is None:
        angle = finite_optional("compass_angle")
        angle_source = "compass_angle" if angle is not None else None
    if angle is not None:
        angle %= 360.0
    captured = raw.get("captured_at")
    if captured is not None:
        try:
            captured = int(captured)
        except (TypeError, ValueError) as error:
            raise MapillaryAPIError("captured_at Mapillary inválido") from error
    width, height = raw.get("width"), raw.get("height")
    width = int(width) if width is not None else None
    height = int(height) if height is not None else None
    if width is not None and width <= 0 or height is not None and height <= 0:
        raise MapillaryAPIError("resolución Mapillary inválida")
    return {
        "image_id": str(raw["id"]),
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_source": "computed_geometry" if raw.get("computed_geometry") else "geometry",
        "captured_at_epoch_ms": captured,
        "orientation_degrees": angle,
        "orientation_source": angle_source,
        "sequence_id": str(raw["sequence"]) if raw.get("sequence") is not None else None,
        "camera_type": raw.get("camera_type"),
        "width_px": width,
        "height_px": height,
        "quality_score": finite_optional("quality_score"),
    }


def validate_inventory(document: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "contract_version", "inventory_id", "provider", "acquired_at_utc",
        "query", "license", "image_count", "images",
    }
    if set(document) != required or document.get("contract_version") != INVENTORY_CONTRACT:
        raise MapillaryCoverageError("inventario Mapillary no cumple el contrato")
    images = document.get("images")
    if not isinstance(images, list) or document.get("image_count") != len(images):
        raise MapillaryCoverageError("conteo del inventario Mapillary inconsistente")
    ids = [row.get("image_id") for row in images if isinstance(row, Mapping)]
    if len(ids) != len(images) or len(ids) != len(set(ids)) or ids != sorted(ids):
        raise MapillaryCoverageError("image_id ausente, duplicado o desordenado")
    if document["query"].get("ground_truth_used") is not False or document["query"].get("images_downloaded") is not False:
        raise MapillaryCoverageError("el inventario debe ser metadata-only y sin GT")
    for row in images:
        _valid_coordinate(float(row["latitude"]), float(row["longitude"]))
    expected = _content_id("mapillary-d004-inventory-sha256-", document, {"inventory_id"})
    if document.get("inventory_id") != expected:
        raise MapillaryCoverageError("inventory_id no corresponde al contenido")


def _age_days(captured_at_ms: int | None, acquired_at: datetime) -> float | None:
    if captured_at_ms is None:
        return None
    captured = datetime.fromtimestamp(captured_at_ms / 1000, tz=timezone.utc)
    return max(0.0, (acquired_at - captured).total_seconds() / 86400)


def _orientation_bins(images: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    angles = [float(row["orientation_degrees"]) for row in images if row.get("orientation_degrees") is not None]
    bins = sorted({int((angle % 360) // 45) for angle in angles})
    return {"available_count": len(angles), "occupied_45_degree_bins": bins, "bin_count": len(bins)}


def _candidate_radius(candidate: Mapping[str, Any], images: Sequence[Mapping[str, Any]], radius: int, acquired_at: datetime) -> dict[str, Any]:
    nearby = []
    for image in images:
        distance = haversine_m(
            float(candidate["latitude"]), float(candidate["longitude"]),
            float(image["latitude"]), float(image["longitude"]),
        )
        if distance <= radius:
            nearby.append((distance, image))
    nearby.sort(key=lambda item: (item[0], item[1]["image_id"]))
    ages = [age for _, image in nearby if (age := _age_days(image.get("captured_at_epoch_ms"), acquired_at)) is not None]
    positions = {(round(float(image["latitude"]), 6), round(float(image["longitude"]), 6)) for _, image in nearby}
    sequences = {image["sequence_id"] for _, image in nearby if image.get("sequence_id") is not None}
    return {
        "covered": bool(nearby),
        "nearest_image_distance_m": nearby[0][0] if nearby else None,
        "image_count": len(nearby),
        "distinct_camera_position_count": len(positions),
        "distinct_sequence_count": len(sequences),
        "orientation_diversity": _orientation_bins([image for _, image in nearby]),
        "age_days": {
            "available_count": len(ages),
            "newest": min(ages) if ages else None,
            "oldest": max(ages) if ages else None,
        },
    }


def _candidate_rows(candidates: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any], acquired_at: datetime) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        rows.append({
            "candidate_id": candidate["candidate_id"],
            "latitude": float(candidate["latitude"]),
            "longitude": float(candidate["longitude"]),
            "radii": {str(radius): _candidate_radius(candidate, inventory["images"], radius, acquired_at) for radius in RADII_M},
            "visual_utility": "not_measured_metadata_only",
        })
    return rows


def _summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    return {
        str(radius): {
            "candidate_count": count,
            "covered_count": sum(row["radii"][str(radius)]["covered"] for row in rows),
            "covered_fraction": sum(row["radii"][str(radius)]["covered"] for row in rows) / count if count else None,
            "visual_utility_measured": False,
        }
        for radius in RADII_M
    }


def _parse_acquired_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MapillaryCoverageError("acquired_at_utc inválido") from error
    if parsed.tzinfo is None:
        raise MapillaryCoverageError("acquired_at_utc debe incluir zona horaria")
    return parsed.astimezone(timezone.utc)


def build_coverage(
    inventory: Mapping[str, Any],
    catalogs: Mapping[str, Mapping[str, Any]],
    rankings: Mapping[str, Any],
    *,
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    validate_inventory(inventory)
    acquired_at = _parse_acquired_at(str(inventory["acquired_at_utc"]))
    expected_counts = {"madrid-25m": 1115, "madrid-50m": 253}
    gallery_results = {}
    for gallery_id, expected_count in expected_counts.items():
        catalog = catalogs.get(gallery_id)
        if not isinstance(catalog, Mapping) or not isinstance(catalog.get("candidates"), list):
            raise MapillaryCoverageError(f"falta catálogo {gallery_id}")
        candidates = catalog["candidates"]
        if len(candidates) != expected_count:
            raise MapillaryCoverageError(f"{gallery_id} debe contener {expected_count} candidatos")
        rows = _candidate_rows(candidates, inventory, acquired_at)
        gallery_results[gallery_id] = {
            "manifest_id": catalog["manifest_id"],
            "candidate_count": len(rows),
            "summary": _summary(rows),
            "candidates": rows,
        }

    selected = [
        row for row in rankings.get("rows", [])
        if row.get("gallery_id") == "madrid-50m" and row.get("kind") == "en_cartographic"
    ]
    if len(selected) != 15 or {row.get("query_id") for row in selected} != {f"H{number}" for number in range(11, 26)}:
        raise MapillaryCoverageError("rankings H11-H25 esperados no disponibles de forma única")
    catalog50 = {row["candidate_id"]: row for row in catalogs["madrid-50m"]["candidates"]}
    unique_ids = sorted({result["candidate_id"] for row in selected for result in row["results"]})
    if len(unique_ids) != 88:
        raise MapillaryCoverageError("el Top-10 congelado debe contener 88 candidatos únicos")
    if any(candidate_id not in catalog50 for candidate_id in unique_ids):
        raise MapillaryCoverageError("ranking contiene candidato ajeno a madrid-50m")
    unique_rows = _candidate_rows([catalog50[candidate_id] for candidate_id in unique_ids], inventory, acquired_at)
    unique_by_id = {row["candidate_id"]: row for row in unique_rows}
    per_query = []
    for ranking in sorted(selected, key=lambda row: row["query_id"]):
        ids = [result["candidate_id"] for result in ranking["results"]]
        if len(ids) != 10 or len(ids) != len(set(ids)):
            raise MapillaryCoverageError(f"Top-10 inválido para {ranking['query_id']}")
        coverage = {}
        for radius in RADII_M:
            covered = [candidate_id for candidate_id in ids if unique_by_id[candidate_id]["radii"][str(radius)]["covered"]]
            coverage[str(radius)] = {
                "covered_candidate_count": len(covered),
                "covered_fraction": len(covered) / 10,
                "no_spatial_evidence": not covered,
            }
        per_query.append({"query_id": ranking["query_id"], "candidate_ids": ids, "coverage": coverage})
    top10_summary = {
        str(radius): {
            **_summary(unique_rows)[str(radius)],
            "query_count": len(per_query),
            "queries_without_spatial_evidence": sum(row["coverage"][str(radius)]["no_spatial_evidence"] for row in per_query),
            "top10_slots_covered": sum(row["coverage"][str(radius)]["covered_candidate_count"] for row in per_query),
            "top10_slot_count": 150,
        }
        for radius in RADII_M
    }
    result = {
        "schema_version": "1.0",
        "contract_version": COVERAGE_CONTRACT,
        "coverage_id": "",
        "protocol": {
            "version": "mapillary-d004-spatial-coverage-v1",
            "radii_m": list(RADII_M),
            "distance": "haversine_mean_earth_radius_6371008.8m",
            "camera_position_deduplication": "latitude_longitude_rounded_6_decimals",
            "orientation_diversity": "occupied_45_degree_bins",
            "ground_truth_used": False,
            "images_downloaded": False,
            "visual_utility_measured": False,
        },
        "inputs": {
            "inventory_id": inventory["inventory_id"],
            "sha256": dict(input_hashes),
            "ranking_filter": {"gallery_id": "madrid-50m", "kind": "en_cartographic", "query_ids": [f"H{x}" for x in range(11, 26)]},
        },
        "galleries": gallery_results,
        "h11_h25_top10": {
            "unique_candidate_count": len(unique_rows),
            "top10_slot_count": 150,
            "summary": top10_summary,
            "unique_candidates": unique_rows,
            "per_query": per_query,
        },
        "limitations": [
            "spatial_coverage_is_not_visual_utility",
            "metadata_only_no_images_downloaded",
            "field_of_view_not_measured",
            "orientation_does_not_prove_candidate_visibility",
            "mapillary_application_terms_and_coverage_remain_conditioned",
        ],
    }
    result["coverage_id"] = _content_id("mapillary-d004-coverage-sha256-", result, {"coverage_id"})
    validate_coverage(result)
    return result


def validate_coverage(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != COVERAGE_CONTRACT:
        raise MapillaryCoverageError("versión de cobertura no soportada")
    protocol = document.get("protocol") or {}
    if protocol.get("ground_truth_used") is not False or protocol.get("images_downloaded") is not False:
        raise MapillaryCoverageError("la cobertura debe ser metadata-only y sin GT")
    galleries = document.get("galleries") or {}
    if galleries.get("madrid-25m", {}).get("candidate_count") != 1115 or galleries.get("madrid-50m", {}).get("candidate_count") != 253:
        raise MapillaryCoverageError("conteos de galerías inconsistentes")
    top10 = document.get("h11_h25_top10") or {}
    if top10.get("unique_candidate_count") != 88 or top10.get("top10_slot_count") != 150 or len(top10.get("per_query", [])) != 15:
        raise MapillaryCoverageError("conteos H11-H25 inconsistentes")
    for section in [*galleries.values(), top10]:
        for radius in RADII_M:
            summary = section["summary"][str(radius)]
            count = summary["candidate_count"]
            covered = summary["covered_count"]
            expected = covered / count if count else None
            if summary["covered_fraction"] != expected or not 0 <= covered <= count:
                raise MapillaryCoverageError("resumen de cobertura inconsistente")
    expected_id = _content_id("mapillary-d004-coverage-sha256-", document, {"coverage_id"})
    if document.get("coverage_id") != expected_id:
        raise MapillaryCoverageError("coverage_id no corresponde al contenido")


def validate_run_manifest(document: Mapping[str, Any], project_root: str | Path) -> None:
    required = {
        "schema_version", "contract_version", "coverage_id", "ground_truth_used",
        "images_downloaded", "artifacts",
    }
    if set(document) != required or document.get("contract_version") != "mapillary-d004-coverage-manifest-v1":
        raise MapillaryCoverageError("manifest final Mapillary inválido")
    if document["ground_truth_used"] is not False or document["images_downloaded"] is not False:
        raise MapillaryCoverageError("manifest final debe declarar metadata-only y ausencia de GT")
    root = Path(project_root).resolve()
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise MapillaryCoverageError("manifest final sin artefactos")
    for name, artifact in artifacts.items():
        if not isinstance(artifact, Mapping) or set(artifact) != {"logical_path", "sha256", "size_bytes"}:
            raise MapillaryCoverageError(f"entrada de artefacto inválida: {name}")
        path = (root / artifact["logical_path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise MapillaryCoverageError(f"artefacto fuera del proyecto: {name}") from error
        if not path.is_file() or path.is_symlink():
            raise MapillaryCoverageError(f"artefacto inexistente o no regular: {name}")
        if path.stat().st_size != artifact["size_bytes"] or sha256_file(path) != artifact["sha256"]:
            raise MapillaryCoverageError(f"integridad de artefacto incorrecta: {name}")


def render_coverage_markdown(document: Mapping[str, Any]) -> str:
    lines = [
        "# Cobertura espacial Mapillary en D004",
        "",
        f"Inventario: `{document['inputs']['inventory_id']}`",
        "",
        "> Esta medición usa solo metadatos. Cobertura espacial no implica utilidad visual.",
        "",
        "| Conjunto | Candidatos | 10 m | 25 m | 50 m | 100 m |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    sections = [
        ("madrid-25m", document["galleries"]["madrid-25m"]),
        ("madrid-50m", document["galleries"]["madrid-50m"]),
        ("Top-10 H11-H25 únicos", document["h11_h25_top10"]),
    ]
    for label, section in sections:
        count = section["candidate_count"] if "candidate_count" in section else section["unique_candidate_count"]
        values = []
        for radius in RADII_M:
            summary = section["summary"][str(radius)]
            values.append(f"{summary['covered_count']}/{summary['candidate_count']} ({summary['covered_fraction']:.1%})")
        lines.append(f"| {label} | {count} | " + " | ".join(values) + " |")
    lines.extend(["", "## Cobertura por consulta H11-H25", "", "| Consulta | 10 m | 25 m | 50 m | 100 m |", "|---|---:|---:|---:|---:|"])
    for row in document["h11_h25_top10"]["per_query"]:
        values = [str(row["coverage"][str(radius)]["covered_candidate_count"]) for radius in RADII_M]
        lines.append(f"| {row['query_id']} | " + " | ".join(values) + " |")
    lines.extend(["", "## Limitaciones", ""])
    lines.extend(f"- `{value}`" for value in document["limitations"])
    return "\n".join(lines) + "\n"
