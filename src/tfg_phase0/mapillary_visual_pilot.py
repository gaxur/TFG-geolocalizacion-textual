"""Selección y artefactos del piloto visual Mapillary, sin reranking."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path, PurePosixPath
import struct
from typing import Any, Mapping, Sequence

from .f4_evaluation import haversine_m
from .mapillary_coverage import canonical_bytes, sha256_bytes


PILOT_POLICY = "mapillary-visual-pilot-selection-v1"
BAND_QUOTAS = {"lt25": 3, "25_50": 3, "50_100": 2, "none": 2}
UTILITY_VALUES = {"useful", "partially_useful", "not_useful", "unverifiable"}
VERIFICATION_LEVELS = {"strong_match", "partial_match", "insufficient", "contradiction"}
FORBIDDEN_GT_FIELDS = {
    "ground_truth",
    "ground_truth_candidate_id",
    "reference",
    "reference_candidate_id",
    "distance_to_gt",
    "distance_to_ground_truth",
    "top1_error_m",
    "minimum_top10_m",
    "geo10_50",
    "geo10_100",
    "geo1_50",
    "geo1_100",
    "recall1",
    "recall10",
    "within_50m",
    "within_100m",
}


class MapillaryPilotError(ValueError):
    """Un artefacto del piloto visual incumple su contrato."""


def reject_ground_truth(value: Any, *, path: str = "input") -> None:
    """Impide que selección y adquisición reciban referencias o métricas de acierto."""
    if isinstance(value, Mapping):
        forbidden = FORBIDDEN_GT_FIELDS.intersection(value)
        if forbidden:
            raise MapillaryPilotError(
                f"campo de GT o evaluación prohibido en {path}: {sorted(forbidden)[0]}"
            )
        for key, item in value.items():
            reject_ground_truth(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            reject_ground_truth(item, path=f"{path}[{index}]")


def content_id(prefix: str, document: Mapping[str, Any], field: str) -> str:
    return prefix + sha256_bytes(canonical_bytes({key: value for key, value in document.items() if key != field}))


def bearing_degrees(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lon = math.radians(longitude_b - longitude_a)
    y = math.sin(delta_lon) * math.cos(lat_b)
    x = math.cos(lat_a) * math.sin(lat_b) - math.sin(lat_a) * math.cos(lat_b) * math.cos(delta_lon)
    return math.degrees(math.atan2(y, x)) % 360


def angular_difference(left: float, right: float) -> float:
    return abs((left - right + 180) % 360 - 180)


def _band(distance: float | None) -> str:
    if distance is None or distance > 100:
        return "none"
    if distance < 25:
        return "lt25"
    if distance < 50:
        return "25_50"
    return "50_100"


def _hash_order(candidate_id: str) -> str:
    return hashlib.sha256(f"{PILOT_POLICY}:{candidate_id}".encode()).hexdigest()


def _contexts(rankings: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    selected = [row for row in rankings.get("rows", []) if row.get("gallery_id") == "madrid-50m" and row.get("kind") == "en_cartographic"]
    if len(selected) != 15:
        raise MapillaryPilotError("se esperaban 15 rankings congelados")
    for row in selected:
        for result in row["results"]:
            output.setdefault(result["candidate_id"], []).append({"query_id": row["query_id"], "baseline_rank": result["rank"]})
    return output


def _nearest(candidate: Mapping[str, Any], images: Sequence[Mapping[str, Any]]) -> float | None:
    values = [haversine_m(candidate["latitude"], candidate["longitude"], image["latitude"], image["longitude"]) for image in images]
    return min(values) if values else None


def select_pilot_candidates(
    inventory: Mapping[str, Any],
    coverage: Mapping[str, Any],
    rankings: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    reject_ground_truth(inventory, path="inventory")
    reject_ground_truth(coverage, path="coverage")
    reject_ground_truth(rankings, path="rankings")
    reject_ground_truth(plan, path="plan")
    contexts = _contexts(rankings)
    controls = {row["query_id"]: row for row in plan.get("controls", []) if row.get("kind") == "en_cartographic"}
    if len(controls) != 15:
        raise MapillaryPilotError("plan H11-H25 no contiene 15 textos en_cartographic")
    coverage_rows = coverage.get("h11_h25_top10", {}).get("unique_candidates", [])
    candidates = {row["candidate_id"]: {"candidate_id": row["candidate_id"], "latitude": row["latitude"], "longitude": row["longitude"], "nearest_image_distance_m": row["radii"]["100"]["nearest_image_distance_m"]} for row in coverage_rows}
    if len(candidates) != 88:
        raise MapillaryPilotError("coverage debe contener 88 candidatos únicos")
    by_band = {band: [] for band in BAND_QUOTAS}
    for candidate in candidates.values():
        distance = candidate["nearest_image_distance_m"]
        candidate = {**candidate, "nearest_image_distance_m": distance, "distance_band": _band(distance), "contexts": sorted(contexts[candidate["candidate_id"]], key=lambda row: (row["baseline_rank"], row["query_id"])), "hash_order": _hash_order(candidate["candidate_id"])}
        by_band[candidate["distance_band"]].append(candidate)
    for rows in by_band.values():
        rows.sort(key=lambda row: row["hash_order"])

    selected = []
    used_queries = set()
    shortages = {}
    for band, quota in BAND_QUOTAS.items():
        pool = by_band[band]
        chosen = []
        while len(chosen) < quota and pool:
            preferred = next((row for row in pool if any(context["query_id"] not in used_queries for context in row["contexts"])), pool[0])
            pool.remove(preferred)
            context = next((item for item in preferred["contexts"] if item["query_id"] not in used_queries), preferred["contexts"][0])
            used_queries.add(context["query_id"])
            chosen.append({**preferred, **context})
        shortages[band] = quota - len(chosen)
        selected.extend(chosen)
    deficit = sum(shortages.values())
    if deficit:
        remaining = sorted((row for rows in by_band.values() for row in rows), key=lambda row: row["hash_order"])
        for row in remaining[:deficit]:
            context = next((item for item in row["contexts"] if item["query_id"] not in used_queries), row["contexts"][0])
            used_queries.add(context["query_id"])
            selected.append({**row, **context, "redistributed_from_shortage": True})
    if len(selected) != 10 or len({row["candidate_id"] for row in selected}) != 10:
        raise MapillaryPilotError("no se pudieron seleccionar diez candidatos")
    selected.sort(key=lambda row: (tuple(BAND_QUOTAS).index(row["distance_band"]), row["hash_order"]))
    result = {
        "schema_version": "1.0",
        "contract_version": "mapillary-visual-pilot-selection-v1",
        "selection_id": "",
        "policy": {"version": PILOT_POLICY, "requested_quotas": BAND_QUOTAS, "shortages": shortages, "ordering": "sha256(policy:candidate_id)_with_query_diversity", "ground_truth_used": False, "evaluation_metrics_used": False},
        "inputs": {"sha256": dict(input_hashes), "inventory_id": inventory["inventory_id"], "ranking_filter": {"gallery_id": "madrid-50m", "kind": "en_cartographic"}},
        "candidates": [{key: value for key, value in row.items() if key not in {"contexts", "hash_order"}} | {"description": controls[row["query_id"]]["text"], "language": controls[row["query_id"]]["language"]} for row in selected],
    }
    result["selection_id"] = content_id("mapillary-visual-pilot-selection-sha256-", result, "selection_id")
    reject_ground_truth(result, path="selection")
    validate_selection(result)
    return result


def validate_selection(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "mapillary-visual-pilot-selection-v1" or document.get("policy", {}).get("ground_truth_used") is not False:
        raise MapillaryPilotError("selección piloto inválida o con GT")
    candidates = document.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 10 or len({row.get("candidate_id") for row in candidates}) != 10:
        raise MapillaryPilotError("selección piloto debe contener diez candidatos únicos")
    if document.get("selection_id") != content_id("mapillary-visual-pilot-selection-sha256-", document, "selection_id"):
        raise MapillaryPilotError("selection_id no corresponde al contenido")


def select_candidate_images(selection: Mapping[str, Any], inventory: Mapping[str, Any], *, max_per_candidate: int = 3, absolute_limit: int = 30) -> dict[str, Any]:
    reject_ground_truth(selection, path="selection")
    reject_ground_truth(inventory, path="inventory")
    validate_selection(selection)
    if not 1 <= max_per_candidate <= 3 or absolute_limit > 30:
        raise MapillaryPilotError("límites de fotografías inválidos")
    planned = []
    used_ids = set()
    for candidate in selection["candidates"]:
        if candidate["distance_band"] == "none":
            planned.append({"candidate_id": candidate["candidate_id"], "status": "no_spatial_coverage", "images": []})
            continue
        nearby = []
        for image in inventory["images"]:
            distance = haversine_m(candidate["latitude"], candidate["longitude"], image["latitude"], image["longitude"])
            if distance <= 100 and image["image_id"] not in used_ids:
                bearing = bearing_degrees(image["latitude"], image["longitude"], candidate["latitude"], candidate["longitude"])
                difference = angular_difference(image["orientation_degrees"], bearing) if image.get("orientation_degrees") is not None else None
                nearby.append({**image, "distance_to_candidate_m": distance, "bearing_to_candidate_degrees": bearing, "angular_difference_degrees": difference, "orientation_bin": int(image["orientation_degrees"] // 45) if image.get("orientation_degrees") is not None else None})
        nearby.sort(key=lambda row: (row["distance_to_candidate_m"], -(row.get("quality_score") or -1), -(row.get("captured_at_epoch_ms") or 0), row["image_id"]))
        chosen = []
        used_sequences = set()
        used_bins = set()
        for strict in (True, False):
            for row in nearby:
                if row in chosen:
                    continue
                if strict and ((row.get("sequence_id") in used_sequences and row.get("sequence_id") is not None) or (row.get("orientation_bin") in used_bins and row.get("orientation_bin") is not None)):
                    continue
                chosen.append(row)
                if row.get("sequence_id") is not None:
                    used_sequences.add(row["sequence_id"])
                if row.get("orientation_bin") is not None:
                    used_bins.add(row["orientation_bin"])
                if len(chosen) == max_per_candidate:
                    break
            if len(chosen) == max_per_candidate:
                break
        for row in chosen:
            used_ids.add(row["image_id"])
        planned.append({"candidate_id": candidate["candidate_id"], "status": "planned" if chosen else "no_spatial_coverage", "images": chosen})
    total = sum(len(row["images"]) for row in planned)
    if total > absolute_limit:
        raise MapillaryPilotError("el plan supera el límite absoluto de fotografías")
    result = {"schema_version": "1.0", "contract_version": "mapillary-visual-image-plan-v1", "image_plan_id": "", "selection_id": selection["selection_id"], "policy": {"max_per_candidate": max_per_candidate, "absolute_download_limit": absolute_limit, "maximum_radius_m": 100, "field_of_view_assumed": False, "ground_truth_used": False}, "planned_image_count": total, "candidates": planned}
    result["image_plan_id"] = content_id("mapillary-visual-image-plan-sha256-", result, "image_plan_id")
    validate_image_plan(result)
    return result


def validate_image_plan(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "mapillary-visual-image-plan-v1" or document.get("policy", {}).get("ground_truth_used") is not False:
        raise MapillaryPilotError("plan de imágenes inválido")
    rows = document.get("candidates", [])
    ids = [image["image_id"] for row in rows for image in row.get("images", [])]
    if len(rows) != 10 or len(ids) != len(set(ids)) or len(ids) != document.get("planned_image_count") or len(ids) > 30 or any(len(row.get("images", [])) > 3 for row in rows):
        raise MapillaryPilotError("límites o duplicados del plan inválidos")
    if document.get("image_plan_id") != content_id("mapillary-visual-image-plan-sha256-", document, "image_plan_id"):
        raise MapillaryPilotError("image_plan_id no corresponde al contenido")


def image_dimensions(raw: bytes) -> tuple[str, int, int]:
    if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
        width, height = struct.unpack(">II", raw[16:24])
        return "image/png", width, height
    if raw.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(raw):
            if raw[offset] != 0xFF:
                offset += 1
                continue
            marker = raw[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(raw):
                break
            length = struct.unpack(">H", raw[offset:offset + 2])[0]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and offset + 7 <= len(raw):
                height, width = struct.unpack(">HH", raw[offset + 3:offset + 7])
                return "image/jpeg", width, height
            if length < 2:
                break
            offset += length
    raise MapillaryPilotError("fotografía no es PNG o JPEG estructuralmente reconocible")


def annotation_template(selection: Mapping[str, Any], image_plan: Mapping[str, Any]) -> dict[str, Any]:
    records = []
    by_candidate = {row["candidate_id"]: row for row in image_plan["candidates"]}
    for candidate in selection["candidates"]:
        rows = by_candidate[candidate["candidate_id"]]["images"]
        if not rows:
            records.append({"query_id": candidate["query_id"], "candidate_id": candidate["candidate_id"], "image_id": None, "coverage_status": "no_spatial_coverage", "review_status": "not_applicable", "utility": None, "matches": [], "contradictions": [], "unverifiable": ["sin evidencia visual disponible"], "limitations": ["no_image_within_100m"], "reviewer": None, "reviewed_at_utc": None, "notes": None})
        for image in rows:
            records.append({"query_id": candidate["query_id"], "candidate_id": candidate["candidate_id"], "image_id": image["image_id"], "coverage_status": "downloaded", "review_status": "pending", "utility": None, "matches": [], "contradictions": [], "unverifiable": [], "limitations": [], "reviewer": None, "reviewed_at_utc": None, "notes": None})
    return {"schema_version": "1.0", "contract_version": "mapillary-visual-annotation-v1", "selection_id": selection["selection_id"], "records": records, "instructions": {"absence_is_not_contradiction": True, "egocentric_relations_require_reliable_alignment": True}}


def validate_annotations(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "mapillary-visual-annotation-v1":
        raise MapillaryPilotError("contrato de anotación inválido")
    for row in document.get("records", []):
        status = row.get("review_status")
        if status not in {"pending", "reviewed", "not_applicable"} or not all(isinstance(row.get(field), list) for field in ("matches", "contradictions", "unverifiable", "limitations")):
            raise MapillaryPilotError("anotación visual inválida")
        if status == "reviewed" and (row.get("utility") not in UTILITY_VALUES or not row.get("reviewer") or not row.get("reviewed_at_utc")):
            raise MapillaryPilotError("anotación revisada incompleta")
        if status == "pending" and row.get("utility") is not None:
            raise MapillaryPilotError("anotación pendiente no debe anticipar utilidad")
        if row.get("image_id") is None and row.get("contradictions"):
            raise MapillaryPilotError("ausencia de imagen no puede ser contradicción")


def vlm_template(selection: Mapping[str, Any], image_plan: Mapping[str, Any]) -> dict[str, Any]:
    by_candidate = {row["candidate_id"]: row for row in image_plan["candidates"]}
    records = []
    for candidate in selection["candidates"]:
        records.append({"candidate_id": candidate["candidate_id"], "image_ids": [row["image_id"] for row in by_candidate[candidate["candidate_id"]]["images"]], "matches": [], "contradictions": [], "unverifiable": [], "verification_level": "insufficient", "evidence": [], "provenance": {"model_id": "Qwen/Qwen3-VL-4B-Instruct", "fallback_model_id": "Qwen/Qwen3-VL-2B-Instruct", "model_revision": None, "prompt_version": "mapillary-visual-verification-v1", "selection_id": selection["selection_id"], "ground_truth_used": False}})
    return {"schema_version": "1.0", "contract_version": "mapillary-vlm-verification-v1", "records": records, "reranking_performed": False}


def validate_vlm(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "mapillary-vlm-verification-v1" or document.get("reranking_performed") is not False:
        raise MapillaryPilotError("contrato VLM inválido")
    for row in document.get("records", []):
        if row.get("verification_level") not in VERIFICATION_LEVELS or row.get("provenance", {}).get("ground_truth_used") is not False:
            raise MapillaryPilotError("resultado VLM inválido o con GT")


def summarize_annotations(annotations: Mapping[str, Any], photo_manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_annotations(annotations)
    photos = {(row["candidate_id"], row["image_id"]): row for row in photo_manifest.get("photos", []) if row.get("status") == "downloaded"}
    reviewed = [row for row in annotations["records"] if row.get("image_id") is not None and row.get("review_status") == "reviewed"]
    pending = [row for row in annotations["records"] if row.get("image_id") is not None and row.get("review_status") == "pending"]
    counts = {value: sum(row.get("utility") == value for row in reviewed) for value in sorted(UTILITY_VALUES)}
    useful_candidates = {row["candidate_id"] for row in reviewed if row.get("utility") in {"useful", "partially_useful"}}
    bands = {"lt25": [], "25_50": [], "50_100": []}
    for row in reviewed:
        photo = photos.get((row["candidate_id"], row["image_id"]))
        if photo is None:
            raise MapillaryPilotError("anotación revisada sin fotografía descargada")
        distance = photo["distance_to_candidate_m"]
        band = "lt25" if distance < 25 else "25_50" if distance < 50 else "50_100"
        bands[band].append(row)
    return {
        "schema_version": "1.0",
        "contract_version": "mapillary-visual-annotation-summary-v1",
        "quantitative_results_available": bool(reviewed) and not pending,
        "reviewed_image_count": len(reviewed),
        "pending_image_count": len(pending),
        "utility": {value: {"count": count, "fraction_of_reviewed": count / len(reviewed) if reviewed else None} for value, count in counts.items()},
        "candidates_with_useful_or_partial_evidence": len(useful_candidates),
        "by_distance_band": {band: {"reviewed": len(rows), "useful_or_partial": sum(row.get("utility") in {"useful", "partially_useful"} for row in rows)} for band, rows in bands.items()},
        "limitations": ["manual_annotations_only", "no_ground_truth", "absence_in_partial_view_is_not_contradiction"],
    }


def render_html(selection: Mapping[str, Any], photo_manifest: Mapping[str, Any], annotations: Mapping[str, Any], output: Path) -> None:
    photos = {}
    for row in photo_manifest.get("photos", []):
        photos.setdefault(row["candidate_id"], []).append(row)
    annotation_index = {(row["candidate_id"], row.get("image_id")): row for row in annotations["records"]}
    articles = []
    for candidate in selection["candidates"]:
        cards = []
        for photo in photos.get(candidate["candidate_id"], []):
            annotation = annotation_index.get((candidate["candidate_id"], photo["image_id"]), {})
            image_html = f'<img loading="lazy" src="{escape(photo["logical_path"], quote=True)}" alt="Vista Mapillary {escape(photo["image_id"])}">' if photo["status"] == "downloaded" else '<div class="missing">fotografía no disponible</div>'
            creator = photo.get("creator") or {}
            creator_name = creator.get("username") or creator.get("name")
            creator_html = escape(str(creator_name))
            if creator_name and photo.get("creator_profile_url"):
                creator_html = f'<a href="{escape(photo["creator_profile_url"], quote=True)}" rel="noreferrer">{creator_html}</a>'
            license_html = "CC BY-SA 4.0"
            if photo.get("license_url"):
                license_html = f'<a href="{escape(photo["license_url"], quote=True)}" rel="license noreferrer">CC BY-SA 4.0</a>'
            utility = annotation.get("utility") or ""
            options = ''.join(f'<option value="{value}"{" selected" if utility == value else ""}>{value}</option>' for value in ("useful", "partially_useful", "not_useful", "unverifiable"))
            def lines(field: str) -> str:
                return escape("\n".join(str(value) for value in annotation.get(field, [])))
            cards.append(f'<section class="photo" data-candidate-id="{escape(candidate["candidate_id"], quote=True)}" data-image-id="{escape(photo["image_id"], quote=True)}">{image_html}<dl><dt>Imagen</dt><dd>{escape(photo["image_id"])}</dd><dt>Distancia</dt><dd>{photo["distance_to_candidate_m"]:.1f} m</dd><dt>Orientación</dt><dd>{escape(str(photo.get("orientation_degrees")))}</dd><dt>Diferencia angular</dt><dd>{escape(str(photo.get("angular_difference_degrees")))}</dd><dt>Fecha</dt><dd>{escape(str(photo.get("captured_at")))}</dd><dt>Resolución</dt><dd>{escape(str(photo.get("downloaded_resolution")))}</dd><dt>Calidad</dt><dd>{escape(str(photo.get("quality_score")))}</dd><dt>Creador</dt><dd>{creator_html or "pendiente"}</dd><dt>Proveedor</dt><dd>Mapillary</dd><dt>Licencia</dt><dd>{license_html}</dd><dt>Modificaciones</dt><dd>{escape(str(photo.get("modifications") or "pendiente"))}</dd><dt>Atribución</dt><dd>{escape(photo.get("attribution") or "pendiente de adquisición")}</dd></dl><a href="{escape(photo["source_page_url"], quote=True)}" rel="noreferrer">Imagen original en Mapillary</a><fieldset><legend>Anotación de esta fotografía</legend><label>Utilidad<select class="utility"><option value="">pendiente</option>{options}</select></label><label>Coincidencias observables, una por línea<textarea class="matches">{lines("matches")}</textarea></label><label>Contradicciones inequívocas, una por línea<textarea class="contradictions">{lines("contradictions")}</textarea></label><label>Elementos no verificables, uno por línea<textarea class="unverifiable">{lines("unverifiable")}</textarea></label><label>Limitaciones de orientación, distancia, resolución u oclusión<textarea class="limitations">{lines("limitations")}</textarea></label><label>Notas<textarea class="notes">{escape(str(annotation.get("notes") or ""))}</textarea></label><label><input class="reviewed" type="checkbox"{" checked" if annotation.get("review_status") == "reviewed" else ""}> Anotación revisada</label></fieldset></section>')
        if not cards:
            cards.append('<p class="missing">sin evidencia visual disponible</p>')
        articles.append(f'<article><h2>{escape(candidate["query_id"])} · rango {candidate["baseline_rank"]}</h2><p>{escape(candidate["description"])}</p><p><code>{escape(candidate["candidate_id"])}</code><br>{candidate["latitude"]:.7f}, {candidate["longitude"]:.7f}<br>Banda: {escape(candidate["distance_band"])}</p><div class="grid">{"".join(cards)}</div></article>')
    annotation_json = json.dumps(annotations, ensure_ascii=False).replace("</", "<\\/")
    script = r'''<script id="annotation-data" type="application/json">ANNOTATION_JSON</script><script>
const data=JSON.parse(document.getElementById('annotation-data').textContent);
const splitLines=v=>v.split('\n').map(x=>x.trim()).filter(Boolean);
const key=(candidate,image)=>candidate+'\u0000'+image;
const records=new Map(data.records.filter(r=>r.image_id!==null).map(r=>[key(r.candidate_id,r.image_id),r]));
function collect(){
 const reviewer=document.getElementById('reviewer').value.trim();
 document.querySelectorAll('.photo[data-image-id]').forEach(card=>{
  const record=records.get(key(card.dataset.candidateId,card.dataset.imageId));
  record.utility=card.querySelector('.utility').value||null;
  record.matches=splitLines(card.querySelector('.matches').value);
  record.contradictions=splitLines(card.querySelector('.contradictions').value);
  record.unverifiable=splitLines(card.querySelector('.unverifiable').value);
  record.limitations=splitLines(card.querySelector('.limitations').value);
  record.notes=card.querySelector('.notes').value.trim()||null;
  if(card.querySelector('.reviewed').checked){
   if(!record.utility||!reviewer) throw new Error('Cada fila revisada necesita utilidad y nombre de revisor.');
   record.review_status='reviewed'; record.reviewer=reviewer; record.reviewed_at_utc=new Date().toISOString();
  } else {record.review_status='pending'; record.reviewer=null; record.reviewed_at_utc=null;}
 });
 return data;
}
document.getElementById('export').addEventListener('click',()=>{
 try {const payload=JSON.stringify(collect(),null,2)+'\n'; const link=document.createElement('a'); link.href=URL.createObjectURL(new Blob([payload],{type:'application/json'})); link.download='annotations.json'; link.click(); URL.revokeObjectURL(link.href); document.getElementById('status').textContent='Anotaciones exportadas.';} catch(error){document.getElementById('status').textContent=error.message;}
});
</script>'''.replace('ANNOTATION_JSON', annotation_json)
    output.write_text('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Piloto visual Mapillary</title><style>body{font:15px system-ui;max-width:1400px;margin:auto;padding:2rem;background:#f4f1e8;color:#18201b}article{border-top:3px solid #1f6f54;padding:1rem 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}.photo{background:white;padding:1rem;border:1px solid #b8b4a8}.photo img{width:100%;max-height:360px;object-fit:contain;background:#111}dl{display:grid;grid-template-columns:9rem 1fr}dt{font-weight:700}.missing{padding:2rem;background:#ead8d0}code{overflow-wrap:anywhere}fieldset{margin-top:1rem;border:1px solid #1f6f54}label{display:block;margin:.6rem 0;font-weight:600}select,textarea,input{font:inherit}select,textarea{box-sizing:border-box;width:100%;margin-top:.25rem}textarea{min-height:5rem}.toolbar{position:sticky;top:0;background:#183b2d;color:white;padding:1rem;z-index:2}.toolbar input{margin:0 .5rem}.toolbar button{padding:.5rem 1rem}</style><h1>Piloto visual Mapillary</h1><p>Inspección manual sin GT ni reranking. Proximidad no demuestra visibilidad. Una ausencia en una vista parcial no es contradicción.</p><div class="toolbar"><label>Revisor <input id="reviewer" type="text"></label><button id="export" type="button">Exportar annotations.json</button> <span id="status"></span></div>' + ''.join(articles) + script + '</html>', encoding="utf-8")


def safe_logical_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MapillaryPilotError("ruta lógica insegura")
