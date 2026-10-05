"""Transformaciones deterministas WGS84/UTM para el piloto de Madrid."""

from __future__ import annotations

import math


WGS84_A = 6_378_137.0
WGS84_F = 1 / 298.257223563
UTM_SCALE = 0.9996
UTM_ZONE_30_CENTRAL_MERIDIAN = -3.0


def wgs84_to_epsg25830(latitude: float, longitude: float) -> tuple[float, float]:
    """Transforma latitud/longitud WGS84 a ETRS89 / UTM zona 30N."""
    lat = math.radians(latitude)
    lon = math.radians(longitude)
    lon0 = math.radians(UTM_ZONE_30_CENTRAL_MERIDIAN)
    eccentricity_sq = WGS84_F * (2 - WGS84_F)
    second_eccentricity_sq = eccentricity_sq / (1 - eccentricity_sq)
    n = WGS84_A / math.sqrt(1 - eccentricity_sq * math.sin(lat) ** 2)
    t = math.tan(lat) ** 2
    c = second_eccentricity_sq * math.cos(lat) ** 2
    a = math.cos(lat) * (lon - lon0)
    meridian = WGS84_A * (
        (1 - eccentricity_sq / 4 - 3 * eccentricity_sq**2 / 64 - 5 * eccentricity_sq**3 / 256) * lat
        - (3 * eccentricity_sq / 8 + 3 * eccentricity_sq**2 / 32 + 45 * eccentricity_sq**3 / 1024) * math.sin(2 * lat)
        + (15 * eccentricity_sq**2 / 256 + 45 * eccentricity_sq**3 / 1024) * math.sin(4 * lat)
        - (35 * eccentricity_sq**3 / 3072) * math.sin(6 * lat)
    )
    easting = 500_000 + UTM_SCALE * n * (
        a + (1 - t + c) * a**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * second_eccentricity_sq) * a**5 / 120
    )
    northing = UTM_SCALE * (
        meridian + n * math.tan(lat) * (
            a**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * a**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * second_eccentricity_sq) * a**6 / 720
        )
    )
    return easting, northing


def epsg25830_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """Transforma ETRS89 / UTM zona 30N a latitud/longitud WGS84."""
    eccentricity_sq = WGS84_F * (2 - WGS84_F)
    second_eccentricity_sq = eccentricity_sq / (1 - eccentricity_sq)
    e1 = (1 - math.sqrt(1 - eccentricity_sq)) / (1 + math.sqrt(1 - eccentricity_sq))
    x = easting - 500_000
    m = northing / UTM_SCALE
    mu = m / (
        WGS84_A
        * (1 - eccentricity_sq / 4 - 3 * eccentricity_sq**2 / 64 - 5 * eccentricity_sq**3 / 256)
    )
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    n1 = WGS84_A / math.sqrt(1 - eccentricity_sq * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = second_eccentricity_sq * math.cos(phi1) ** 2
    r1 = WGS84_A * (1 - eccentricity_sq) / (1 - eccentricity_sq * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * UTM_SCALE)
    latitude = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * second_eccentricity_sq) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * second_eccentricity_sq - 3 * c1**2) * d**6 / 720
    )
    longitude = math.radians(UTM_ZONE_30_CENTRAL_MERIDIAN) + (
        d - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * second_eccentricity_sq + 24 * t1**2) * d**5 / 120
    ) / math.cos(phi1)
    return math.degrees(latitude), math.degrees(longitude)
