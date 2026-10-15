"""Geometría determinista Web Mercator y XYZ para el perfil visual F4."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .crs import WGS84_A


WEB_MERCATOR_MAX_LATITUDE = 85.0511287798066
WEB_MERCATOR_HALF_WORLD_M = math.pi * WGS84_A
WEB_MERCATOR_WORLD_M = 2 * WEB_MERCATOR_HALF_WORLD_M


class F4GeometryError(ValueError):
    """Coordenadas o parámetros incompatibles con la geometría F4."""


@dataclass(frozen=True)
class BBox3857:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def as_document(self) -> dict[str, float | str]:
        return {"crs": "EPSG:3857", "min_x": self.min_x, "min_y": self.min_y, "max_x": self.max_x, "max_y": self.max_y}


@dataclass(frozen=True)
class CandidateRasterGeometry:
    center_x: float
    center_y: float
    global_pixel_x: float
    global_pixel_y: float
    request_bbox: BBox3857
    source_mosaic_bbox: BBox3857
    output_bbox: BBox3857
    tile_min_x: int
    tile_min_y: int
    tile_max_x: int
    tile_max_y: int
    mosaic_width_px: int
    mosaic_height_px: int
    candidate_pixel_x: float
    candidate_pixel_y: float
    crop_left_px: float
    crop_top_px: float
    native_meters_per_pixel: float


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise F4GeometryError(f"{name} debe ser finito")
    return float(value)


def wgs84_to_epsg3857(latitude: float, longitude: float) -> tuple[float, float]:
    latitude = _finite(latitude, "latitude")
    longitude = _finite(longitude, "longitude")
    if not -180 <= longitude <= 180 or not -WEB_MERCATOR_MAX_LATITUDE <= latitude <= WEB_MERCATOR_MAX_LATITUDE:
        raise F4GeometryError("coordenada fuera del dominio EPSG:3857")
    x = WGS84_A * math.radians(longitude)
    y = WGS84_A * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
    return x, y


def epsg3857_to_wgs84(x: float, y: float) -> tuple[float, float]:
    x = _finite(x, "x")
    y = _finite(y, "y")
    if abs(x) > WEB_MERCATOR_HALF_WORLD_M or abs(y) > WEB_MERCATOR_HALF_WORLD_M:
        raise F4GeometryError("coordenada fuera del dominio EPSG:3857")
    longitude = math.degrees(x / WGS84_A)
    latitude = math.degrees(2 * math.atan(math.exp(y / WGS84_A)) - math.pi / 2)
    return latitude, longitude


def meters_per_pixel(zoom: int, tile_size_px: int = 256) -> float:
    if isinstance(zoom, bool) or not isinstance(zoom, int) or zoom < 0:
        raise F4GeometryError("zoom debe ser entero no negativo")
    if isinstance(tile_size_px, bool) or not isinstance(tile_size_px, int) or tile_size_px < 1:
        raise F4GeometryError("tile_size_px debe ser entero positivo")
    return WEB_MERCATOR_WORLD_M / (tile_size_px * 2**zoom)


def wgs84_to_global_pixel(latitude: float, longitude: float, zoom: int, tile_size_px: int = 256) -> tuple[float, float]:
    x, y = wgs84_to_epsg3857(latitude, longitude)
    world_px = tile_size_px * 2**zoom
    pixel_x = (x + WEB_MERCATOR_HALF_WORLD_M) / WEB_MERCATOR_WORLD_M * world_px
    pixel_y = (WEB_MERCATOR_HALF_WORLD_M - y) / WEB_MERCATOR_WORLD_M * world_px
    return pixel_x, pixel_y


def global_pixel_to_wgs84(pixel_x: float, pixel_y: float, zoom: int, tile_size_px: int = 256) -> tuple[float, float]:
    pixel_x = _finite(pixel_x, "pixel_x")
    pixel_y = _finite(pixel_y, "pixel_y")
    world_px = tile_size_px * 2**zoom
    if not 0 <= pixel_x <= world_px or not 0 <= pixel_y <= world_px:
        raise F4GeometryError("píxel global fuera del mundo XYZ")
    x = pixel_x / world_px * WEB_MERCATOR_WORLD_M - WEB_MERCATOR_HALF_WORLD_M
    y = WEB_MERCATOR_HALF_WORLD_M - pixel_y / world_px * WEB_MERCATOR_WORLD_M
    return epsg3857_to_wgs84(x, y)


def candidate_raster_geometry(latitude: float, longitude: float, *, zoom: int = 18, tile_size_px: int = 256, crop_size_px: int = 256) -> CandidateRasterGeometry:
    if crop_size_px < 1 or isinstance(crop_size_px, bool):
        raise F4GeometryError("crop_size_px debe ser entero positivo")
    center_x, center_y = wgs84_to_epsg3857(latitude, longitude)
    global_x, global_y = wgs84_to_global_pixel(latitude, longitude, zoom, tile_size_px)
    mpp = meters_per_pixel(zoom, tile_size_px)
    half_crop_m = crop_size_px * mpp / 2
    output_bbox = BBox3857(center_x - half_crop_m, center_y - half_crop_m, center_x + half_crop_m, center_y + half_crop_m)
    # La petición real debe cubrir el crop completo. El valor upstream de 33,6256 m
    # se conserva en el perfil como evidencia, pero no puede limitar la fuente.
    request_bbox = BBox3857(center_x - half_crop_m, center_y - half_crop_m, center_x + half_crop_m, center_y + half_crop_m)

    crop_left_global = global_x - crop_size_px / 2
    crop_top_global = global_y - crop_size_px / 2
    crop_right_global = global_x + crop_size_px / 2
    crop_bottom_global = global_y + crop_size_px / 2
    tile_min_x = math.floor(crop_left_global / tile_size_px)
    tile_min_y = math.floor(crop_top_global / tile_size_px)
    tile_max_x = math.floor(math.nextafter(crop_right_global, -math.inf) / tile_size_px)
    tile_max_y = math.floor(math.nextafter(crop_bottom_global, -math.inf) / tile_size_px)
    tile_count = 2**zoom
    if min(tile_min_x, tile_min_y) < 0 or max(tile_max_x, tile_max_y) >= tile_count:
        raise F4GeometryError("el crop cruza el límite del mundo XYZ")
    mosaic_left_global = tile_min_x * tile_size_px
    mosaic_top_global = tile_min_y * tile_size_px
    mosaic_right_global = (tile_max_x + 1) * tile_size_px
    mosaic_bottom_global = (tile_max_y + 1) * tile_size_px
    source_mosaic_bbox = BBox3857(
        mosaic_left_global * mpp - WEB_MERCATOR_HALF_WORLD_M,
        WEB_MERCATOR_HALF_WORLD_M - mosaic_bottom_global * mpp,
        mosaic_right_global * mpp - WEB_MERCATOR_HALF_WORLD_M,
        WEB_MERCATOR_HALF_WORLD_M - mosaic_top_global * mpp,
    )
    return CandidateRasterGeometry(
        center_x=center_x, center_y=center_y,
        global_pixel_x=global_x, global_pixel_y=global_y,
        request_bbox=request_bbox, source_mosaic_bbox=source_mosaic_bbox, output_bbox=output_bbox,
        tile_min_x=tile_min_x, tile_min_y=tile_min_y, tile_max_x=tile_max_x, tile_max_y=tile_max_y,
        mosaic_width_px=(tile_max_x - tile_min_x + 1) * tile_size_px,
        mosaic_height_px=(tile_max_y - tile_min_y + 1) * tile_size_px,
        candidate_pixel_x=global_x - mosaic_left_global,
        candidate_pixel_y=global_y - mosaic_top_global,
        crop_left_px=crop_left_global - mosaic_left_global,
        crop_top_px=crop_top_global - mosaic_top_global,
        native_meters_per_pixel=mpp,
    )


def bbox_wgs84_to_epsg3857(bbox: Mapping[str, float]) -> BBox3857:
    west_x, south_y = wgs84_to_epsg3857(bbox["south"], bbox["west"])
    east_x, north_y = wgs84_to_epsg3857(bbox["north"], bbox["east"])
    return BBox3857(west_x, south_y, east_x, north_y)


def bbox_contains(container: BBox3857, contained: BBox3857, tolerance_m: float = 1e-6) -> bool:
    return (
        container.min_x <= contained.min_x + tolerance_m
        and container.min_y <= contained.min_y + tolerance_m
        and container.max_x >= contained.max_x - tolerance_m
        and container.max_y >= contained.max_y - tolerance_m
    )
