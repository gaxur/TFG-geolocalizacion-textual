"""Adquisición F5.5 de evidencias Panoramax y preparación de revisión humana."""

from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .crs import wgs84_to_epsg25830
from .f4_evaluation import assign_reference, query_dataset_id
from .f5_ground_truth_evaluation import ground_truth_dataset_id


PANORAMAX_PREFIX = "f55-panoramax-inventory-sha256-"
REVIEW_PREFIX = "f55-panoramax-review-sha256-"
DEFAULT_BBOX = {"west": -3.709, "south": 40.412, "east": -3.699, "north": 40.420}
DEFAULT_ENDPOINT = "https://api.panoramax.xyz/api/search"
LICENSE_ID = "CC-BY-SA-4.0"


class F55EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class DownloadedAsset:
    logical_path: str
    source_url: str
    retrieved_at_utc: str
    size_bytes: int
    sha256: str
    media_type: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def inventory_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "source", "bbox_wgs84", "raw_response", "catalogs", "items", "limitations")}
    return PANORAMAX_PREFIX + sha256_bytes(canonical_bytes(identity))


def review_queue_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "inventory", "selection", "records", "limitations")}
    return REVIEW_PREFIX + sha256_bytes(canonical_bytes(identity))


def fetch_url(url: str, *, user_agent: str, timeout_seconds: int = 60) -> tuple[bytes, Mapping[str, str], int]:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/geo+json,application/json,image/*;q=0.8"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read(), dict(response.headers.items()), response.status
    except (HTTPError, URLError, TimeoutError) as error:
        raise F55EvidenceError(f"falló la adquisición de {url}: {error}") from error


def parse_panoramax_response(raw: bytes, *, endpoint_url: str, retrieved_at_utc: str, catalogs: Mapping[str, Any], bbox: Mapping[str, float] = DEFAULT_BBOX, response_media_type: str = "application/json") -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise F55EvidenceError("respuesta Panoramax no es JSON válido") from error
    if payload.get("type") not in {None, "FeatureCollection"} or not isinstance(payload.get("features"), list):
        raise F55EvidenceError("respuesta Panoramax no contiene una colección de features")
    items, ids = [], set()
    for feature in payload["features"]:
        item = parse_panoramax_item(feature, catalogs=catalogs, bbox=bbox)
        if item["item_id"] in ids:
            raise F55EvidenceError(f"item Panoramax duplicado: {item['item_id']}")
        ids.add(item["item_id"]); items.append(item)
    document = {
        "schema_version": "1.0", "contract_version": "f55-panoramax-inventory-v1", "inventory_id": PANORAMAX_PREFIX + "0" * 64,
        "source": {"provider": "Panoramax federated catalog", "endpoint_url": endpoint_url, "retrieved_at_utc": retrieved_at_utc, "response_sha256": sha256_bytes(raw), "response_size_bytes": len(raw), "response_media_type": response_media_type},
        "bbox_wgs84": dict(bbox),
        "raw_response": {"logical_path": "raw-response.geojson", "sha256": sha256_bytes(raw), "size_bytes": len(raw)},
        "catalogs": {gallery: {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "cell_size_m": catalog.cell_size_m} for gallery, catalog in sorted(catalogs.items())},
        "items": sorted(items, key=lambda row: row["item_id"]),
        "limitations": ["provider_snapshot_can_change", "camera_coordinates_require_human_validation", "camera_azimuth_is_not_automatically_observer_orientation", "missing_accuracy_is_not_inferred"],
    }
    document["inventory_id"] = inventory_id(document)
    return document


def parse_panoramax_item(feature: Mapping[str, Any], *, catalogs: Mapping[str, Any], bbox: Mapping[str, float]) -> dict[str, Any]:
    item_id = feature.get("id")
    geometry = feature.get("geometry")
    if not isinstance(item_id, str) or not item_id or not isinstance(geometry, Mapping) or geometry.get("type") != "Point" or not isinstance(geometry.get("coordinates"), list) or len(geometry["coordinates"]) < 2:
        raise F55EvidenceError("item Panoramax sin ID o Point válido")
    longitude, latitude = geometry["coordinates"][:2]
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (latitude, longitude)) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise F55EvidenceError(f"coordenada Panoramax inválida: {item_id}")
    inside = bbox["west"] <= longitude <= bbox["east"] and bbox["south"] <= latitude <= bbox["north"]
    if not inside:
        raise F55EvidenceError(f"item Panoramax fuera de D004: {item_id}")
    properties = feature.get("properties") if isinstance(feature.get("properties"), Mapping) else {}
    accuracy = properties.get("quality:horizontal_accuracy")
    if accuracy is not None and (not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy) or accuracy < 0):
        raise F55EvidenceError(f"precisión Panoramax inválida: {item_id}")
    azimuth = properties.get("view:azimuth")
    if azimuth is not None and (not isinstance(azimuth, (int, float)) or not math.isfinite(azimuth) or not 0 <= azimuth < 360):
        raise F55EvidenceError(f"azimuth Panoramax inválido: {item_id}")
    license_links = [link for link in feature.get("links", []) if isinstance(link, Mapping) and link.get("rel") == "license"]
    license_id = properties.get("license")
    if license_id != LICENSE_ID or not license_links:
        raise F55EvidenceError(f"item Panoramax sin licencia {LICENSE_ID}: {item_id}")
    assets = {}
    for name in ("thumb", "sd", "hd"):
        value = feature.get("assets", {}).get(name)
        assets[name] = {"url": value.get("href"), "media_type": value.get("type"), "download": None} if isinstance(value, Mapping) and value.get("href") else None
    if assets["thumb"] is None and assets["sd"] is None:
        raise F55EvidenceError(f"item Panoramax sin asset de revisión: {item_id}")
    exif = properties.get("exif") if isinstance(properties.get("exif"), Mapping) else {}
    providers = [{"id": row.get("id"), "name": row.get("name"), "roles": row.get("roles", [])} for row in feature.get("providers", []) if isinstance(row, Mapping)]
    assignments = {}
    for gallery, catalog in sorted(catalogs.items()):
        assignments[gallery] = assign_reference(latitude, longitude, catalog, reported_accuracy_m=accuracy) if accuracy is not None else {"status": "accuracy_unavailable", "candidate_id": None, "center_distance_m": None, "distance_to_cell_boundary_m": None, "boundary_ambiguous": True}
    return {
        "item_id": item_id, "collection_id": feature.get("collection"), "item_url": next((link.get("href") for link in feature.get("links", []) if isinstance(link, Mapping) and link.get("rel") == "self"), None),
        "camera_position": {"latitude": latitude, "longitude": longitude, "crs": "EPSG:4326", "inside_d004": inside, "horizontal_accuracy_m": accuracy, "validation_status": "metadata_only"},
        "captured_at_utc": normalize_utc(properties.get("datetime")), "providers": providers,
        "license": {"identifier": license_id, "url": license_links[0].get("href"), "attribution_required": True, "review_status": "pending"},
        "orientation": {"camera_azimuth_degrees": azimuth, "convention": "degrees_clockwise_from_north" if azimuth is not None else None, "observer_orientation_validated": False},
        "camera": {"manufacturer": properties.get("pers:interior_orientation", {}).get("camera_manufacturer") if isinstance(properties.get("pers:interior_orientation"), Mapping) else None, "model": properties.get("pers:interior_orientation", {}).get("camera_model") if isinstance(properties.get("pers:interior_orientation"), Mapping) else None, "exif_make": exif.get("Exif.Image.Make"), "exif_model": exif.get("Exif.Image.Model")},
        "assets": assets, "catalog_assignments": assignments,
        "source_metadata": {"geovisio_producer": properties.get("geovisio:producer"), "rank_in_collection": properties.get("geovisio:rank_in_collection"), "original_file_name": properties.get("original_file:name"), "original_file_size": properties.get("original_file:size")},
    }


def select_review_items(items: Sequence[Mapping[str, Any]], *, limit: int = 5, max_per_collection: int = 3) -> list[str]:
    if limit < 1 or max_per_collection < 1:
        raise F55EvidenceError("límites de selección no válidos")
    unique = {item["item_id"]: item for item in items}
    if len(unique) != len(items):
        raise F55EvidenceError("no se pueden seleccionar items duplicados")
    candidates = sorted(items, key=lambda row: (-row["camera_position"]["latitude"], row["camera_position"]["longitude"], row["item_id"]))
    if not candidates:
        return []
    selected = [candidates.pop(0)]
    counts = Counter([selected[0].get("collection_id")])
    projected = {item["item_id"]: wgs84_to_epsg25830(item["camera_position"]["latitude"], item["camera_position"]["longitude"]) for item in items}
    while candidates and len(selected) < limit:
        eligible = [item for item in candidates if counts[item.get("collection_id")] < max_per_collection]
        pool = eligible or candidates
        def score(item):
            x, y = projected[item["item_id"]]
            minimum = min(math.hypot(x - projected[row["item_id"]][0], y - projected[row["item_id"]][1]) for row in selected)
            return (-minimum, item["item_id"])
        chosen = min(pool, key=score)
        selected.append(chosen); counts[chosen.get("collection_id")] += 1; candidates.remove(chosen)
    return [item["item_id"] for item in selected]


def build_review_queue(inventory: Mapping[str, Any], selected_ids: Sequence[str]) -> dict[str, Any]:
    by_id = {item["item_id"]: item for item in inventory["items"]}
    if len(selected_ids) != len(set(selected_ids)) or any(value not in by_id for value in selected_ids):
        raise F55EvidenceError("selección de revisión inválida")
    records = []
    for order, item_id in enumerate(selected_ids, 1):
        item = by_id[item_id]
        records.append({
            "selection_order": order, "item_id": item_id, "collection_id": item["collection_id"], "item_url": item["item_url"],
            "camera_position": copy.deepcopy(item["camera_position"]), "captured_at_utc": item["captured_at_utc"], "providers": copy.deepcopy(item["providers"]), "license": copy.deepcopy(item["license"]), "orientation": copy.deepcopy(item["orientation"]), "camera": copy.deepcopy(item["camera"]), "assets": copy.deepcopy(item["assets"]), "catalog_assignments": copy.deepcopy(item["catalog_assignments"]),
            "review": {"status": "pending", "reviewer": None, "reviewed_at_utc": None, "license_verified": False, "camera_position_verified": False, "description_matches_evidence": False, "orientation_usable": False, "orientation_uncertainty_degrees": None, "original_spanish_description": None, "acceptance_reasons": [], "rejection_reasons": [], "notes": None},
        })
    document = {"schema_version": "1.0", "contract_version": "f55-panoramax-review-v1", "review_queue_id": REVIEW_PREFIX + "0" * 64, "inventory": {"inventory_id": inventory["inventory_id"], "sha256": sha256_bytes(canonical_bytes(inventory) + b"\n")}, "selection": {"method": "farthest_point_epsg25830_northwest_seed_v1", "limit": len(selected_ids), "max_per_collection": 3, "uses_model_outputs": False}, "records": records, "limitations": ["all_records_start_pending", "no_automatic_ground_truth_approval", "descriptions_require_human_authorship", "panoramax_camera_is_not_automatically_f54_observer"]}
    document["review_queue_id"] = review_queue_id(document)
    return document


def upgrade_visual_review_queue(queue: Mapping[str, Any], decisions: Mapping[str, Any]) -> dict[str, Any]:
    if queue.get("contract_version") != "f55-panoramax-review-v1":
        raise F55EvidenceError("la revisión visual F5.5b parte de una cola v1")
    output = copy.deepcopy(queue)
    rows = decisions.get("decisions")
    if decisions.get("contract_version") != "f55b-visual-review-decisions-v1" or not isinstance(decisions.get("reviewer"), str) or not decisions["reviewer"].strip() or not isinstance(decisions.get("recorded_at_utc"), str) or not decisions["recorded_at_utc"].endswith("Z") or not isinstance(rows, list):
        raise F55EvidenceError("manifiesto de revisión visual incompatible")
    by_id = {row.get("item_id"): row for row in rows}
    expected = {row["item_id"] for row in output["records"]}
    if set(by_id) != expected or len(by_id) != len(rows):
        raise F55EvidenceError("la revisión visual debe cubrir exactamente la cola")
    for record in output["records"]:
        decision = by_id[record["item_id"]]
        suitability = decision.get("suitability")
        observations = decision.get("visible_observations")
        if suitability not in {"suitable", "limited", "unsuitable"} or not isinstance(observations, list) or not observations or any(not isinstance(value, str) or not value.strip() for value in observations):
            raise F55EvidenceError("decisión visual incompleta")
        description = decision.get("proposed_spanish_description")
        if description is not None and (not isinstance(description, str) or not description.strip()):
            raise F55EvidenceError("descripción propuesta vacía")
        if suitability == "suitable" and not description:
            raise F55EvidenceError("imagen apta sin descripción piloto propuesta")
        record["visual_review"] = {
            "status": "reviewed", "suitability": suitability, "reviewer": decisions["reviewer"], "recorded_at_utc": decisions["recorded_at_utc"],
            "visible_observations": list(observations), "proposed_spanish_description": description,
            "description_final_review_status": "pending" if description else "not_applicable", "benchmark_main_eligible": suitability == "suitable",
            "notes": decision.get("notes"),
        }
        if record["review"]["status"] != "pending":
            raise F55EvidenceError("la revisión visual no puede modificar aprobación GT")
    output["contract_version"] = "f55-panoramax-review-v2"
    output["limitations"] = sorted(set([*output["limitations"], "visual_suitability_does_not_approve_ground_truth", "proposed_descriptions_require_final_review"]))
    output["review_queue_id"] = review_queue_id(output)
    return output


def upgrade_existing_visual_review_queue(queue: Mapping[str, Any], decisions: Mapping[str, Any]) -> dict[str, Any]:
    if queue.get("contract_version") != "f55-panoramax-review-v2" or any(row.get("visual_review", {}).get("status") != "pending" for row in queue.get("records", [])):
        raise F55EvidenceError("la cola complementaria no está pendiente en v2")
    legacy = copy.deepcopy(queue)
    legacy["contract_version"] = "f55-panoramax-review-v1"
    for record in legacy["records"]: record.pop("visual_review", None)
    legacy["review_queue_id"] = review_queue_id(legacy)
    reviewed = upgrade_visual_review_queue(legacy, decisions)
    reviewed["selection"] = copy.deepcopy(queue["selection"])
    reviewed["inventory"] = copy.deepcopy(queue["inventory"])
    reviewed["limitations"] = sorted(set([*queue["limitations"], *reviewed["limitations"]]))
    reviewed["review_queue_id"] = review_queue_id(reviewed)
    return reviewed


def build_complementary_review_queue(inventory: Mapping[str, Any], primary_queue: Mapping[str, Any]) -> dict[str, Any]:
    selected = {row["item_id"] for row in primary_queue["records"]}
    remaining = sorted(item["item_id"] for item in inventory["items"] if item["item_id"] not in selected)
    if len(selected) + len(remaining) != len(inventory["items"]):
        raise F55EvidenceError("cola primaria contiene items ajenos o duplicados")
    output = build_review_queue(inventory, remaining[:5])
    output["contract_version"] = "f55-panoramax-review-v2"
    output["selection"] = {"method": "complement_of_primary_queue_item_id_order_v1", "limit": len(output["records"]), "max_per_collection": None, "uses_model_outputs": False, "primary_review_queue_id": primary_queue["review_queue_id"], "primary_review_queue_sha256": sha256_bytes(canonical_bytes(primary_queue) + b"\n")}
    for record in output["records"]:
        record["visual_review"] = {"status": "pending", "suitability": None, "reviewer": None, "recorded_at_utc": None, "visible_observations": [], "proposed_spanish_description": None, "description_final_review_status": "pending", "benchmark_main_eligible": False, "notes": None}
    output["limitations"] = sorted(set([*output["limitations"], "complementary_batch_not_spatially_selected", "visual_suitability_pending"]))
    output["review_queue_id"] = review_queue_id(output)
    return output


def validate_inventory(document: Mapping[str, Any], catalogs: Mapping[str, Any]) -> dict[str, Any]:
    if document.get("inventory_id") != inventory_id(document):
        raise F55EvidenceError("inventory_id no corresponde al contenido")
    if document.get("source", {}).get("response_sha256") != document.get("raw_response", {}).get("sha256") or document.get("source", {}).get("response_size_bytes") != document.get("raw_response", {}).get("size_bytes"):
        raise F55EvidenceError("provenance raw Panoramax inconsistente")
    ids = [row.get("item_id") for row in document.get("items", [])]
    if len(ids) != len(set(ids)):
        raise F55EvidenceError("inventario Panoramax contiene IDs duplicados")
    for item in document.get("items", []):
        position = item["camera_position"]
        accuracy = position["horizontal_accuracy_m"]
        for gallery, catalog in catalogs.items():
            expected = assign_reference(position["latitude"], position["longitude"], catalog, reported_accuracy_m=accuracy) if accuracy is not None else {"status": "accuracy_unavailable", "candidate_id": None, "center_distance_m": None, "distance_to_cell_boundary_m": None, "boundary_ambiguous": True}
            if item["catalog_assignments"][gallery] != expected:
                raise F55EvidenceError(f"asignación Panoramax inconsistente: {item['item_id']} {gallery}")
    return {"items": len(ids), "collections": len({row.get("collection_id") for row in document.get("items", [])}), "with_horizontal_accuracy": sum(row["camera_position"]["horizontal_accuracy_m"] is not None for row in document.get("items", []))}


def attach_download(queue: dict[str, Any], item_id: str, role: str, asset: DownloadedAsset) -> None:
    record = next((row for row in queue["records"] if row["item_id"] == item_id), None)
    if record is None or role not in {"thumb", "sd"} or record["assets"].get(role) is None:
        raise F55EvidenceError("asset descargado no corresponde a la cola")
    if record["assets"][role]["url"] != asset.source_url:
        raise F55EvidenceError("URL descargada no corresponde al item")
    record["assets"][role]["download"] = asset.__dict__
    queue["review_queue_id"] = review_queue_id(queue)


def download_review_asset(url: str, destination: Path, *, logical_path: str, user_agent: str, timeout_seconds: int = 60) -> DownloadedAsset:
    raw, headers, status = fetch_url(url, user_agent=user_agent, timeout_seconds=timeout_seconds)
    if status != 200 or not raw:
        raise F55EvidenceError(f"asset vacío o HTTP {status}")
    media_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise F55EvidenceError(f"media type de asset no permitido: {media_type}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != raw:
        raise F55EvidenceError(f"asset existente incompatible: {destination}")
    destination.write_bytes(raw)
    return DownloadedAsset(logical_path, url, utc_now(), len(raw), sha256_bytes(raw), media_type)


def validate_review_queue(queue: Mapping[str, Any]) -> dict[str, int]:
    if queue["review_queue_id"] != review_queue_id(queue):
        raise F55EvidenceError("review_queue_id no corresponde al contenido")
    counts = Counter(); downloaded_hashes = {}
    contract = queue.get("contract_version")
    if contract not in {"f55-panoramax-review-v1", "f55-panoramax-review-v2"}:
        raise F55EvidenceError("versión de cola Panoramax no soportada")
    for record in queue["records"]:
        visual = record.get("visual_review")
        if contract == "f55-panoramax-review-v1" and visual is not None:
            raise F55EvidenceError("cola v1 contiene revisión visual v2")
        if contract == "f55-panoramax-review-v2":
            _validate_visual_review(visual)
        for role in ("thumb", "sd"):
            value = record["assets"].get(role)
            if value and value.get("download"):
                digest = value["download"].get("sha256")
                if not _is_sha256(digest):
                    raise F55EvidenceError("asset descargado sin SHA-256 válido")
                previous = downloaded_hashes.setdefault(digest, record["item_id"])
                if previous != record["item_id"]:
                    raise F55EvidenceError("evidencia visual duplicada entre items")
        status = record["review"]["status"]
        counts[status] += 1
        if status == "pending":
            if record["review"]["reviewer"] is not None or record["review"]["reviewed_at_utc"] is not None:
                raise F55EvidenceError("registro pending contiene aprobación")
        elif status == "approved":
            review = record["review"]
            if not review["reviewer"] or not review["reviewed_at_utc"] or not review["license_verified"] or not review["camera_position_verified"] or not review["description_matches_evidence"] or not review["original_spanish_description"] or not review["acceptance_reasons"]:
                raise F55EvidenceError("aprobación Panoramax incompleta")
            if not any(value.get("download") for key, value in record["assets"].items() if value and key in {"thumb", "sd"}):
                raise F55EvidenceError("aprobación sin evidencia visual descargada")
            if review["orientation_usable"] and (review["orientation_uncertainty_degrees"] is None or not 0 <= review["orientation_uncertainty_degrees"] <= 180):
                raise F55EvidenceError("orientación usable sin incertidumbre angular")
        elif status == "rejected":
            if not record["review"]["reviewer"] or not record["review"]["reviewed_at_utc"] or not record["review"]["rejection_reasons"]:
                raise F55EvidenceError("rechazo Panoramax incompleto")
        else:
            raise F55EvidenceError(f"estado de revisión no válido: {status}")
    return {key: counts[key] for key in ("pending", "approved", "rejected")}


def _validate_visual_review(visual: Any) -> None:
    fields = {"status", "suitability", "reviewer", "recorded_at_utc", "visible_observations", "proposed_spanish_description", "description_final_review_status", "benchmark_main_eligible", "notes"}
    if not isinstance(visual, Mapping) or set(visual) != fields or visual["status"] not in {"pending", "reviewed"} or not isinstance(visual["benchmark_main_eligible"], bool):
        raise F55EvidenceError("revisión visual v2 incompatible")
    if visual["status"] == "pending":
        if visual["suitability"] is not None or visual["reviewer"] is not None or visual["recorded_at_utc"] is not None or visual["visible_observations"] or visual["proposed_spanish_description"] is not None or visual["benchmark_main_eligible"]:
            raise F55EvidenceError("revisión visual pending contiene valoración")
        return
    if visual["suitability"] not in {"suitable", "limited", "unsuitable"} or not visual["reviewer"] or not str(visual["recorded_at_utc"]).endswith("Z") or not visual["visible_observations"]:
        raise F55EvidenceError("revisión visual reviewed incompleta")
    if visual["benchmark_main_eligible"] != (visual["suitability"] == "suitable"):
        raise F55EvidenceError("aptitud principal inconsistente")
    expected_description_status = "pending" if visual["proposed_spanish_description"] else "not_applicable"
    if visual["description_final_review_status"] != expected_description_status:
        raise F55EvidenceError("estado de descripción propuesta inconsistente")


def render_review_html(queue: Mapping[str, Any], output: Path) -> None:
    cards = []
    for record in queue["records"]:
        asset = next((value for role in ("sd", "thumb") if (value := record["assets"].get(role)) and value.get("download")), None)
        image = f'<img src="{escape(asset["download"]["logical_path"])}" alt="Evidencia {escape(record["item_id"])}">' if asset else "<p>Asset no descargado.</p>"
        assignments = "".join(f"<li>{escape(gallery)}: <code>{escape(value['status'])}</code></li>" for gallery, value in sorted(record["catalog_assignments"].items()))
        visual = record.get("visual_review")
        visual_html = ""
        if visual:
            observations = "".join(f"<li>{escape(value)}</li>" for value in visual["visible_observations"])
            description = f'<blockquote>{escape(visual["proposed_spanish_description"])}</blockquote>' if visual["proposed_spanish_description"] else ""
            visual_html = f'<h3>Revisión visual: {escape(visual["status"])}</h3><p>Aptitud: <strong>{escape(str(visual["suitability"]))}</strong>; elegible benchmark principal: {visual["benchmark_main_eligible"]}</p><ul>{observations}</ul>{description}'
        cards.append(f'<article><h2>{record["selection_order"]}. <code>{escape(record["item_id"])}</code></h2>{image}<ul><li>Captura: {escape(str(record["captured_at_utc"]))}</li><li>Posición: {record["camera_position"]["latitude"]}, {record["camera_position"]["longitude"]}</li><li>Precisión: {escape(str(record["camera_position"]["horizontal_accuracy_m"]))} m</li><li>Azimut cámara: {escape(str(record["orientation"]["camera_azimuth_degrees"]))}°</li>{assignments}<li>Licencia: <a href="{escape(record["license"]["url"] or "#")}">{escape(record["license"]["identifier"] or "ausente")}</a></li></ul>{visual_html}<p>Aprobación GT: <strong>{escape(record["review"]["status"])}</strong></p></article>')
    html = "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\"><title>Revisión Panoramax F5.5</title><style>body{font:16px system-ui;max-width:1100px;margin:auto;padding:2rem;background:#f4f1e8;color:#18201d}article{background:white;padding:1.2rem;margin:1rem 0;border-left:6px solid #b84b2d}img{max-width:100%;height:auto}code{overflow-wrap:anywhere}</style></head><body><h1>Cola Panoramax F5.5</h1><p>Todos los registros comienzan pendientes. No usar como GT hasta revisión humana y validación F5.4.</p>" + "".join(cards) + "</body></html>"
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(html, encoding="utf-8")


def validate_field_record(record: Mapping[str, Any]) -> None:
    if record.get("contract_version") != "f55-field-observation-v1" or record.get("review", {}).get("status") not in {"pending", "approved", "rejected"}:
        raise F55EvidenceError("registro de campo F5.5 incompatible")
    evidence = record.get("evidence")
    if not isinstance(evidence, list):
        raise F55EvidenceError("evidence de campo debe ser lista")
    for row in evidence:
        path = PurePosixPath(row.get("logical_path", ""))
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or not _is_sha256(row.get("sha256")):
            raise F55EvidenceError("evidencia de campo no verificable")
    if record["review"]["status"] == "approved":
        required = (record.get("observer_position"), record.get("captured_at_utc"), record.get("device"), record.get("original_spanish_description"), record["review"].get("reviewer"), record["review"].get("reviewed_at_utc"), record["review"].get("validation_method"))
        if any(value is None or value == "" for value in required) or not record.get("gnss_readings") or not evidence:
            raise F55EvidenceError("registro aprobado carece de posición, GNSS, descripción, evidencia o revisión")
        position = record["observer_position"]
        if position.get("source") != "measured_observer_position" or position.get("horizontal_accuracy_m") is None or not _valid_coordinate(position.get("latitude"), position.get("longitude")) or position.get("crs") != "EPSG:4326":
            raise F55EvidenceError("posición aprobada no es medición del observador")
        if not record.get("captured_at_utc", "").endswith("Z") or not record.get("consent_or_data_policy"):
            raise F55EvidenceError("registro aprobado sin fecha UTC o política de datos")
        evidence_ids = {row.get("evidence_id") for row in evidence}
        if None in evidence_ids or len(evidence_ids) != len(evidence):
            raise F55EvidenceError("evidence_id de campo duplicado o ausente")
        for reading in record["gnss_readings"]:
            if not isinstance(reading, Mapping) or not _valid_coordinate(reading.get("latitude"), reading.get("longitude")) or not isinstance(reading.get("horizontal_accuracy_m"), (int, float)) or reading["horizontal_accuracy_m"] < 0 or not str(reading.get("captured_at_utc", "")).endswith("Z"):
                raise F55EvidenceError("lectura GNSS inválida")
        if record.get("orientation", {}).get("status") == "verified" and not record["orientation"].get("evidence_ids"):
            raise F55EvidenceError("orientación verificada sin evidencia")
        if not set(record.get("orientation", {}).get("evidence_ids", [])) <= evidence_ids:
            raise F55EvidenceError("orientación referencia evidencia inexistente")


def import_approved_field_records(records: Sequence[Mapping[str, Any]], *, evidence_root: Path, catalogs: Mapping[str, Any], dataset_version: str = "madrid-f55-field-pilot-v1") -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    approved, counts = [], Counter()
    seen = set()
    for record in records:
        validate_field_record(record)
        status = record["review"]["status"]; counts[status] += 1
        if status != "approved":
            continue
        if record["record_id"] in seen:
            raise F55EvidenceError("record_id de campo duplicado")
        seen.add(record["record_id"])
        _verify_evidence_files(record["evidence"], evidence_root)
        approved.append(record)
    queries, observations = [], []
    for record in approved:
        position = record["observer_position"]
        latitude, longitude, accuracy = position["latitude"], position["longitude"], position["horizontal_accuracy_m"]
        assignments = {gallery: assign_reference(latitude, longitude, catalog, reported_accuracy_m=accuracy) for gallery, catalog in catalogs.items()}
        query_id = record["record_id"]
        query = {
            "query_id": query_id, "location_id": record["location_id"], "derivation_group_id": record["derivation_group_id"], "partition": record["partition"],
            "description": {"text": record["original_spanish_description"], "language": "es", "contains_coordinates": False},
            "provenance": {"source_type": "human_in_situ", "description": "Observación F5.5 redactada in situ antes de consultar rankings.", "independent_environment_observation": True, "instructions_version": "f55-human-in-situ-v1", "collected_at_utc": record["captured_at_utc"]},
            "reference": {"status": "validated", "latitude": latitude, "longitude": longitude, "crs": "EPSG:4326", "capture_method": f"multi_reading_gnss:{record['device']}", "reported_accuracy_m": accuracy, "validation_method": record["review"]["validation_method"], "catalog_assignment": assignments["madrid-50m"]},
            "ambiguity": {"status": "not_ambiguous", "notes": record["review"].get("notes")}, "validation_status": "validated",
        }
        queries.append(query)
        observations.append(_f54_observation(query, record["evidence"], record["orientation"], assignments, limitations=record["limitations"]))
    query_dataset = _query_dataset(queries, catalogs["madrid-50m"], dataset_version)
    gt_dataset = _gt_dataset(observations, query_dataset, catalogs, dataset_version)
    return query_dataset, gt_dataset, {key: counts[key] for key in ("pending", "approved", "rejected")}


def import_approved_panoramax_reviews(queue: Mapping[str, Any], *, evidence_root: Path, catalogs: Mapping[str, Any], dataset_version: str = "madrid-f55-panoramax-pilot-v1") -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    counts = validate_review_queue(queue)
    queries, observations = [], []
    for record in queue["records"]:
        if record["review"]["status"] != "approved":
            continue
        asset = next((value["download"] for role in ("sd", "thumb") if (value := record["assets"].get(role)) and value.get("download")), None)
        if asset is None:
            raise F55EvidenceError("Panoramax aprobado sin asset")
        _verify_evidence_files([{"logical_path": asset["logical_path"], "sha256": asset["sha256"]}], evidence_root)
        position = record["camera_position"]
        accuracy = position["horizontal_accuracy_m"]
        if accuracy is None:
            raise F55EvidenceError("Panoramax aprobado sin precisión horizontal")
        assignments = {gallery: assign_reference(position["latitude"], position["longitude"], catalog, reported_accuracy_m=accuracy) for gallery, catalog in catalogs.items()}
        query_id = f"panoramax-{record['item_id']}"
        query = {
            "query_id": query_id, "location_id": query_id, "derivation_group_id": query_id, "partition": "development",
            "description": {"text": record["review"]["original_spanish_description"], "language": "es", "contains_coordinates": False},
            "provenance": {"source_type": "existing_dataset", "description": "Descripción humana derivada de evidencia fotográfica Panoramax; no es observación in situ del redactor.", "independent_environment_observation": True, "instructions_version": "f55-panoramax-human-description-v1", "collected_at_utc": record["captured_at_utc"]},
            "reference": {"status": "validated", "latitude": position["latitude"], "longitude": position["longitude"], "crs": "EPSG:4326", "capture_method": "panoramax_camera_metadata", "reported_accuracy_m": accuracy, "validation_method": "human_review_of_panoramax_metadata_and_evidence", "catalog_assignment": assignments["madrid-50m"]},
            "ambiguity": {"status": "not_ambiguous", "notes": record["review"].get("notes")}, "validation_status": "validated",
        }
        orientation = {"status": "reported" if record["review"]["orientation_usable"] else "absent", "cardinal": None, "bearing_degrees": record["orientation"]["camera_azimuth_degrees"] if record["review"]["orientation_usable"] else None, "uncertainty_degrees": record["review"]["orientation_uncertainty_degrees"] if record["review"]["orientation_usable"] else None, "verification_method": "panoramax_view_azimuth_metadata" if record["review"]["orientation_usable"] else None, "evidence_ids": [f"panoramax-{record['item_id']}-image"] if record["review"]["orientation_usable"] else [], "egocentric_relations_present": False, "notes": "Azimut de cámara; no equivale automáticamente a orientación corporal." if record["review"]["orientation_usable"] else None}
        evidence = [{"evidence_id": f"panoramax-{record['item_id']}-image", "kind": "existing_dataset_record", "logical_path": asset["logical_path"], "sha256": asset["sha256"], "description": f"Asset Panoramax {record['item_id']} revisado; licencia {record['license']['identifier']}.", "captured_at_utc": record["captured_at_utc"]}]
        queries.append(query); observations.append(_f54_observation(query, evidence, orientation, assignments, limitations=["description_derived_from_photograph", "camera_metadata_not_first_party_survey"]))
    query_dataset = _query_dataset(queries, catalogs["madrid-50m"], dataset_version)
    gt_dataset = _gt_dataset(observations, query_dataset, catalogs, dataset_version)
    return query_dataset, gt_dataset, counts


def _query_dataset(queries: list[dict[str, Any]], catalog, version: str) -> dict[str, Any]:
    document = {"schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "", "dataset_version": version, "region": {"region_id": catalog.region_id, "bbox_wgs84": dict(catalog.region_bbox_wgs84)}, "catalog": {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": len(catalog.candidates), "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"}, "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": .8}, "queries": queries}
    document["dataset_id"] = query_dataset_id(document); return document


def _gt_dataset(observations: list[dict[str, Any]], source: Mapping[str, Any], catalogs: Mapping[str, Any], version: str) -> dict[str, Any]:
    source_raw = canonical_bytes(source) + b"\n"
    document = {"schema_version": "1.0", "contract_version": "f5-ground-truth-dataset-v1", "dataset_id": "", "dataset_version": version, "source_query_dataset": {"dataset_id": source["dataset_id"], "sha256": sha256_bytes(source_raw)}, "catalogs": {gallery: {"manifest_id": catalog.manifest_id, "manifest_sha256": catalog.sha256, "candidate_count": len(catalog.candidates), "cell_size_m": catalog.cell_size_m} for gallery, catalog in sorted(catalogs.items())}, "collection_protocol": {"version": "f54-madrid-observer-collection-v1", "target_observations": {"minimum": 20, "maximum": 30}, "observer_position_policy": "observer_wgs84_not_mentioned_object", "description_policy": "original_spanish_independent_observation", "ground_truth_capture_before_ranking": True, "evidence_required": True, "orientation_policy": "explicit_evidence_no_egocentric_to_cardinal_inference", "synthetic_excluded_from_accuracy": True}, "observations": observations}
    document["dataset_id"] = ground_truth_dataset_id(document); return document


def _f54_observation(query: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]], orientation: Mapping[str, Any], assignments: Mapping[str, Any], *, limitations: Sequence[str]) -> dict[str, Any]:
    normalized_evidence = []
    for row in evidence:
        normalized_evidence.append({"evidence_id": row.get("evidence_id") or row.get("id"), "kind": row.get("kind", "other"), "logical_reference": row["logical_path"], "sha256": row["sha256"], "description": row.get("description", "Evidencia F5.5 revisada"), "captured_at_utc": row.get("captured_at_utc") or query["provenance"]["collected_at_utc"], "review_status": "reviewed"})
    reference = query["reference"]
    return {"source_query_id": query["query_id"], "location_id": query["location_id"], "derivation_group_id": query["derivation_group_id"], "partition": query["partition"], "description_profile": "complete_observation", "comparison_parent_query_id": None, "observer_reference": {"status": "validated", "latitude": reference["latitude"], "longitude": reference["longitude"], "crs": "EPSG:4326", "capture_method": reference["capture_method"], "reported_accuracy_m": reference["reported_accuracy_m"], "validation_method": reference["validation_method"], "evidence": normalized_evidence, "review_notes": query["ambiguity"]["notes"] or "Revisión F5.5 completada."}, "orientation": dict(orientation), "catalog_assignments": dict(assignments), "description_review_status": "reviewed", "limitations": list(limitations)}


def _verify_evidence_files(evidence: Sequence[Mapping[str, Any]], root: Path) -> None:
    for row in evidence:
        relative = row.get("logical_path")
        path = PurePosixPath(relative or "")
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise F55EvidenceError("path de evidencia no válido")
        physical = root / Path(*path.parts)
        if not physical.is_file() or sha256_bytes(physical.read_bytes()) != row.get("sha256"):
            raise F55EvidenceError(f"evidencia ausente o modificada: {relative}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_utc(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise F55EvidenceError(f"timestamp no ISO-8601: {value}") from error
    if parsed.tzinfo is None:
        raise F55EvidenceError(f"timestamp sin zona horaria: {value}")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _valid_coordinate(latitude: Any, longitude: Any) -> bool:
    return isinstance(latitude, (int, float)) and not isinstance(latitude, bool) and isinstance(longitude, (int, float)) and not isinstance(longitude, bool) and math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180
