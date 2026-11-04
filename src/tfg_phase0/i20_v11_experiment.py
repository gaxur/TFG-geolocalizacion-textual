"""Preparación CPU del experimento pareado v10/v11 y sidecars semánticos."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .i20_assisted_annotation import I20AssistedError, content_id
from .i20_preparation import canonical_bytes


DEVELOPMENT_TARGETS = ("I10", "I12", "I16")


def annotation_prompt_v11() -> str:
    return (
        "Describe exclusivamente lo observable en esta fotografía urbana, en español natural y conciso. No uses mapas, coordenadas, "
        "OSM, rankings, GT, metadatos o conocimiento externo. Prioriza indicios visuales discriminativos: objetos, atributos, estructura, "
        "relaciones en el encuadre y texto realmente legible. Después de redactar description_es, representa como claims las principales "
        "evidencias directamente observables que hayas descrito. Cuando existan, incluye evidencias no textuales además del texto visible; "
        "no cierres claims tras un único texto visible si la descripción contiene otros indicios discriminativos. No fuerces tipos ausentes, "
        "no conviertas dudas en hechos y no generes claims redundantes. Evita inventarios exhaustivos de ausencias, repeticiones y detalles "
        "genéricos. La descripción debe tener entre 80 y 900 caracteres. Para cada claim devuelve semantic_text_es como interpretación "
        "atómica y evidence_quote como una cita exacta, no vacía y copiada una sola vez de description_es; no calcules offsets. Un claim "
        "visible_text debe usar requires_ocr=true. En los demás claims, requires_ocr solo será true si verificar la evidencia depende de leer "
        "o transcribir texto visible. Para visible_text, evidence_quote también debe ser una cita exacta y única de description_es. No "
        "inventes nombres o lugares. La orientación cardinal debe quedar unknown. La salida es una propuesta IA pendiente de revisión "
        "humana. Devuelve solo JSON estricto conforme al schema."
    )


def validate_v11_ocr_policy(raw: Mapping[str, Any]) -> None:
    for index, claim in enumerate(raw.get("claims", [])):
        if claim.get("kind") == "visible_text" and claim.get("requires_ocr") is not True:
            raise I20AssistedError(f"claim visible_text sin requires_ocr=true en {index}")


def select_blind_development_targets(annotation_fixture: Mapping[str, Any], scene_fixture: Mapping[str, Any]) -> tuple[str, ...]:
    degree={observation_id:0 for observation_id in annotation_fixture["expected_observation_ids"]}
    for row in scene_fixture["records"]:
        degree[row["left_observation_id"]]+=1;degree[row["right_observation_id"]]+=1
    selected=tuple(observation_id for observation_id in annotation_fixture["expected_observation_ids"][4:] if degree[observation_id]==0)[:3]
    if selected!=DEVELOPMENT_TARGETS:
        raise I20AssistedError("selección ciega de desarrollo incompatible")
    return selected


def semantic_sidecar_schema() -> dict[str, Any]:
    return {
        "$schema":"https://json-schema.org/draft/2020-12/schema",
        "$id":"i20_assisted_semantic_claims.schema.json",
        "type":"object","additionalProperties":False,
        "required":["schema_version","contract_version","sidecar_id","status","proposal_id","observation_id","reference_asset_sha256","generator_identity","description_sha256","claims"],
        "properties":{
            "schema_version":{"const":"1.0"},"contract_version":{"const":"i20-assisted-semantic-claims-v1"},
            "sidecar_id":{"type":"string","pattern":"^i20-semantic-sidecar-sha256-[0-9a-f]{64}$"},
            "status":{"const":"noncanonical_pending_human_review"},
            "proposal_id":{"type":"string","pattern":"^i20-assist-annotation-proposal-sha256-[0-9a-f]{64}$"},
            "observation_id":{"type":"string","pattern":"^I(?:0[1-9]|1[0-9]|20)$"},
            "reference_asset_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
            "generator_identity":{"type":"object","additionalProperties":False,"required":["model_id","model_revision","weight_sha256","prompt_sha256","schema_sha256","decoding_sha256","input_identity_sha256","raw_output_sha256"],"properties":{"model_id":{"type":"string","minLength":1},"model_revision":{"type":"string","pattern":"^[0-9a-f]{40}$"},"weight_sha256":{"type":"array","minItems":1,"items":{"type":"string","pattern":"^[0-9a-f]{64}$"}},"prompt_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"schema_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"decoding_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"input_identity_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"raw_output_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"}}},
            "description_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
            "claims":{"type":"array","minItems":1,"items":{"type":"object","additionalProperties":False,"required":["claim_id","kind","semantic_text_es","evidence_quote","span","requires_ocr","ocr_policy_status","semantic_relation","human_review_status"],"properties":{"claim_id":{"type":"string","pattern":"^i20-claim-sha256-[0-9a-f]{64}$"},"kind":{"type":"string","minLength":1},"semantic_text_es":{"type":"string","minLength":1},"evidence_quote":{"type":"string","minLength":1},"span":{"type":"object","additionalProperties":False,"required":["start","end"],"properties":{"start":{"type":"integer","minimum":0},"end":{"type":"integer","minimum":1}}},"requires_ocr":{"type":"boolean"},"ocr_policy_status":{"enum":["coherent","incoherent_pending_review"]},"semantic_relation":{"const":"generated_interpretation_of_literal_evidence"},"human_review_status":{"const":"pending"}}}}
        }
    }


def build_semantic_sidecar(*, raw: Mapping[str, Any], proposal: Mapping[str, Any], generator_identity: Mapping[str, Any]) -> dict[str, Any]:
    materialized=proposal["ai_draft"]["claims"]
    if len(raw["claims"])!=len(materialized):raise I20AssistedError("sidecar y propuesta difieren en cardinalidad")
    claims=[];description=raw["description_es"]
    for source,target in zip(raw["claims"],materialized,strict=True):
        span=target["span"]
        if source["kind"]!=target["kind"] or source["evidence_quote"]!=target["text_es"] or description[span["start"]:span["end"]]!=source["evidence_quote"]:
            raise I20AssistedError("enlace semántico/canónico inválido")
        coherent=source["kind"]!="visible_text" or source["requires_ocr"] is True
        claims.append({"claim_id":target["claim_id"],"kind":target["kind"],"semantic_text_es":source["semantic_text_es"],"evidence_quote":source["evidence_quote"],"span":dict(span),"requires_ocr":source["requires_ocr"],"ocr_policy_status":"coherent" if coherent else "incoherent_pending_review","semantic_relation":"generated_interpretation_of_literal_evidence","human_review_status":"pending"})
    document={"schema_version":"1.0","contract_version":"i20-assisted-semantic-claims-v1","sidecar_id":"","status":"noncanonical_pending_human_review","proposal_id":proposal["proposal_id"],"observation_id":proposal["observation_id"],"reference_asset_sha256":proposal["reference_asset_sha256"],"generator_identity":dict(generator_identity),"description_sha256":hashlib.sha256(description.encode()).hexdigest(),"claims":claims}
    document["sidecar_id"]=content_id("i20-semantic-sidecar-sha256-",document,"sidecar_id")
    return document
