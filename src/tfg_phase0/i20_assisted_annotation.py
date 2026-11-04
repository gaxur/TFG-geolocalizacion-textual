"""Contratos de asistencia VLM I01-I20; propuestas inmutables y revisión separada."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from .i20_preparation import EXPECTED_IDS, canonical_bytes


FORBIDDEN_KEYS = {
    "latitude", "longitude", "coordinates", "ground_truth", "gt", "ranking",
    "rank", "score", "candidate_id", "candidate", "osm", "openstreetmap",
    "holdout", "distance_m", "nearest", "cell_id", "gallery", "mapillary_id",
    "provider_record_id", "sequence_id", "location_id",
}
HUMAN_STATES = {"pending", "reviewed", "corrected", "rejected", "unresolved"}


class I20AssistedError(ValueError):
    pass


def content_id(prefix: str, document: Mapping[str, Any], field: str) -> str:
    return prefix + hashlib.sha256(canonical_bytes({key: value for key, value in document.items() if key != field})).hexdigest()


def reject_forbidden(value: Any, *, path: str = "document") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise I20AssistedError(f"campo prohibido en {path}: {key}")
            reject_forbidden(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            reject_forbidden(item, path=f"{path}[{index}]")
    elif isinstance(value, str) and (value.startswith("http://") or value.startswith("https://")):
        raise I20AssistedError(f"URL externa prohibida en {path}")


def scene_prompt() -> str:
    return (
        "Compara exclusivamente estas dos fotografías urbanas. No tienes coordenadas, mapas, OSM, rankings, GT ni holdout. "
        "Propón si muestran la misma escena, si comparten objetos distintivos, si sus campos de visión se solapan y si son "
        "vistas alternativas del mismo lugar. Usa yes|no|uncertain. decision debe ser CLEAR, EXCLUDE o REVIEW; ante duda usa REVIEW. "
        "La propuesta requiere revisión humana. Devuelve solo JSON estricto conforme al schema."
    )


def annotation_prompt() -> str:
    return (
        "Describe exclusivamente lo observable en esta fotografía urbana, en español natural. No uses mapas, coordenadas, OSM, "
        "rankings, GT, metadatos o conocimiento externo. Incluye elementos útiles para geolocalización, relaciones visibles en el "
        "encuadre, texto solo si es legible, claims atómicos con spans literales y dudas explícitas. No inventes nombres o lugares. "
        "La orientación cardinal debe quedar unknown. La salida es una propuesta IA pendiente de revisión humana. Devuelve solo JSON estricto."
    )


def annotation_prompt_v10() -> str:
    return (
        "Describe exclusivamente lo observable en esta fotografía urbana, en español natural y conciso. No uses mapas, coordenadas, "
        "OSM, rankings, GT, metadatos o conocimiento externo. Prioriza indicios visuales discriminativos: objetos, atributos, estructura, "
        "relaciones en el encuadre y texto realmente legible. Evita inventarios exhaustivos de ausencias, repeticiones y detalles genéricos. "
        "La descripción debe tener entre 80 y 900 caracteres. Para cada claim devuelve semantic_text_es como interpretación atómica y "
        "evidence_quote como una cita exacta, no vacía y copiada una sola vez de description_es; no calcules offsets. Para visible_text, "
        "evidence_quote también debe ser una cita exacta y única de description_es. No inventes nombres o lugares. La orientación cardinal "
        "debe quedar unknown. La salida es una propuesta IA pendiente de revisión humana. Devuelve solo JSON estricto conforme al schema."
    )


def scene_draft_schema_v1() -> dict[str, Any]:
    return {"type":"object","additionalProperties":False,"required":["same_scene","distinctive_objects_shared","field_of_view_overlap","same_place_different_frame","decision","justification_es","uncertainties","human_review_required"],"properties":{"same_scene":{"enum":["yes","no","uncertain"]},"distinctive_objects_shared":{"enum":["yes","no","uncertain"]},"field_of_view_overlap":{"enum":["yes","no","uncertain"]},"same_place_different_frame":{"enum":["yes","no","uncertain"]},"decision":{"enum":["CLEAR","EXCLUDE","REVIEW"]},"justification_es":{"type":"string","maxLength":600},"uncertainties":{"type":"array","maxItems":6,"uniqueItems":True,"items":{"type":"string","maxLength":300}},"human_review_required":{"const":True}}}


def annotation_draft_schema_v1() -> dict[str, Any]:
    claim={"type":"object","additionalProperties":False,"required":["kind","text_es","span","observability","certainty","requires_ocr","requires_orientation","orientation_frame","limitations"],"properties":{"kind":{"enum":["object_presence","attribute","visible_text","scene_structure","camera_frame_relation","egocentric_relation","other_observable"]},"text_es":{"type":"string","maxLength":300},"span":{"type":"object","additionalProperties":False,"required":["start","end"],"properties":{"start":{"type":"integer","minimum":0},"end":{"type":"integer","minimum":1}}},"observability":{"enum":["direct","partially_observable","uncertain"]},"certainty":{"enum":["certain","probable","uncertain"]},"requires_ocr":{"type":"boolean"},"requires_orientation":{"type":"boolean"},"orientation_frame":{"enum":["camera_frame","observer_frame_reported","unknown"]},"limitations":{"type":"array","uniqueItems":True,"items":{"type":"string","maxLength":120}}}}
    visible={"type":"object","additionalProperties":False,"required":["transcription_es","span","legibility","certainty"],"properties":{"transcription_es":{"type":["string","null"],"maxLength":200},"span":{"type":"object","additionalProperties":False,"required":["start","end"],"properties":{"start":{"type":"integer","minimum":0},"end":{"type":"integer","minimum":1}}},"legibility":{"enum":["readable","partially_readable","unreadable","uncertain"]},"certainty":{"enum":["certain","probable","uncertain"]}}}
    return {"type":"object","additionalProperties":False,"required":["description_es","claims","visible_text","visual_uncertainty","orientation","human_review_required"],"properties":{"description_es":{"type":"string","minLength":20,"maxLength":2000},"claims":{"type":"array","minItems":1,"maxItems":40,"items":claim},"visible_text":{"type":"array","maxItems":20,"items":visible},"visual_uncertainty":{"type":"object","additionalProperties":False,"required":["overall_status","limitations","notes_es"],"properties":{"overall_status":{"enum":["adequate","limited","insufficient"]},"limitations":{"type":"array","uniqueItems":True,"items":{"type":"string","maxLength":120}},"notes_es":{"type":["string","null"],"maxLength":500}}},"orientation":{"type":"object","additionalProperties":False,"required":["status","bearing_degrees","uncertainty_degrees","meaning","source","evidence_ids","cardinal_conversion_allowed"],"properties":{"status":{"const":"unknown"},"bearing_degrees":{"type":"null"},"uncertainty_degrees":{"type":"null"},"meaning":{"const":"unknown"},"source":{"const":"not_available"},"evidence_ids":{"type":"array","maxItems":0},"cardinal_conversion_allowed":{"const":False}}},"human_review_required":{"const":True}}}


def _replace_boolean_consts(value: Any, *, use_enum: bool) -> Any:
    """Sustituye const booleano solo en schemas guiados; el contrato queda estricto."""
    if isinstance(value, Mapping):
        if set(value) == {"const"} and isinstance(value["const"], bool):
            return {"enum": [value["const"]]} if use_enum else {"type": "boolean"}
        return {key: _replace_boolean_consts(item, use_enum=use_enum) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_boolean_consts(item, use_enum=use_enum) for item in value]
    return value


def scene_draft_schema_v2() -> dict[str, Any]:
    return _replace_boolean_consts(scene_draft_schema_v1(), use_enum=True)


def annotation_draft_schema_v2() -> dict[str, Any]:
    return _replace_boolean_consts(annotation_draft_schema_v1(), use_enum=True)


def scene_draft_schema() -> dict[str, Any]:
    return _replace_boolean_consts(scene_draft_schema_v1(), use_enum=False)


def annotation_draft_schema() -> dict[str, Any]:
    return _replace_boolean_consts(annotation_draft_schema_v1(), use_enum=False)


def annotation_evidence_draft_schema_v10() -> dict[str, Any]:
    claim={"type":"object","additionalProperties":False,"required":["kind","semantic_text_es","evidence_quote","observability","certainty","requires_ocr","requires_orientation","orientation_frame","limitations"],"properties":{"kind":{"enum":["object_presence","attribute","visible_text","scene_structure","camera_frame_relation","egocentric_relation","other_observable"]},"semantic_text_es":{"type":"string","minLength":1,"maxLength":300},"evidence_quote":{"type":"string","minLength":1,"maxLength":300},"observability":{"enum":["direct","partially_observable","uncertain"]},"certainty":{"enum":["certain","probable","uncertain"]},"requires_ocr":{"type":"boolean"},"requires_orientation":{"type":"boolean"},"orientation_frame":{"enum":["camera_frame","observer_frame_reported","unknown"]},"limitations":{"type":"array","maxItems":6,"uniqueItems":True,"items":{"type":"string","minLength":1,"maxLength":120}}}}
    visible={"type":"object","additionalProperties":False,"required":["transcription_es","evidence_quote","legibility","certainty"],"properties":{"transcription_es":{"type":["string","null"],"maxLength":200},"evidence_quote":{"type":"string","minLength":1,"maxLength":200},"legibility":{"enum":["readable","partially_readable","unreadable","uncertain"]},"certainty":{"enum":["certain","probable","uncertain"]}}}
    orientation=annotation_draft_schema()["properties"]["orientation"]
    return {"type":"object","additionalProperties":False,"required":["description_es","claims","visible_text","visual_uncertainty","orientation","human_review_required"],"properties":{"description_es":{"type":"string","minLength":80,"maxLength":900},"claims":{"type":"array","minItems":1,"maxItems":12,"items":claim},"visible_text":{"type":"array","maxItems":8,"items":visible},"visual_uncertainty":{"type":"object","additionalProperties":False,"required":["overall_status","limitations","notes_es"],"properties":{"overall_status":{"enum":["adequate","limited","insufficient"]},"limitations":{"type":"array","maxItems":6,"uniqueItems":True,"items":{"type":"string","minLength":1,"maxLength":120}},"notes_es":{"type":["string","null"],"maxLength":300}}},"orientation":orientation,"human_review_required":{"type":"boolean"}}}


def unique_literal_span(description: str, evidence_quote: str) -> dict[str, int]:
    if not isinstance(description,str) or not isinstance(evidence_quote,str) or not evidence_quote:
        raise I20AssistedError("evidence_quote ausente o vacío")
    starts=[];offset=0
    while True:
        index=description.find(evidence_quote,offset)
        if index<0:break
        starts.append(index);offset=index+1
    if not starts:raise I20AssistedError("evidence_quote no aparece literalmente en description_es")
    if len(starts)>1:raise I20AssistedError("evidence_quote ambiguo: múltiples coincidencias literales")
    start=starts[0];end=start+len(evidence_quote)
    if description[start:end]!=evidence_quote:raise I20AssistedError("materialización literal incoherente")
    return {"start":start,"end":end}


def materialize_annotation_evidence_draft(raw: Mapping[str, Any]) -> dict[str, Any]:
    jsonschema.Draft202012Validator(annotation_evidence_draft_schema_v10()).validate(raw)
    reject_forbidden(raw)
    description=raw["description_es"]
    output={key:json.loads(json.dumps(value,ensure_ascii=False)) for key,value in raw.items() if key not in {"claims","visible_text"}}
    output["claims"]=[]
    for source in raw["claims"]:
        span=unique_literal_span(description,source["evidence_quote"])
        claim={key:json.loads(json.dumps(value,ensure_ascii=False)) for key,value in source.items() if key not in {"semantic_text_es","evidence_quote"}}
        claim["text_es"]=source["evidence_quote"];claim["span"]=span
        claim["claim_id"]=content_id("i20-claim-sha256-",claim,"claim_id")
        output["claims"].append(claim)
    output["visible_text"]=[]
    for source in raw["visible_text"]:
        item={key:json.loads(json.dumps(value,ensure_ascii=False)) for key,value in source.items() if key!="evidence_quote"}
        item["span"]=unique_literal_span(description,source["evidence_quote"]);output["visible_text"].append(item)
    validate_annotation_draft_contract(output);_validate_claims(output)
    return output


def _contract_schema(schema_name: str) -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / schema_name
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _validate_schema(document: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as error:
        path = ".".join(str(part) for part in error.absolute_path) or "document"
        raise I20AssistedError(f"contrato JSON inválido en {path}: {error.message}") from error


def _validate_contract(document: Mapping[str, Any], schema_name: str) -> None:
    _validate_schema(document, _contract_schema(schema_name))


def _record_schema(contract_schema: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "$defs": contract_schema.get("$defs", {}),
        **contract_schema["properties"]["records"]["items"],
    }


def validate_scene_draft_contract(draft: Mapping[str, Any]) -> None:
    schema = _contract_schema("i20_assisted_scene_proposals.schema.json")
    _validate_schema(draft, schema["properties"]["records"]["items"]["properties"]["ai_draft"])


def validate_annotation_draft_contract(draft: Mapping[str, Any]) -> None:
    schema = _contract_schema("i20_assisted_annotation_proposals.schema.json")
    _validate_schema(draft, {"$ref": "#/$defs/draft", "$defs": schema["$defs"]})


def normalize_annotation_draft(raw: Mapping[str, Any]) -> dict[str, Any]:
    draft=json.loads(json.dumps(raw,ensure_ascii=False))
    for claim in draft["claims"]:
        claim["claim_id"]=content_id("i20-claim-sha256-",claim,"claim_id")
    validate_annotation_draft_contract(draft);_validate_claims(draft);return draft


def task_identity(*, kind: str, target_id: str, image_sha256: Sequence[str], model: Mapping[str, Any], prompt_sha256: str, schema_sha256: str, instructions_sha256: str) -> dict[str, Any]:
    if kind not in {"scene_pair", "annotation"}:
        raise I20AssistedError("tipo de tarea asistida inválido")
    return {
        "contract_version": "i20-assisted-cache-entry-v1",
        "task_kind": kind,
        "target_id": target_id,
        "image_sha256": list(image_sha256),
        "model_id": model["model_id"],
        "model_revision": model["revision"],
        "weight_sha256": model["weight_sha256"],
        "processor_policy": model.get("processor_policy", "qwen3-vl-auto-processor-local-files-only-v1"),
        "prompt_sha256": prompt_sha256,
        "schema_sha256": schema_sha256,
        "decoding": model["decoding"],
        "instructions_sha256": instructions_sha256,
    }


def cache_entry_id(identity: Mapping[str, Any]) -> str:
    return "i20-assist-cache-sha256-" + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def validate_plan(document: Mapping[str, Any], *, annotation_fixture: Mapping[str, Any], scene_fixture: Mapping[str, Any]) -> None:
    reject_forbidden(document)
    if document.get("contract_version") != "i20-assisted-annotation-plan-v1":
        raise I20AssistedError("plan asistido incompatible")
    if document.get("plan_id") != content_id("i20-assist-plan-sha256-", document, "plan_id"):
        raise I20AssistedError("plan_id inválido")
    source = document["source"]
    if source["expected_observation_ids"] != list(EXPECTED_IDS):
        raise I20AssistedError("I01-I20 incompleto")
    expected_pairs = [row["pair_id"] for row in scene_fixture["records"]]
    if source["expected_scene_pair_ids"] != expected_pairs or document["jobs"]["scene_order"] != expected_pairs:
        raise I20AssistedError("pares de escena incompatibles")
    if document["jobs"]["annotation_order"] != list(EXPECTED_IDS) or document["jobs"]["scene_job_count"] != 12 or document["jobs"]["annotation_job_count"] != 20:
        raise I20AssistedError("cardinalidad de jobs inválida")
    if source["annotation_fixture_id"] != annotation_fixture["fixture_id"] or source["scene_fixture_sha256"] != scene_fixture["fixture_sha256"]:
        raise I20AssistedError("fixtures incompatibles")
    if not all(value is False for value in document["blinding"].values()):
        raise I20AssistedError("plan contiene señales prohibidas")
    if document["generator"]["decoding"]["do_sample"] is not False or document["generator"]["decoding"]["temperature"] != 0:
        raise I20AssistedError("generación no determinista")


def _validate_claims(draft: Mapping[str, Any]) -> None:
    description = draft["description_es"]
    seen = set()
    for claim in draft["claims"]:
        start, end = claim["span"]["start"], claim["span"]["end"]
        if not 0 <= start < end <= len(description) or description[start:end] != claim["text_es"]:
            raise I20AssistedError("span de claim asistido no literal")
        expected = content_id("i20-claim-sha256-", claim, "claim_id")
        if claim["claim_id"] != expected or expected in seen:
            raise I20AssistedError("claim_id asistido inválido o duplicado")
        seen.add(expected)
        if claim["kind"] in {"camera_frame_relation", "egocentric_relation"} and not claim["requires_orientation"]:
            raise I20AssistedError("relación asistida sin orientación")
        if claim["orientation_frame"] == "cardinal_verified":
            raise I20AssistedError("VLM no puede verificar orientación cardinal")
    for text in draft["visible_text"]:
        start, end = text["span"]["start"], text["span"]["end"]
        if not 0 <= start < end <= len(description):
            raise I20AssistedError("span de texto visible inválido")
        if text["legibility"] in {"unreadable", "uncertain"} and text["transcription_es"] is not None:
            raise I20AssistedError("texto ilegible no puede transcribirse")
        if text["legibility"] in {"readable", "partially_readable"} and not text["transcription_es"]:
            raise I20AssistedError("texto legible sin transcripción")
    orientation = draft["orientation"]
    if orientation["status"] != "unknown" or orientation["bearing_degrees"] is not None or orientation["uncertainty_degrees"] is not None or orientation["meaning"] != "unknown" or orientation["cardinal_conversion_allowed"]:
        raise I20AssistedError("borrador visual no puede inferir orientación geográfica")
    if draft["human_review_required"] is not True:
        raise I20AssistedError("borrador no exige revisión humana")


def validate_annotation_proposals(document: Mapping[str, Any], *, plan: Mapping[str, Any], fixture: Mapping[str, Any]) -> None:
    _validate_contract(document, "i20_assisted_annotation_proposals.schema.json")
    reject_forbidden(document)
    if document.get("contract_version") != "i20-assisted-annotation-proposals-v1" or document.get("plan_id") != plan["plan_id"] or document.get("annotation_fixture_id") != fixture["fixture_id"]:
        raise I20AssistedError("propuestas de anotación incompatibles")
    records = document.get("records", [])
    if [row.get("observation_id") for row in records] != list(EXPECTED_IDS):
        raise I20AssistedError("propuestas I01-I20 incompletas o desordenadas")
    fixture_by = {row["observation_id"]: row for row in fixture["observations"]}
    for row in records:
        expected_fixture = fixture_by[row["observation_id"]]
        if row["reference_asset_id"] != expected_fixture["reference_asset_id"] or row["reference_asset_sha256"] != expected_fixture["reference_asset_sha256"] or row["proposal_status"] != "proposed":
            raise I20AssistedError("referencia de propuesta alterada")
        _validate_claims(row["ai_draft"])
        expected = content_id("i20-assist-annotation-proposal-sha256-", row, "proposal_id")
        if row["proposal_id"] != expected:
            raise I20AssistedError("proposal_id de anotación inválido")
    if document.get("artifact_id") != content_id("i20-assist-annotation-proposals-sha256-", document, "artifact_id"):
        raise I20AssistedError("artifact_id de anotaciones inválido")


def validate_annotation_proposal_record(row: Mapping[str, Any], *, fixture_row: Mapping[str, Any]) -> None:
    schema = _contract_schema("i20_assisted_annotation_proposals.schema.json")
    _validate_schema(row, _record_schema(schema))
    reject_forbidden(row)
    if row["observation_id"] != fixture_row["observation_id"] or row["reference_asset_id"] != fixture_row["reference_asset_id"] or row["reference_asset_sha256"] != fixture_row["reference_asset_sha256"] or row["proposal_status"] != "proposed":
        raise I20AssistedError("referencia de propuesta alterada")
    _validate_claims(row["ai_draft"])
    if row["proposal_id"] != content_id("i20-assist-annotation-proposal-sha256-", row, "proposal_id"):
        raise I20AssistedError("proposal_id de anotación inválido")


def validate_scene_proposals(document: Mapping[str, Any], *, plan: Mapping[str, Any], fixture: Mapping[str, Any], annotation_fixture: Mapping[str, Any]) -> None:
    _validate_contract(document, "i20_assisted_scene_proposals.schema.json")
    reject_forbidden(document)
    if document.get("contract_version") != "i20-assisted-scene-proposals-v1" or document.get("plan_id") != plan["plan_id"] or document.get("scene_fixture_sha256") != fixture["fixture_sha256"]:
        raise I20AssistedError("propuestas de escena incompatibles")
    expected = {row["pair_id"]: row for row in fixture["records"]}
    records = document.get("records", [])
    if [row.get("pair_id") for row in records] != list(expected):
        raise I20AssistedError("propuestas de escena incompletas o desordenadas")
    assets = {row["observation_id"]: row["reference_asset_sha256"] for row in annotation_fixture["observations"]}
    for row in records:
        pair = expected[row["pair_id"]]
        if (row["left_observation_id"], row["right_observation_id"]) != (pair["left_observation_id"], pair["right_observation_id"]):
            raise I20AssistedError("par de escena alterado")
        if row["left_reference_asset_sha256"] != assets[row["left_observation_id"]] or row["right_reference_asset_sha256"] != assets[row["right_observation_id"]]:
            raise I20AssistedError("hash de escena alterado")
        draft = row["ai_draft"]
        if draft["human_review_required"] is not True:
            raise I20AssistedError("escena sin revisión humana requerida")
        if draft["decision"] == "CLEAR" and (draft["same_scene"] != "no" or draft["field_of_view_overlap"] != "no" or draft["same_place_different_frame"] == "uncertain"):
            raise I20AssistedError("CLEAR asistido no conservador")
        if row["proposal_id"] != content_id("i20-assist-scene-proposal-sha256-", row, "proposal_id"):
            raise I20AssistedError("proposal_id de escena inválido")
    if document.get("artifact_id") != content_id("i20-assist-scene-proposals-sha256-", document, "artifact_id"):
        raise I20AssistedError("artifact_id de escenas inválido")


def validate_scene_proposal_record(row: Mapping[str, Any], *, fixture_row: Mapping[str, Any], asset_sha256: Mapping[str, str]) -> None:
    schema = _contract_schema("i20_assisted_scene_proposals.schema.json")
    _validate_schema(row, _record_schema(schema))
    reject_forbidden(row)
    if (row["pair_id"], row["left_observation_id"], row["right_observation_id"]) != (fixture_row["pair_id"], fixture_row["left_observation_id"], fixture_row["right_observation_id"]):
        raise I20AssistedError("par de escena alterado")
    if row["left_reference_asset_sha256"] != asset_sha256[row["left_observation_id"]] or row["right_reference_asset_sha256"] != asset_sha256[row["right_observation_id"]]:
        raise I20AssistedError("hash de escena alterado")
    draft = row["ai_draft"]
    if draft["decision"] == "CLEAR" and (draft["same_scene"] != "no" or draft["field_of_view_overlap"] != "no" or draft["same_place_different_frame"] == "uncertain"):
        raise I20AssistedError("CLEAR asistido no conservador")
    if row["proposal_id"] != content_id("i20-assist-scene-proposal-sha256-", row, "proposal_id"):
        raise I20AssistedError("proposal_id de escena inválido")


def validate_human_decisions(document: Mapping[str, Any], *, scene_proposals: Mapping[str, Any], annotation_proposals: Mapping[str, Any]) -> dict[str, int]:
    reject_forbidden(document)
    if document.get("contract_version") != "i20-assisted-human-decisions-v1":
        raise I20AssistedError("decisiones humanas asistidas incompatibles")
    proposals = {row["proposal_id"]: ("scene_pair", row["pair_id"], row["ai_draft"]) for row in scene_proposals["records"]}
    proposals.update({row["proposal_id"]: ("annotation", row["observation_id"], row["ai_draft"]) for row in annotation_proposals["records"]})
    seen = set(); counts = {state: 0 for state in sorted(HUMAN_STATES)}
    for row in document.get("decisions", []):
        if row["status"] not in HUMAN_STATES or row["proposal_id"] not in proposals:
            raise I20AssistedError("decisión humana desconocida")
        kind, target, original = proposals[row["proposal_id"]]
        if row["target_kind"] != kind or row["target_id"] != target or row["proposal_id"] in seen:
            raise I20AssistedError("target humano alterado o duplicado")
        seen.add(row["proposal_id"]); counts[row["status"]] += 1
        if row["status"] == "pending" and (not row["reviewer_pseudonym"] or row["reviewed_at_utc"] is not None or row["human_revision"] is not None):
            raise I20AssistedError("pending humano incoherente")
        if row["status"] == "reviewed" and (not row["reviewer_pseudonym"] or not row["reviewed_at_utc"] or row["human_revision"] is not None):
            raise I20AssistedError("reviewed humano incoherente")
        if row["status"] == "corrected":
            if not row["reviewer_pseudonym"] or not row["reviewed_at_utc"] or not isinstance(row["human_revision"], Mapping) or canonical_bytes(row["human_revision"]) == canonical_bytes(original):
                raise I20AssistedError("corrected sin corrección explícita")
            if kind == "annotation": _validate_claims(row["human_revision"])
        if row["status"] in {"rejected", "unresolved"} and (not row["reviewer_pseudonym"] or not row["reviewed_at_utc"] or row["human_revision"] is not None or not row["reason_codes"]):
            raise I20AssistedError("rechazo/duda sin razón humana")
        if row["decision_id"] != content_id("i20-assist-human-decision-sha256-", row, "decision_id"):
            raise I20AssistedError("decision_id inválido")
    if document.get("artifact_id") != content_id("i20-assist-human-decisions-sha256-", document, "artifact_id"):
        raise I20AssistedError("artifact_id de decisiones inválido")
    return counts
