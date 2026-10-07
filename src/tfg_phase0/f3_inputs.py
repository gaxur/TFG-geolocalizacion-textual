"""Carga local, inmutable y no geométrica de los inputs de Fase 3."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import xml.etree.ElementTree as ET

from .catalog import GENERATOR_VERSION, catalog_grid_identity, iter_catalog_candidates
from .config import load_region_config
from .osm_snapshot import SnapshotConflictError, sha256_bytes, validate_local_snapshot
from .provenance import sha256_json
from .validation import SchemaValidationError, validate_document


D049_RULES_SHA256 = "cf81018ba820557c59c2c27de7ea6b314009abed040cd11249e94ed1a3a10583"
D049_RULES_SIZE = 2753
D049_RULES_POLICY = "way_is_area-v1"
D049_RULES_RELEASE = "v0.9.2"
D049_RULES_COMMIT = "069a46416629ddbe84390c7a3ccc600fe73ee706"


class F3InputError(ValueError):
    """Un input local de F3 no cumple su contrato o no es coherente."""


@dataclass(frozen=True)
class CandidateInput:
    candidate_id: str
    latitude: float
    longitude: float
    center_easting_m: float
    center_northing_m: float
    row: int
    column: int
    cell_ring_wgs84: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class OSMNodeInput:
    osm_id: int
    latitude: float
    longitude: float
    tags: tuple[tuple[str, str], ...]
    source_role: str


@dataclass(frozen=True)
class OSMWayInput:
    osm_id: int
    ordered_node_refs: tuple[int, ...]
    tags: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class OSMMemberInput:
    member_type: str
    ref: int
    role: str
    present: bool


@dataclass(frozen=True)
class OSMRelationInput:
    osm_id: int
    tags: tuple[tuple[str, str], ...]
    members: tuple[OSMMemberInput, ...]


@dataclass(frozen=True)
class CatalogInput:
    path: Path
    size_bytes: int
    sha256: str
    manifest_id: str
    region_id: str
    catalog_version: str
    spacing_m: int
    cell_size_m: int
    source_crs: str
    projected_crs: str
    grid_hash: str
    region_bbox_wgs84: Mapping[str, float]
    provenance: Mapping[str, Any]
    candidates: tuple[CandidateInput, ...]


@dataclass(frozen=True)
class SnapshotInput:
    directory: Path
    source_path: Path
    provenance_path: Path
    osm_snapshot_id: str
    raw_sha256: str
    raw_size_bytes: int
    raw: bytes
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class OSMInventory:
    nodes: tuple[OSMNodeInput, ...]
    ways: tuple[OSMWayInput, ...]
    relations: tuple[OSMRelationInput, ...]


@dataclass(frozen=True)
class D049RulesInput:
    path: Path
    size_bytes: int
    sha256: str
    policy: str
    release: str
    commit: str
    rules: tuple[tuple[str, str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class VerifiedF3Inputs:
    catalog: CatalogInput
    snapshot: SnapshotInput
    inventory: OSMInventory
    rules: D049RulesInput
    config_sha256: str
    config_canonical_sha256: str


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise F3InputError(f"{label} no existe o no es un fichero: {path}")
        return path.read_bytes()
    except OSError as error:
        raise F3InputError(f"no se pudo leer {label}: {path}") from error


def _load_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise F3InputError(f"{label} no es JSON UTF-8 válido") from error


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise F3InputError(f"{field} debe ser un número finito")
    return float(value)


def _validate_finite_bbox(bbox: Mapping[str, Any], context: str) -> None:
    for field in ("north", "south", "east", "west"):
        _finite(bbox[field], f"{context}.{field}")


def _tags(element: ET.Element, context: str) -> tuple[tuple[str, str], ...]:
    values: dict[str, str] = {}
    for tag in element.findall("tag"):
        key = tag.attrib.get("k")
        value = tag.attrib.get("v")
        if key is None or value is None:
            raise F3InputError(f"{context} contiene un tag incompleto")
        if key in values:
            raise F3InputError(f"{context} contiene el tag duplicado {key!r}")
        values[key] = value
    return tuple(sorted(values.items()))


def load_verified_catalog(manifest_path: str | Path, config: Mapping[str, Any]) -> CatalogInput:
    """Carga y verifica un manifest F1 materializado sin regenerarlo."""
    path = Path(manifest_path)
    raw = _read_bytes(path, "manifest F1")
    document = _load_json(raw, "manifest F1")
    try:
        validate_document(document, "manifest")
    except SchemaValidationError as error:
        raise F3InputError("manifest F1 inválido") from error

    generation = document["generation"]
    _validate_finite_bbox(config["region"]["bbox"], "config.region.bbox")
    _validate_finite_bbox(generation["region_bbox_wgs84"], "manifest.generation.region_bbox_wgs84")
    expected_manifest_id = (
        f"{document['catalog_version']}-s{generation['spacing_m']}"
        f"-l{generation['cell_size_m']}"
    )
    if document["manifest_id"] != expected_manifest_id:
        raise F3InputError("manifest_id no corresponde a catálogo, spacing y tamaño")
    if document["osm_snapshot_id"] is not None:
        raise F3InputError("F3 requiere un manifest F1 inmutable y no vinculado")
    expected_generation = {
        "region_bbox_wgs84": config["region"]["bbox"],
        "source_crs": config["region"]["crs"],
        "projected_crs": config["catalog"]["projected_crs"],
        "border_policy": config["catalog"]["border_policy"],
        "generator_version": GENERATOR_VERSION,
    }
    if document["region_id"] != config["region"]["name"]:
        raise F3InputError("region_id de F1 no coincide con la configuración")
    if document["catalog_version"] != config["catalog"]["catalog_version"]:
        raise F3InputError("catalog_version de F1 no coincide con la configuración")
    if any(generation[field] != expected for field, expected in expected_generation.items()):
        raise F3InputError("parámetros de generación F1 incompatibles con la configuración")
    grid_identity = catalog_grid_identity(
        config,
        spacing_m=generation["spacing_m"],
        cell_size_m=generation["cell_size_m"],
    )
    if generation["grid_hash"] != sha256_json(grid_identity)[:12]:
        raise F3InputError("grid_hash de F1 no corresponde a sus parámetros")
    if document["provenance"]["artifact_id"] != document["manifest_id"]:
        raise F3InputError("artifact_id de provenance no coincide con manifest_id")
    if document["provenance"]["parameters_hash"] != sha256_json(generation):
        raise F3InputError("parameters_hash de F1 no corresponde a generation")
    if document["provenance"]["input_hashes"].get("region_config") != sha256_json(config):
        raise F3InputError("hash canónico de configuración en F1 no coincide")
    if document["provenance"]["code_version"] != GENERATOR_VERSION:
        raise F3InputError("code_version de F1 no soportada")

    if not document["candidates"]:
        raise F3InputError("manifest F1 sin candidatos")
    candidates = []
    seen_positions = set()
    seen_centers = set()
    sentinel = object()
    expected_candidates = iter_catalog_candidates(
        config,
        spacing_m=generation["spacing_m"],
        cell_size_m=generation["cell_size_m"],
        grid_hash=generation["grid_hash"],
    )
    for item, expected in zip_longest(
        document["candidates"], expected_candidates, fillvalue=sentinel
    ):
        if item is sentinel:
            raise F3InputError("manifest F1 incompleto: falta una celda determinista")
        if expected is sentinel:
            raise F3InputError("manifest F1 contiene una celda extra")
        generation_item = item["generation"]
        compared_fields = (
            "candidate_id", "latitude", "longitude", "cell_geometry", "generation",
        )
        if any(item[field] != expected[field] for field in compared_fields):
            raise F3InputError("candidato F1 no corresponde a la celda determinista")
        position = (generation_item["row"], generation_item["column"])
        if position in seen_positions:
            raise F3InputError("fila y columna de candidato duplicadas")
        seen_positions.add(position)
        metric_center = (
            generation_item["center_easting_m"],
            generation_item["center_northing_m"],
        )
        if metric_center in seen_centers:
            raise F3InputError("centro métrico de candidato duplicado")
        seen_centers.add(metric_center)
        ring = tuple(
            (_finite(point[0], "cell longitude"), _finite(point[1], "cell latitude"))
            for point in item["cell_geometry"]["coordinates"][0]
        )
        candidates.append(CandidateInput(
            candidate_id=item["candidate_id"],
            latitude=_finite(item["latitude"], "candidate latitude"),
            longitude=_finite(item["longitude"], "candidate longitude"),
            center_easting_m=_finite(generation_item["center_easting_m"], "candidate easting"),
            center_northing_m=_finite(generation_item["center_northing_m"], "candidate northing"),
            row=generation_item["row"],
            column=generation_item["column"],
            cell_ring_wgs84=ring,
        ))
    return CatalogInput(
        path=path,
        size_bytes=len(raw),
        sha256=sha256_bytes(raw),
        manifest_id=document["manifest_id"],
        region_id=document["region_id"],
        catalog_version=document["catalog_version"],
        spacing_m=generation["spacing_m"],
        cell_size_m=generation["cell_size_m"],
        source_crs=generation["source_crs"],
        projected_crs=generation["projected_crs"],
        grid_hash=generation["grid_hash"],
        region_bbox_wgs84=_freeze(generation["region_bbox_wgs84"]),
        provenance=_freeze(document["provenance"]),
        candidates=tuple(candidates),
    )


def load_verified_snapshot(snapshot_dir: str | Path) -> SnapshotInput:
    """Carga metadata de un snapshot F2 después de validarlo solo localmente."""
    path = Path(snapshot_dir)
    try:
        provenance, raw = validate_local_snapshot(path)
    except (OSError, SnapshotConflictError) as error:
        raise F3InputError("snapshot F2 local inválido") from error
    return SnapshotInput(
        directory=path,
        source_path=path / "source.osm",
        provenance_path=path / "provenance.json",
        osm_snapshot_id=provenance["osm_snapshot_id"],
        raw_sha256=provenance["raw_sha256"],
        raw_size_bytes=provenance["raw_size_bytes"],
        raw=raw,
        provenance=_freeze(provenance),
    )


def parse_osm_inventory(source: str | Path | bytes, bbox: Mapping[str, float]) -> OSMInventory:
    """Parsea identidad, tags y referencias OSM sin construir geometrías."""
    raw = source if isinstance(source, bytes) else _read_bytes(Path(source), "source.osm")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise F3InputError("source.osm no es XML válido") from error
    if root.tag != "osm" or root.attrib.get("version") != "0.6":
        raise F3InputError("source.osm no tiene una raíz OSM 0.6 válida")

    node_elements: dict[int, ET.Element] = {}
    way_elements: dict[int, ET.Element] = {}
    relation_elements: dict[int, ET.Element] = {}
    for name, target in (("node", node_elements), ("way", way_elements), ("relation", relation_elements)):
        for element in root.findall(name):
            try:
                osm_id = int(element.attrib["id"])
            except (KeyError, ValueError) as error:
                raise F3InputError(f"{name} sin ID entero") from error
            if osm_id <= 0 or osm_id in target:
                raise F3InputError(f"ID {name} inválido o duplicado: {osm_id}")
            target[osm_id] = element

    way_node_refs = set()
    ways = []
    for osm_id in sorted(way_elements):
        element = way_elements[osm_id]
        try:
            refs = tuple(int(nd.attrib["ref"]) for nd in element.findall("nd"))
        except (KeyError, ValueError) as error:
            raise F3InputError(f"way/{osm_id} contiene un nd ref inválido") from error
        if any(ref <= 0 or ref not in node_elements for ref in refs):
            raise F3InputError(f"way/{osm_id} contiene un nd ref ausente")
        way_node_refs.update(refs)
        ways.append(OSMWayInput(osm_id=osm_id, ordered_node_refs=refs, tags=_tags(element, f"way/{osm_id}")))

    nodes = []
    for osm_id in sorted(node_elements):
        element = node_elements[osm_id]
        try:
            latitude = _finite(float(element.attrib["lat"]), f"node/{osm_id}.lat")
            longitude = _finite(float(element.attrib["lon"]), f"node/{osm_id}.lon")
        except (KeyError, ValueError) as error:
            raise F3InputError(f"node/{osm_id} no tiene coordenadas válidas") from error
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise F3InputError(f"node/{osm_id} tiene coordenadas fuera de rango")
        inside = bbox["south"] <= latitude <= bbox["north"] and bbox["west"] <= longitude <= bbox["east"]
        if not inside and osm_id not in way_node_refs:
            raise F3InputError(f"node/{osm_id} exterior no justificado por un way")
        nodes.append(OSMNodeInput(
            osm_id=osm_id,
            latitude=latitude,
            longitude=longitude,
            tags=_tags(element, f"node/{osm_id}"),
            source_role="node_bbox" if inside else "added_way_node",
        ))

    present_ids = {
        "node": set(node_elements),
        "way": set(way_elements),
        "relation": set(relation_elements),
    }
    relations = []
    for osm_id in sorted(relation_elements):
        element = relation_elements[osm_id]
        members = []
        for member in element.findall("member"):
            member_type = member.attrib.get("type")
            role = member.attrib.get("role")
            if member_type not in present_ids or role is None:
                raise F3InputError(f"relation/{osm_id} contiene un member inválido")
            try:
                ref = int(member.attrib["ref"])
            except (KeyError, ValueError) as error:
                raise F3InputError(f"relation/{osm_id} contiene un member ref inválido") from error
            if ref <= 0:
                raise F3InputError(f"relation/{osm_id} contiene un member ref no positivo")
            members.append(OSMMemberInput(
                member_type=member_type,
                ref=ref,
                role=role,
                present=ref in present_ids[member_type],
            ))
        relations.append(OSMRelationInput(
            osm_id=osm_id,
            tags=_tags(element, f"relation/{osm_id}"),
            members=tuple(members),
        ))

    return OSMInventory(nodes=tuple(nodes), ways=tuple(ways), relations=tuple(relations))


def load_d049_rules(rules_path: str | Path) -> D049RulesInput:
    """Verifica y carga la tabla D049 fijada, sin aplicar sus reglas."""
    path = Path(rules_path)
    raw = _read_bytes(path, "reglas D049")
    if len(raw) != D049_RULES_SIZE or sha256_bytes(raw) != D049_RULES_SHA256:
        raise F3InputError("las reglas D049 no coinciden con la revisión aprobada")
    document = _load_json(raw, "reglas D049")
    if not isinstance(document, list):
        raise F3InputError("las reglas D049 deben ser una lista")
    result = []
    seen_keys = set()
    for entry in document:
        if not isinstance(entry, Mapping) or set(entry) not in ({"key", "polygon"}, {"key", "polygon", "values"}):
            raise F3InputError("entrada D049 inválida")
        key = entry.get("key")
        policy = entry.get("polygon")
        values = entry.get("values", [])
        if not isinstance(key, str) or not key or key in seen_keys:
            raise F3InputError("key D049 inválida o duplicada")
        if policy not in {"all", "whitelist", "blacklist"}:
            raise F3InputError("política D049 inválida")
        if policy == "all" and "values" in entry:
            raise F3InputError("una regla D049 all no debe declarar values")
        if policy != "all" and (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value for value in values)
            or len(values) != len(set(values))
        ):
            raise F3InputError("values D049 inválidos")
        seen_keys.add(key)
        result.append((key, policy, tuple(values)))
    return D049RulesInput(
        path=path,
        size_bytes=len(raw),
        sha256=sha256_bytes(raw),
        policy=D049_RULES_POLICY,
        release=D049_RULES_RELEASE,
        commit=D049_RULES_COMMIT,
        rules=tuple(result),
    )


def load_verified_f3_inputs(
    *, manifest_path: str | Path, snapshot_dir: str | Path,
    config_path: str | Path, rules_path: str | Path,
) -> VerifiedF3Inputs:
    """Construye la frontera F3.2 verificada sin geometría ni persistencia."""
    config_file = Path(config_path)
    config_raw = _read_bytes(config_file, "configuración")
    try:
        config = load_region_config(config_file)
    except SchemaValidationError as error:
        raise F3InputError("configuración inválida") from error
    _validate_finite_bbox(config["region"]["bbox"], "config.region.bbox")
    catalog = load_verified_catalog(manifest_path, config)
    snapshot = load_verified_snapshot(snapshot_dir)
    provenance = snapshot.provenance
    if catalog.region_id != provenance["region_id"]:
        raise F3InputError("F1 y F2 tienen regiones diferentes")
    if dict(config["region"]["bbox"]) != provenance["bbox"]:
        raise F3InputError("bbox de configuración y F2 no coinciden")
    inventory = parse_osm_inventory(snapshot.raw, provenance["bbox"])
    if len(inventory.nodes) != provenance["counts"]["node"]:
        raise F3InputError("inventario de nodes no coincide con provenance F2")
    if len(inventory.ways) != provenance["counts"]["way"]:
        raise F3InputError("inventario de ways no coincide con provenance F2")
    if len(inventory.relations) != provenance["counts"]["relation"]:
        raise F3InputError("inventario de relations no coincide con provenance F2")
    source_roles = {"node_bbox": 0, "added_way_node": 0}
    for node in inventory.nodes:
        source_roles[node.source_role] += 1
    if source_roles["node_bbox"] != provenance["counts"]["selected_objects"]["node_bbox"]:
        raise F3InputError("conteo node_bbox no coincide con provenance F2")
    if source_roles["added_way_node"] != provenance["counts"]["added_way_nodes"]:
        raise F3InputError("conteo added_way_nodes no coincide con provenance F2")
    if sha256_bytes(_read_bytes(snapshot.source_path, "source.osm")) != snapshot.raw_sha256:
        raise F3InputError("source.osm cambió después de su validación")
    rules = load_d049_rules(rules_path)
    return VerifiedF3Inputs(
        catalog=catalog,
        snapshot=snapshot,
        inventory=inventory,
        rules=rules,
        config_sha256=sha256_bytes(config_raw),
        config_canonical_sha256=sha256_json(config),
    )
