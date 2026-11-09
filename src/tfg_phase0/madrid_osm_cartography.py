"""Preparación local, trazable y sin alturas inferidas de cartografía OSM Madrid.

Las dependencias cartográficas se mantienen opcionales para que la aplicación y
los tests CPU existentes no requieran Osmium, Shapely ni un encoder MVT. Véase
``requirements-cartography.txt`` para el entorno aislado de preparación.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Callable

from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.crs import epsg25830_to_wgs84, wgs84_to_epsg25830


CARTOGRAPHY_CONTRACT = "madrid-osm-vector-cartography-v1"
PMTILES_PROFILE = "madrid-osm-explicit-height-v1"
OSM_ATTRIBUTION = (
    "© OpenStreetMap contributors. Datos disponibles bajo la Open Database "
    "License (ODbL). https://www.openstreetmap.org/copyright"
)
F4_SOURCE_RELATIVE = Path("data/raw/osm/f4_sources/madrid-geofabrik-20261014")
F4_SOURCE_SHA256 = "9ef85f5c728a26995712a835a68f0cb30e01a32af6d2a7facd6744f3a3840db8"
F4_SOURCE_SIZE = 85_306_514
F4_SOURCE_ID = f"f4-osm-madrid-geofabrik-sha256-{F4_SOURCE_SHA256}"
DEFAULT_MARGIN_METERS = 250
DEFAULT_MIN_ZOOM = 11
DEFAULT_MAX_ZOOM = 17
MVT_EXTENT = 4096

NUMBER_WITH_OPTIONAL_METERS = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m)?\s*$", re.IGNORECASE
)
BUILDING_NO_VALUES = {"", "no", "false"}


class CartographyInputError(ValueError):
    """Input OSM o provenance no coincide con la identidad esperada."""


def parse_explicit_height_m(value: str | None) -> float | None:
    """Devuelve solo una altura OSM explícita con unidad m o sin unidad.

    No interpreta pies, niveles, rangos, aproximaciones ni texto libre.
    """
    if not value:
        return None
    match = NUMBER_WITH_OPTIONAL_METERS.fullmatch(value)
    if not match:
        return None
    height = float(match.group(1))
    return height if math.isfinite(height) and height > 0 else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tag_value(tags: Any, key: str) -> str | None:
    value = tags.get(key)
    return str(value) if value is not None and str(value).strip() else None


def _is_building(tags: Any) -> bool:
    return any(
        (value := _tag_value(tags, key)) is not None
        and value.strip().lower() not in BUILDING_NO_VALUES
        for key in ("building", "building:part")
    )


def _is_part(tags: Any) -> bool:
    value = _tag_value(tags, "building:part")
    return value is not None and value.strip().lower() not in BUILDING_NO_VALUES


def verify_f4_source(source_dir: Path, config_path: Path) -> dict[str, Any]:
    """Verifica bytes/provenance/ODbL del PBF sin abrir ni modificar el raw."""
    pbf_path = source_dir / "source.osm.pbf"
    provenance_path = source_dir / "provenance.json"
    for path in (pbf_path, provenance_path):
        if not path.is_file():
            raise FileNotFoundError(f"Falta el input cartográfico {path}")

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[2]
    committed_provenance_path = project_root / "config/madrid_f4_osm_source_provenance.json"
    committed_provenance = json.loads(committed_provenance_path.read_text(encoding="utf-8"))
    config = load_region_config(config_path)
    expected = config["region"]["bbox"]
    if provenance.get("raw_format") != "osmpbf":
        raise CartographyInputError("La provenance F4 no declara formato osmpbf")
    if provenance.get("license") != "ODbL-1.0":
        raise CartographyInputError("La provenance F4 no declara ODbL-1.0")
    if provenance.get("source_id") != F4_SOURCE_ID:
        raise CartographyInputError("source_id F4 no coincide con la fuente fijada")
    if provenance.get("raw_sha256") != F4_SOURCE_SHA256:
        raise CartographyInputError("raw_sha256 F4 difiere del source_id fijado")
    actual_size = pbf_path.stat().st_size
    if actual_size != provenance.get("raw_size_bytes") or actual_size != F4_SOURCE_SIZE:
        raise CartographyInputError("Tamaño PBF no coincide con provenance F4")
    actual_sha256 = _sha256(pbf_path)
    if actual_sha256 != F4_SOURCE_SHA256:
        raise CartographyInputError("SHA-256 PBF no coincide con provenance F4")

    bbox = provenance.get("bbox")
    if not isinstance(bbox, dict) or not all(
        isinstance(bbox.get(key), (int, float))
        for key in ("west", "south", "east", "north")
    ):
        raise CartographyInputError("La provenance F4 no contiene bbox numérica")
    if not (
        bbox["west"] <= expected["west"]
        and bbox["south"] <= expected["south"]
        and bbox["east"] >= expected["east"]
        and bbox["north"] >= expected["north"]
    ):
        raise CartographyInputError("La bbox del PBF F4 no cubre D004")
    if provenance.get("data_timestamp_utc") != "2026-10-14T20:21:12Z":
        raise CartographyInputError("Timestamp de datos F4 inesperado")
    for key in (
        "source_id", "raw_sha256", "raw_size_bytes", "bbox", "data_timestamp_utc",
        "license", "resolved_filename", "source_url",
    ):
        if provenance.get(key) != committed_provenance.get(key):
            raise CartographyInputError(f"Provenance F4 local difiere del registro versionado: {key}")

    return {
        "path": pbf_path,
        "logical_path": F4_SOURCE_RELATIVE.as_posix(),
        "provenance_path": provenance_path,
        "provenance": provenance,
        "provenance_sha256": _sha256(provenance_path),
        "sha256": actual_sha256,
        "size_bytes": actual_size,
        "bbox_wgs84": bbox,
        "catalog_bbox_wgs84": expected,
        "license": provenance["license"],
        "attribution": provenance["attribution"],
    }


def build_study_context(bbox: dict[str, float], margin_m: float = DEFAULT_MARGIN_METERS):
    """Construye D004 y su margen en EPSG:25830; no aproxima celdas F1."""
    if not math.isfinite(margin_m) or margin_m < 0 or margin_m > 2_000:
        raise ValueError("El margen cartográfico debe estar entre 0 y 2.000 m")
    try:
        from shapely.geometry import Polygon, box
        from shapely.ops import transform
    except ImportError as error:  # pragma: no cover - entorno opcional
        raise RuntimeError("Instala requirements-cartography.txt en un venv local") from error

    corners = [
        wgs84_to_epsg25830(bbox["south"], bbox["west"]),
        wgs84_to_epsg25830(bbox["south"], bbox["east"]),
        wgs84_to_epsg25830(bbox["north"], bbox["east"]),
        wgs84_to_epsg25830(bbox["north"], bbox["west"]),
    ]
    eastings = [point[0] for point in corners]
    northings = [point[1] for point in corners]
    d004 = box(min(eastings), min(northings), max(eastings), max(northings))
    padded = d004.buffer(margin_m, join_style="mitre") if margin_m else d004

    def inverse_transform(x: Any, y: Any, z: Any = None):
        if hasattr(x, "__iter__"):
            converted = [epsg25830_to_wgs84(float(e), float(n)) for e, n in zip(x, y)]
            xs = [longitude for _, longitude in converted]
            ys = [latitude for latitude, _ in converted]
            return (xs, ys) if z is None else (xs, ys, z)
        latitude, longitude = epsg25830_to_wgs84(float(x), float(y))
        return (longitude, latitude) if z is None else (longitude, latitude, z)

    context_wgs84 = transform(inverse_transform, padded)
    west, south, east, north = context_wgs84.bounds
    map_bounds = {"west": west, "south": south, "east": east, "north": north}
    return {
        "d004_utm": d004,
        "coverage_utm": padded,
        "coverage_wgs84": context_wgs84,
        "map_bounds_wgs84": map_bounds,
        "d004_bbox_wgs84": dict(bbox),
        "margin_m": float(margin_m),
        "crs": "EPSG:25830",
    }


def _height_values(tags: Any) -> tuple[float | None, float | None, str | None]:
    explicit_key = None
    height = None
    for key in ("height", "building:height"):
        value = _tag_value(tags, key)
        parsed = parse_explicit_height_m(value)
        if parsed is not None:
            height, explicit_key = parsed, key
            break
    minimum = parse_explicit_height_m(_tag_value(tags, "min_height"))
    if height is not None and minimum is not None and minimum >= height:
        minimum = None
    return height, minimum, explicit_key


def _classify_area(tags: Any) -> tuple[str, str] | None:
    """Devuelve source-layer y clase semántica para las áreas que se dibujan."""
    if _is_building(tags):
        return "building", "building_part" if _is_part(tags) else "building"
    place = _tag_value(tags, "place")
    if place == "square":
        return "place", "square"
    natural = _tag_value(tags, "natural")
    landuse = _tag_value(tags, "landuse")
    leisure = _tag_value(tags, "leisure")
    waterway = _tag_value(tags, "waterway")
    water = _tag_value(tags, "water")
    if natural in {"water", "bay"} or water is not None or waterway == "riverbank" or landuse == "reservoir":
        return "water", water or natural or waterway or "reservoir"
    if natural in {"wood", "grassland", "scrub", "heath", "wetland"} or landuse in {"forest", "grass", "meadow"}:
        return "landcover", natural or landuse or "vegetation"
    if leisure in {"park", "garden", "playground", "recreation_ground", "nature_reserve", "pitch", "sports_centre"}:
        return "landuse", leisure
    if landuse in {"park", "grass", "meadow", "village_green", "recreation_ground", "cemetery", "allotments", "pedestrian", "commercial", "retail", "industrial", "residential"}:
        return "landuse", landuse
    return None


def _highway_class(tags: Any) -> str | None:
    highway = _tag_value(tags, "highway")
    if highway is None:
        return None
    if highway in {"motorway", "motorway_link"}:
        return "motorway"
    if highway in {"trunk", "trunk_link", "primary", "primary_link"}:
        return "primary"
    if highway in {"secondary", "secondary_link"}:
        return "secondary"
    return "minor"


def collect_local_features(
    pbf_path: Path,
    context: dict[str, Any],
    *,
    source_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lee el PBF y devuelve solo geometrías que intersectan el ámbito de salida."""
    try:
        import osmium
        from shapely import from_wkb
        from shapely.geometry import Point, Polygon
        from shapely.ops import transform, unary_union
    except ImportError as error:  # pragma: no cover - entorno opcional
        raise RuntimeError("Instala requirements-cartography.txt en un venv local") from error

    coverage = context["coverage_utm"]
    d004 = context["d004_utm"]
    coarse_bounds = context["map_bounds_wgs84"]
    wkb_factory = osmium.geom.WKBFactory()
    features: list[dict[str, Any]] = []
    invalid_area_records: list[dict[str, Any]] = []
    unreadable_area_records: list[dict[str, Any]] = []
    member_ways_by_relation: dict[int, set[int]] = defaultdict(set)
    valid_building_relations: set[int] = set()
    counters: Counter[str] = Counter()
    ordered_ids = {"node": 0, "way": 0, "relation": 0}

    def project_geometry(geometry: Any):
        def forward(x: Any, y: Any, z: Any = None):
            if hasattr(x, "__iter__"):
                converted = [wgs84_to_epsg25830(float(lat), float(lon)) for lon, lat in zip(x, y)]
                eastings = [east for east, _ in converted]
                northings = [north for _, north in converted]
                return (eastings, northings) if z is None else (eastings, northings, z)
            easting, northing = wgs84_to_epsg25830(float(y), float(x))
            return (easting, northing) if z is None else (easting, northing, z)
        return transform(forward, geometry)

    def keep_geometry(geometry: Any) -> Any | None:
        if geometry.is_empty or not geometry.is_valid:
            return None
        if not coarse_intersects(geometry):
            return None
        projected = project_geometry(geometry)
        if not projected.intersects(coverage):
            return None
        clipped = projected.intersection(coverage)
        return None if clipped.is_empty else clipped

    def coarse_intersects(geometry: Any) -> bool:
        minx, miny, maxx, maxy = geometry.bounds
        return not (
            maxx < coarse_bounds["west"]
            or minx > coarse_bounds["east"]
            or maxy < coarse_bounds["south"]
            or miny > coarse_bounds["north"]
        )

    def add_feature(
        layer: str,
        source_type: str,
        osm_id: int,
        geometry: Any,
        properties: dict[str, Any],
    ) -> None:
        clipped = keep_geometry(geometry)
        if clipped is None:
            return
        features.append({
            "layer": layer,
            "source_type": source_type,
            "osm_id": int(osm_id),
            "geometry": clipped,
            "properties": {
                **properties,
                "osm_type": source_type,
                "osm_id": int(osm_id),
            },
        })

    class Collector(osmium.SimpleHandler):
        def _check_order(self, kind: str, osm_id: int) -> None:
            counters[f"{kind}_objects"] += 1
            if osm_id < ordered_ids[kind]:
                counters["object_order_violations"] += 1
            ordered_ids[kind] = osm_id

        def node(self, node: Any) -> None:
            self._check_order("node", int(node.id))
            tags = node.tags
            if tags.get("building") or tags.get("building:part"):
                if node.location.valid() and (
                    coarse_bounds["west"] <= node.location.lon <= coarse_bounds["east"]
                    and coarse_bounds["south"] <= node.location.lat <= coarse_bounds["north"]
                ):
                    counters["building_nodes_coarse_bbox_candidates"] += 1
            name = _tag_value(tags, "name")
            place = _tag_value(tags, "place")
            amenity = _tag_value(tags, "amenity")
            tourism = _tag_value(tags, "tourism")
            historic = _tag_value(tags, "historic")
            if not name or not node.location.valid():
                return
            if place not in {"city", "town", "village", "hamlet", "suburb", "neighbourhood", "locality", "square"} and amenity not in {"school", "hospital", "place_of_worship", "townhall", "marketplace"} and tourism not in {"attraction", "museum", "viewpoint"} and not historic:
                return
            add_feature("place", "node", node.id, Point(node.location.lon, node.location.lat), {"name": name, "class": place or amenity or tourism or historic or "place"})
            counters["place_points"] += 1

        def way(self, way: Any) -> None:
            self._check_order("way", int(way.id))
            tags = way.tags
            building = _is_building(tags)
            nodes = list(way.nodes)
            coords = [(node.location.lon, node.location.lat) for node in nodes if node.location.valid()]
            if building and coords:
                minx = min(point[0] for point in coords)
                maxx = max(point[0] for point in coords)
                miny = min(point[1] for point in coords)
                maxy = max(point[1] for point in coords)
                if not (maxx < coarse_bounds["west"] or minx > coarse_bounds["east"] or maxy < coarse_bounds["south"] or miny > coarse_bounds["north"]):
                    counters["building_ways_coarse_bbox_candidates"] += 1
                    closed = len(coords) >= 4 and coords[0] == coords[-1]
                    if closed:
                        counters["closed_building_ways_coarse_bbox_candidates"] += 1
                        try:
                            ring = Polygon(coords)
                            counters["building_way_geometry_valid"] += int(ring.is_valid)
                            counters["building_way_geometry_invalid"] += int(not ring.is_valid)
                        except Exception:
                            counters["building_way_geometry_invalid"] += 1
                    else:
                        counters["open_building_ways_coarse_bbox_candidates"] += 1

            highway_class = _highway_class(tags)
            if highway_class is None or len(coords) < 2:
                return
            try:
                line = from_wkb(wkb_factory.create_linestring(way))
            except Exception:
                counters["invalid_road_geometries"] += 1
                return
            if not coarse_intersects(line):
                return
            if not line.is_valid or line.is_empty:
                counters["invalid_road_geometries"] += 1
                return
            name = _tag_value(tags, "name")
            highway = _tag_value(tags, "highway") or ""
            properties = {"class": highway_class, "highway": highway}
            if name:
                properties["name"] = name
            ref = _tag_value(tags, "ref")
            if ref:
                properties["ref"] = ref
            add_feature("transportation", "way", way.id, line, properties)
            counters["road_geometries"] += 1
            if name:
                add_feature("transportation_name", "way", way.id, line, properties)

        def relation(self, relation: Any) -> None:
            self._check_order("relation", int(relation.id))
            tags = relation.tags
            if not _is_building(tags) or tags.get("type") not in {"multipolygon", "building"}:
                return
            counters["building_relations_in_source"] += 1
            for member in relation.members:
                if member.type == "w":
                    member_ways_by_relation[int(relation.id)].add(int(member.ref))

        def area(self, area: Any) -> None:
            tags = area.tags
            classified = _classify_area(tags)
            if classified is None:
                return
            layer, feature_class = classified
            source_type = "way" if area.from_way() else "relation"
            source_id = int(area.orig_id())
            try:
                geometry = from_wkb(wkb_factory.create_multipolygon(area))
            except Exception as error:
                counters["area_geometry_unreadable_sourcewide"] += 1
                if layer == "building":
                    counters["building_area_geometry_unreadable_sourcewide"] += 1
                unreadable_area_records.append({
                    "source_type": source_type,
                    "osm_id": source_id,
                    "layer": layer,
                    "name": _tag_value(tags, "name"),
                    "error": f"{type(error).__name__}: {error}",
                })
                return
            if not coarse_intersects(geometry):
                return
            if not geometry.is_valid:
                counters["area_geometry_invalid"] += 1
                if layer == "building":
                    counters["building_area_geometry_invalid"] += 1
                invalid_area_records.append({"source_type": source_type, "osm_id": source_id, "layer": layer})
                return
            clipped = keep_geometry(geometry)
            if clipped is None:
                return

            name = _tag_value(tags, "name")
            properties: dict[str, Any] = {"class": feature_class}
            if name:
                properties["name"] = name
            if layer == "building":
                part = _is_part(tags)
                height, base, height_source = _height_values(tags)
                counters["building_area_objects"] += 1
                if source_type == "relation" and not part:
                    valid_building_relations.add(source_id)
                if part:
                    counters["building_parts"] += 1
                    properties["building:part"] = _tag_value(tags, "building:part") or "yes"
                else:
                    properties["building"] = _tag_value(tags, "building") or "yes"
                if _tag_value(tags, "height"):
                    counters["height_tagged_objects"] += 1
                if _tag_value(tags, "building:height"):
                    counters["building_height_tagged_objects"] += 1
                if _tag_value(tags, "building:levels") or _tag_value(tags, "building:levels:aboveground"):
                    counters["building_levels_tagged_objects"] += 1
                if _tag_value(tags, "min_height"):
                    counters["min_height_tagged_objects"] += 1
                if height is not None:
                    properties["height"] = height
                    properties["height_source"] = height_source or "height"
                    counters["explicit_numeric_height_objects"] += 1
                raw_height = _tag_value(tags, "height") or _tag_value(tags, "building:height")
                if raw_height is not None and height is None:
                    properties["height_raw"] = raw_height
                    properties["height_source_raw"] = (
                        "height" if _tag_value(tags, "height") else "building:height"
                    )
                if base is not None:
                    properties["min_height"] = base
                    counters["usable_min_height_objects"] += 1
                raw_minimum = _tag_value(tags, "min_height")
                if raw_minimum is not None and base is None:
                    properties["min_height_raw"] = raw_minimum
                levels = _tag_value(tags, "building:levels")
                aboveground_levels = _tag_value(tags, "building:levels:aboveground")
                if levels is not None:
                    # Kept as a source tag only; it is never interpreted as metres.
                    properties["building:levels"] = levels
                if aboveground_levels is not None:
                    properties["building:levels:aboveground"] = aboveground_levels
                properties["audit_height_tag"] = bool(
                    _tag_value(tags, "height")
                )
                properties["audit_building_height_tag"] = _tag_value(tags, "building:height") is not None
                properties["audit_levels_tag"] = levels is not None
                properties["audit_aboveground_levels_tag"] = aboveground_levels is not None
                properties["audit_min_height_tag"] = _tag_value(tags, "min_height") is not None
            else:
                counters[f"{layer}_areas"] += 1

            features.append({
                "layer": layer,
                "source_type": source_type,
                "osm_id": source_id,
                "geometry": clipped,
                "properties": {
                    **properties,
                    "osm_type": source_type,
                    "osm_id": source_id,
                },
            })
            if layer == "place" and feature_class == "square":
                features.append({
                    "layer": "landuse",
                    "source_type": source_type,
                    "osm_id": source_id,
                    "geometry": clipped,
                    "properties": {
                        "class": "square",
                        **({"name": name} if name else {}),
                        "osm_type": source_type,
                        "osm_id": source_id,
                    },
                })

    Collector().apply_file(str(pbf_path), locations=True, idx="flex_mem")

    # A tagged multipolygon is the single canonical footprint for its member
    # outline ways. Building parts remain separate, meaningful geometries.
    relation_members = set().union(
        *(member_ways_by_relation[relation_id] for relation_id in valid_building_relations)
    ) if valid_building_relations else set()
    filtered: list[dict[str, Any]] = []
    duplicate_member_ways = 0
    for feature in features:
        if (
            feature["layer"] == "building"
            and feature["source_type"] == "way"
            and feature["osm_id"] in relation_members
            and feature["properties"].get("building:part") is None
        ):
            duplicate_member_ways += 1
            continue
        filtered.append(feature)

    # The geometry collection is already clipped to the projected context.
    base_buildings = [
        f["geometry"] for f in filtered
        if f["layer"] == "building" and f["properties"].get("building:part") is None
    ]
    building_parts = [
        f["geometry"] for f in filtered
        if f["layer"] == "building" and f["properties"].get("building:part") is not None
    ]
    all_buildings = base_buildings + building_parts
    d004_area = d004.area
    context_area = coverage.area
    unique_covered = unary_union(all_buildings) if all_buildings else None
    covered_total = unique_covered.area if unique_covered is not None else 0.0
    covered_d004 = unique_covered.intersection(d004).area if unique_covered is not None else 0.0

    base_records = [
        f for f in filtered
        if f["layer"] == "building" and f["properties"].get("building:part") is None
    ]
    explicit = sum("height" in f["properties"] for f in base_records)
    levels_only = sum(
        "height" not in f["properties"]
        and any(k in f["properties"] for k in ("building:levels", "building:levels:aboveground"))
        for f in base_records
    )
    total_base = len(base_records)
    parts_records = [
        f for f in filtered
        if f["layer"] == "building" and f["properties"].get("building:part") is not None
    ]
    def tag_counts(records: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "height": sum(f["properties"].get("audit_height_tag", False) for f in records),
            "building:height": sum(f["properties"].get("audit_building_height_tag", False) for f in records),
            "building:levels": sum(f["properties"].get("audit_levels_tag", False) for f in records),
            "building:levels:aboveground": sum(f["properties"].get("audit_aboveground_levels_tag", False) for f in records),
            "min_height": sum(f["properties"].get("audit_min_height_tag", False) for f in records),
        }

    height_tags = {
        "base_buildings": tag_counts(base_records),
        "building_parts": tag_counts(parts_records),
    }
    for feature in filtered:
        for key in (
            "audit_height_tag",
            "audit_building_height_tag",
            "audit_levels_tag",
            "audit_aboveground_levels_tag",
            "audit_min_height_tag",
        ):
            feature["properties"].pop(key, None)
    stats = {
        "candidate_building_area_geometries": counters["building_area_objects"] + counters["building_area_geometry_invalid"],
        "valid_building_area_geometries": counters["building_area_objects"],
        "base_buildings_after_relation_deduplication": total_base,
        "building_parts": len(parts_records),
        "building_nodes_coarse_bbox_candidates": counters["building_nodes_coarse_bbox_candidates"],
        "building_way_entities_coarse_bbox_candidates": counters["building_ways_coarse_bbox_candidates"],
        "closed_building_way_entities_coarse_bbox_candidates": counters["closed_building_ways_coarse_bbox_candidates"],
        "open_building_way_entities_coarse_bbox_candidates": counters["open_building_ways_coarse_bbox_candidates"],
        "valid_building_way_rings": counters["building_way_geometry_valid"],
        "invalid_building_way_rings": counters["building_way_geometry_invalid"],
        "invalid_building_area_geometries_in_context": counters["building_area_geometry_invalid"],
        "raw_building_relations_in_source": counters["building_relations_in_source"],
        "relation_member_way_areas_deduplicated": duplicate_member_ways,
        "height_tags": height_tags,
        "height_coverage_base_buildings": {
            "denominator": total_base,
            "explicit_numeric_metre_height": explicit,
            "explicit_percent": round(100 * explicit / total_base, 4) if total_base else None,
            "levels_present_no_metre_conversion": levels_only,
            "levels_only_percent": round(100 * levels_only / total_base, 4) if total_base else None,
            "unknown_or_unusable_metre_height": total_base - explicit,
            "unknown_or_unusable_percent": round(100 * (total_base - explicit) / total_base, 4) if total_base else None,
            "min_height_is_not_a_top_height": True,
            "levels_converted_to_meters": False,
        },
        "height_coverage_building_parts": {
            "denominator": len(parts_records),
            "explicit_numeric_metre_height": sum("height" in f["properties"] for f in parts_records),
            "explicit_percent": round(
                100 * sum("height" in f["properties"] for f in parts_records) / len(parts_records), 4
            ) if parts_records else None,
            "height_unknown_or_unusable": sum("height" not in f["properties"] for f in parts_records),
            "levels_converted_to_meters": False,
        },
        "spatial_coverage": {
            "crs": "EPSG:25830",
            "d004_area_m2": round(d004_area, 3),
            "context_area_m2": round(context_area, 3),
            "building_union_area_in_context_m2": round(covered_total, 3),
            "building_union_area_in_d004_m2": round(covered_d004, 3),
            "context_area_coverage_percent": round(100 * covered_total / context_area, 4) if context_area else None,
            "d004_area_coverage_percent": round(100 * covered_d004 / d004_area, 4) if d004_area else None,
            "margin_m": context["margin_m"],
        },
        "interpretation": {
            "building_height_is_measured": False,
            "levels_were_converted_to_meters": False,
            "extrusion_policy": "explicit_numeric_height_only",
            "base_buildings_and_parts_reported_separately": True,
            "relation_member_ways_suppressed_only_when_relation_area_exists": True,
            "context_bbox_wgs84": context["map_bounds_wgs84"],
            "source_scope_note": "F4 regional Geofabrik extract; features clipped to local context only.",
        },
        "feature_counts_by_layer": dict(Counter(f["layer"] for f in filtered)),
        "area_geometry_invalid_total": counters["area_geometry_invalid"],
        "building_area_geometries_unreadable_sourcewide": counters["building_area_geometry_unreadable_sourcewide"],
        "area_geometries_unreadable_sourcewide": counters["area_geometry_unreadable_sourcewide"],
        "invalid_area_geometry_samples": invalid_area_records[:20],
        "unreadable_area_geometry_samples": unreadable_area_records[:20],
        "invalid_road_geometries": counters["invalid_road_geometries"],
        "pbf_object_counts": {
            "node": counters["node_objects"],
            "way": counters["way_objects"],
            "relation": counters["relation_objects"],
            "object_order_violations": counters["object_order_violations"],
        },
    }
    return filtered, stats


def read_f4_pbf_header(pbf_path: Path, provenance: dict[str, Any]) -> dict[str, Any]:
    """Comprueba header, bbox y timestamp usando PyOsmium sin escribir al PBF."""
    try:
        import osmium
        from importlib.metadata import version
    except ImportError as error:  # pragma: no cover - entorno opcional
        raise RuntimeError("Instala requirements-cartography.txt en un venv local") from error
    reader = osmium.io.Reader(str(pbf_path))
    try:
        header = reader.header()
        bounds = header.box()
        observed = {
            "west": float(bounds.bottom_left.lon),
            "south": float(bounds.bottom_left.lat),
            "east": float(bounds.top_right.lon),
            "north": float(bounds.top_right.lat),
        }
        expected = provenance["bbox"]
        for key in observed:
            if not math.isclose(observed[key], float(expected[key]), abs_tol=1e-7):
                raise CartographyInputError(f"Header PBF: bbox {key} no coincide con provenance")
        timestamp = header.get("osmosis_replication_timestamp")
        if timestamp != provenance["data_timestamp_utc"]:
            raise CartographyInputError("Header PBF: timestamp no coincide con provenance")
        return {
            "bbox_wgs84": observed,
            "data_timestamp_utc": timestamp,
            "has_multiple_object_versions": bool(header.has_multiple_object_versions),
            "reader": f"pyosmium {version('osmium')}",
        }
    finally:
        reader.close()


def audit_local_pbf(
    source_dir: Path,
    config_path: Path,
    *,
    margin_m: float = DEFAULT_MARGIN_METERS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verifica identidad PBF, procesa todos sus bloques y audita el área local."""
    source = verify_f4_source(source_dir, config_path)
    header = read_f4_pbf_header(source["path"], source["provenance"])
    context = build_study_context(source["catalog_bbox_wgs84"], margin_m)
    features, stats = collect_local_features(
        source["path"], context, source_id=source["provenance"]["source_id"]
    )
    from importlib.metadata import version
    stats["source"] = {
        "source_id": source["provenance"]["source_id"],
        "path": source["logical_path"],
        "sha256": source["sha256"],
        "provenance_sha256": source["provenance_sha256"],
        "size_bytes": source["size_bytes"],
        "license": source["license"],
        "bbox_wgs84": source["bbox_wgs84"],
        "source_url": source["provenance"]["source_url"],
        "data_timestamp_utc": source["provenance"]["data_timestamp_utc"],
        "header": header,
    }
    stats["toolchain"] = {
        "python": __import__("sys").version.split()[0],
        "osmium": version("osmium"),
        "shapely": version("shapely"),
        "numpy": version("numpy"),
    }
    if stats["pbf_object_counts"]["object_order_violations"]:
        raise CartographyInputError("El PBF parseado no conserva el orden ascendente esperado por tipo")
    return features, stats


def vector_layer_metadata(
    features: list[dict[str, Any]], *, min_zoom: int, max_zoom: int
) -> list[dict[str, Any]]:
    fields: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for feature in features:
        for key, value in feature["properties"].items():
            if isinstance(value, bool):
                fields[feature["layer"]][key].add("Boolean")
            elif isinstance(value, (int, float)):
                fields[feature["layer"]][key].add("Number")
            elif isinstance(value, str):
                fields[feature["layer"]][key].add("String")
    result = []
    for layer in sorted(fields):
        layer_fields = {}
        for field, types in sorted(fields[layer].items()):
            if len(types) == 1:
                layer_fields[field] = next(iter(types))
            else:
                layer_fields[field] = "String"
        result.append({
            "id": layer,
            "description": f"OSM {layer} local, clipped to D004 plus margin",
            "minzoom": min_zoom,
            "maxzoom": max_zoom,
            "fields": layer_fields,
        })
    return result


def validate_pmtiles_archive(path: Path, expected_bounds: dict[str, float]) -> dict[str, Any]:
    """Lee todos los directorios y MVT del archive y valida esquema/cobertura."""
    try:
        import gzip
        import mapbox_vector_tile
        from pmtiles.reader import MmapSource, Reader, all_tiles
        from pmtiles.tile import Compression, TileType
    except ImportError as error:  # pragma: no cover - entorno opcional
        raise RuntimeError("Instala requirements-cartography.txt en un venv local") from error

    with path.open("rb") as source:
        get_bytes = MmapSource(source)
        reader = Reader(get_bytes)
        header = reader.header()
        metadata = reader.metadata()
        if header["version"] != 3 or header["tile_type"] != TileType.MVT:
            raise CartographyInputError("El archive no es PMTiles v3 MVT")
        if header["tile_compression"] != Compression.GZIP:
            raise CartographyInputError("Las teselas MVT no declaran compresión GZIP")
        observed_bounds = {
            "west": header["min_lon_e7"] / 10_000_000,
            "south": header["min_lat_e7"] / 10_000_000,
            "east": header["max_lon_e7"] / 10_000_000,
            "north": header["max_lat_e7"] / 10_000_000,
        }
        if any(
            observed_bounds[key] > expected_bounds[key] + 1e-7
            for key in ("west", "south")
        ) or any(
            observed_bounds[key] < expected_bounds[key] - 1e-7
            for key in ("east", "north")
        ):
            raise CartographyInputError("El header PMTiles no cubre el margen cartográfico")
        vector_layers = metadata.get("vector_layers")
        if not isinstance(vector_layers, list):
            raise CartographyInputError("Faltan vector_layers en metadata PMTiles")
        schema = {layer.get("id"): layer for layer in vector_layers if isinstance(layer, dict)}
        if not {"building", "transportation"}.issubset(schema):
            raise CartographyInputError("PMTiles debe incluir building y transportation")
        if "height" not in schema["building"].get("fields", {}):
            raise CartographyInputError("PMTiles no declara height explícita para edificios")

        counts: Counter[str] = Counter()
        explicit_height_features = 0
        for (zoom, x, y), tile_data in all_tiles(get_bytes):
            try:
                decoded = mapbox_vector_tile.decode(gzip.decompress(tile_data))
            except Exception as error:
                raise CartographyInputError(f"Tesela MVT ilegible z{zoom}/{x}/{y}: {error}") from error
            for layer, body in decoded.items():
                counts[layer] += len(body.get("features", []))
                if layer == "building":
                    for feature in body.get("features", []):
                        height = feature.get("properties", {}).get("height")
                        if isinstance(height, (int, float)) and math.isfinite(height) and height > 0:
                            explicit_height_features += 1
        if not explicit_height_features:
            raise CartographyInputError("No hay extrusiones con altura explícita en las teselas")
        if not all(counts.get(layer, 0) for layer in ("building", "transportation")):
            raise CartographyInputError("Las capas building/transportation no contienen features")
        return {
            "version": header["version"],
            "tile_type": "MVT",
            "tile_compression": "GZIP",
            "bounds_wgs84": observed_bounds,
            "min_zoom": header["min_zoom"],
            "max_zoom": header["max_zoom"],
            "addressed_tiles_count": header["addressed_tiles_count"],
            "tile_entries_count": header["tile_entries_count"],
            "tile_contents_count": header["tile_contents_count"],
            "decoded_feature_counts_by_layer": dict(counts),
            "explicit_height_features_in_tiles": explicit_height_features,
            "vector_layers": vector_layers,
            "metadata_attribution": metadata.get("attribution"),
        }


def _web_mercator_transform_geometry(geometry: Any):
    try:
        from shapely.ops import transform
    except ImportError as error:  # pragma: no cover - entorno opcional
        raise RuntimeError("Instala requirements-cartography.txt en un venv local") from error

    radius = 6_378_137.0
    max_lat = 85.0511287798066

    def project(x: Any, y: Any, z: Any = None):
        def one(easting: float, northing: float) -> tuple[float, float]:
            latitude, longitude = epsg25830_to_wgs84(easting, northing)
            latitude = max(-max_lat, min(max_lat, latitude))
            lon_rad = math.radians(longitude)
            lat_rad = math.radians(latitude)
            return radius * lon_rad, radius * math.log(math.tan(math.pi / 4 + lat_rad / 2))

        if hasattr(x, "__iter__"):
            converted = [one(float(a), float(b)) for a, b in zip(x, y)]
            xs = [point[0] for point in converted]
            ys = [point[1] for point in converted]
            return (xs, ys) if z is None else (xs, ys, z)
        mx, my = one(float(x), float(y))
        return (mx, my) if z is None else (mx, my, z)

    return transform(project, geometry)


def build_mvt_tiles(
    features: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    min_zoom: int = DEFAULT_MIN_ZOOM,
    max_zoom: int = DEFAULT_MAX_ZOOM,
) -> tuple[list[tuple[int, int, int, bytes]], dict[str, Any]]:
    """Codifica vector tiles MVT, recortados al tile, para las capas del perfil."""
    try:
        import gzip
        import mercantile
        import mapbox_vector_tile
        from shapely.geometry import box, mapping
        from shapely.strtree import STRtree
    except ImportError as error:  # pragma: no cover - entorno opcional
        raise RuntimeError("Instala requirements-cartography.txt en un venv local") from error

    if min_zoom < 0 or max_zoom > 17 or min_zoom > max_zoom:
        raise ValueError("Zoom inválido; perfil soportado 0–17")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in features:
        projected = _web_mercator_transform_geometry(feature["geometry"])
        if projected.is_empty or not projected.is_valid:
            continue
        grouped[feature["layer"]].append({**feature, "geometry_3857": projected})

    if not grouped:
        raise ValueError("No quedaron geometrías cartográficas para teselar")

    trees: dict[str, Any] = {}
    geometries: dict[str, list[Any]] = {}
    for layer, layer_features in grouped.items():
        geometries[layer] = [f["geometry_3857"] for f in layer_features]
        trees[layer] = STRtree(geometries[layer])

    bounds = context["map_bounds_wgs84"]
    encoded: list[tuple[int, int, int, bytes]] = []
    quantized_drops: Counter[str] = Counter()
    tile_counts: Counter[int] = Counter()
    for zoom in range(min_zoom, max_zoom + 1):
        for tile in mercantile.tiles(bounds["west"], bounds["south"], bounds["east"], bounds["north"], zoom):
            merc_bounds = mercantile.xy_bounds(tile)
            tile_box = box(merc_bounds.left, merc_bounds.bottom, merc_bounds.right, merc_bounds.top)
            layers_payload: list[dict[str, Any]] = []
            for layer, layer_features in grouped.items():
                indices = trees[layer].query(tile_box, predicate="intersects")
                if not len(indices):
                    continue
                payload_features = []
                for index in indices:
                    record = layer_features[int(index)]
                    clipped = record["geometry_3857"].intersection(tile_box)
                    if clipped.is_empty:
                        continue
                    if clipped.geom_type == "GeometryCollection":
                        wanted = 0 if layer in {"building", "landcover", "landuse", "water"} else (1 if layer in {"transportation", "transportation_name"} else 0)
                        pieces = [g for g in clipped.geoms if g.geom_type in ({"Polygon", "MultiPolygon"} if wanted == 0 else {"LineString", "MultiLineString"}) and not g.is_empty]
                        if not pieces:
                            continue
                        if len(pieces) == 1:
                            clipped = pieces[0]
                        else:
                            from shapely.ops import unary_union
                            clipped = unary_union(pieces)
                    if not clipped.is_valid or clipped.is_empty:
                        continue
                    def quantize(x: Any, y: Any, z: Any = None):
                        xfactor = MVT_EXTENT / (merc_bounds.right - merc_bounds.left)
                        yfactor = MVT_EXTENT / (merc_bounds.top - merc_bounds.bottom)
                        if hasattr(x, "__iter__"):
                            qx = [round(xfactor * (float(value) - merc_bounds.left)) for value in x]
                            qy = [round(yfactor * (merc_bounds.top - float(value))) for value in y]
                            return (qx, qy) if z is None else (qx, qy, z)
                        qx = round(xfactor * (float(x) - merc_bounds.left))
                        qy = round(yfactor * (merc_bounds.top - float(y)))
                        return (qx, qy) if z is None else (qx, qy, z)

                    from shapely.ops import transform as transform_geometry
                    quantized = transform_geometry(quantize, clipped)
                    valid_after_quantization = (
                        not quantized.is_empty
                        and quantized.is_valid
                        and (quantized.geom_type not in {"Polygon", "MultiPolygon"} or quantized.area > 0)
                        and (quantized.geom_type not in {"LineString", "MultiLineString"} or quantized.length > 0)
                    )
                    if not valid_after_quantization:
                        quantized_drops[f"{layer}@z{zoom}"] += 1
                        continue
                    payload_features.append({"geometry": mapping(quantized), "properties": record["properties"]})
                if payload_features:
                    layers_payload.append({"name": layer, "features": payload_features})
            if not layers_payload:
                continue
            mvt = mapbox_vector_tile.encode(
                layers_payload,
                default_options={
                    "extents": MVT_EXTENT,
                    "quantize_bounds": None,
                    "y_coord_down": True,
                    "check_winding_order": True,
                    "on_invalid_geometry": mapbox_vector_tile.encoder.on_invalid_geometry_raise,
                },
            )
            if not mvt:
                continue
            encoded.append((zoom, tile.x, tile.y, gzip.compress(mvt, mtime=0)))
            tile_counts[zoom] += 1
    if not encoded:
        raise ValueError("No se generaron teselas MVT en el ámbito seleccionado")
    return encoded, {
        "extent": MVT_EXTENT,
        "min_zoom_requested": min_zoom,
        "max_zoom_requested": max_zoom,
        "nonempty_tiles_by_zoom": {str(k): tile_counts[k] for k in sorted(tile_counts)},
        "features_dropped_after_tile_quantization": dict(sorted(quantized_drops.items())),
        "quantization_policy": "Mapbox Vector Tile integer extent; collapsed/invalid geometries omitted per zoom, no repair",
    }


def write_pmtiles(
    output_path: Path,
    encoded_tiles: list[tuple[int, int, int, bytes]],
    context: dict[str, Any],
    *,
    source_id: str,
    source_sha256: str,
    feature_stats: dict[str, Any],
) -> dict[str, Any]:
    """Escribe PMTiles v3 MVT sin reemplazar un archivo existente."""
    try:
        from pmtiles.tile import Compression, TileType, zxy_to_tileid
        from pmtiles.writer import Writer
    except ImportError as error:  # pragma: no cover - entorno opcional
        raise RuntimeError("Instala requirements-cartography.txt en un venv local") from error

    output_path = output_path.resolve()
    provenance_path = output_path.with_suffix(output_path.suffix + ".provenance.json")
    if output_path.exists() or provenance_path.exists():
        raise FileExistsError("No se sobrescribe PMTiles ni provenance existentes")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(encoded_tiles, key=lambda tile: zxy_to_tileid(tile[0], tile[1], tile[2]))
    zooms = [tile[0] for tile in ordered]
    bounds = context["map_bounds_wgs84"]
    center = {
        "longitude": (bounds["west"] + bounds["east"]) / 2,
        "latitude": (bounds["south"] + bounds["north"]) / 2,
    }
    center_zoom = min(15, max(zooms))
    vector_layers = feature_stats["vector_layers"]
    metadata = {
        "name": "Madrid D004 · OSM local",
        "description": "Teselas vectoriales locales OSM recortadas a D004 y buffer EPSG:25830.",
        "attribution": OSM_ATTRIBUTION,
        "format": "pbf",
        "bounds": ",".join(str(bounds[k]) for k in ("west", "south", "east", "north")),
        "center": ",".join(str(center[k]) for k in ("longitude", "latitude")) + f",{center_zoom}",
        "minzoom": min(zooms),
        "maxzoom": max(zooms),
        "vector_layers": vector_layers,
        "generator": CARTOGRAPHY_CONTRACT,
    }
    header = {
        "version": 3,
        "tile_type": TileType.MVT,
        "tile_compression": Compression.GZIP,
        "min_zoom": min(zooms),
        "max_zoom": max(zooms),
        "min_lon_e7": round(bounds["west"] * 10_000_000),
        "min_lat_e7": round(bounds["south"] * 10_000_000),
        "max_lon_e7": round(bounds["east"] * 10_000_000),
        "max_lat_e7": round(bounds["north"] * 10_000_000),
        "center_zoom": center_zoom,
        "center_lon_e7": round(center["longitude"] * 10_000_000),
        "center_lat_e7": round(center["latitude"] * 10_000_000),
    }
    temporary = output_path.with_name(f".{output_path.name}.staging")
    if temporary.exists():
        raise FileExistsError(f"No se reutiliza un staging existente: {temporary}")
    try:
        with temporary.open("xb") as sink:
            writer = Writer(sink)
            for zoom, x, y, tile_data in ordered:
                writer.write_tile(zxy_to_tileid(zoom, x, y), tile_data)
            writer.finalize(header, metadata)
        # Rename on the same filesystem; the final name was checked absent above.
        temporary.rename(output_path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    output_sha = _sha256(output_path)
    provenance = {
        "schema_version": "1.0",
        "contract_version": CARTOGRAPHY_CONTRACT,
        "profile": PMTILES_PROFILE,
        "source": {
            "source_id": source_id,
            "source_pbf_sha256": source_sha256,
            "source_provenance_sha256": feature_stats["audit"]["source"]["provenance_sha256"],
            "data_timestamp_utc": feature_stats["audit"]["source"]["data_timestamp_utc"],
            "source_bbox_wgs84": feature_stats["audit"]["source"]["bbox_wgs84"],
            "source_url": feature_stats["audit"]["source"]["source_url"],
            "license": "ODbL-1.0",
            "attribution": OSM_ATTRIBUTION,
        },
        "extent": {
            "crs": "EPSG:4326",
            "construction_crs": "EPSG:25830",
            "bounds_wgs84": bounds,
            "d004_bbox_wgs84": context["d004_bbox_wgs84"],
            "margin_m": context["margin_m"],
        },
        "zoom": {"min": min(zooms), "max": max(zooms)},
        "tile_type": "MVT",
        "tile_compression": "GZIP",
        "layers": vector_layers,
        "feature_audit": feature_stats["audit"],
        "toolchain": feature_stats["toolchain"],
        "pmtiles": {"path": output_path.name, "size_bytes": output_path.stat().st_size, "sha256": output_sha},
    }
    temporary_provenance = provenance_path.with_name(f".{provenance_path.name}.staging")
    if provenance_path.exists() or temporary_provenance.exists():
        raise FileExistsError("No se sobrescribe la provenance PMTiles")
    temporary_provenance.write_text(json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_provenance.rename(provenance_path)
    return provenance
