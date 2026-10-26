"""Smoke aislado de Qwen3-VL sobre fotografías Mapillary ya anotadas."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping


LEVELS = {"strong_match", "partial_match", "insufficient", "contradiction"}
FORBIDDEN_INPUT_FIELDS = {
    "query_id", "baseline_rank", "latitude", "longitude", "reference",
    "ground_truth", "distance_to_gt", "human_annotation", "utility",
}


class VLMSmokeError(ValueError):
    """El smoke VLM incumple su contrato o contiene información prohibida."""


def reject_forbidden_input(value: Any, *, path: str = "request") -> None:
    if isinstance(value, Mapping):
        forbidden = FORBIDDEN_INPUT_FIELDS.intersection(value)
        if forbidden:
            raise VLMSmokeError(f"campo prohibido en {path}: {sorted(forbidden)[0]}")
        for key, item in value.items():
            reject_forbidden_input(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_forbidden_input(item, path=f"{path}[{index}]")


def verification_prompt(description: str, candidate_id: str) -> str:
    request = {"candidate_id": candidate_id, "description": description}
    reject_forbidden_input(request)
    return (
        "Compara exclusivamente la fotografía con la descripción. No adivines la "
        "ubicación. Una ausencia en una vista parcial es no verificable, no una "
        "contradicción. Las relaciones izquierda/derecha son no verificables si la "
        "orientación no es inequívoca. Devuelve solo JSON válido, sin Markdown, con "
        "este formato exacto: {\"matches\":[\"...\"],\"contradictions\":[\"...\"],"
        "\"unverifiable\":[\"...\"],\"verification_level\":\"strong_match|"
        "partial_match|insufficient|contradiction\"}.\n"
        f"candidate_id opaco: {candidate_id}\nDescripción: {description}"
    )


def conservative_verification_prompt(description: str, candidate_id: str) -> str:
    request = {"candidate_id": candidate_id, "description": description}
    reject_forbidden_input(request)
    return (
        "Actúa como verificador visual conservador. Compara exclusivamente píxeles "
        "observables en ESTA fotografía con cada detalle de la descripción. No "
        "adivines la ubicación ni completes la escena por plausibilidad.\n"
        "Reglas obligatorias:\n"
        "1. matches: solo objetos o atributos inequívocamente visibles. Cita detalles "
        "atómicos; no copies una oración completa si solo ves una parte.\n"
        "2. Un nombre de comercio solo es match si el rótulo exacto es legible. Una "
        "fachada genérica no demuestra que sea una inmobiliaria, farmacia, hotel o tienda.\n"
        "3. Rasgos genéricos como calle, edificio, balcón, árbol o plaza no justifican "
        "strong_match por sí solos.\n"
        "4. La ausencia de un objeto en esta vista parcial nunca es contradicción: "
        "añádelo a unverifiable. contradictions exige evidencia visible incompatible "
        "e inequívoca, no mera ausencia.\n"
        "5. Izquierda, derecha, enfrente y detrás son unverifiable salvo que el marco "
        "de orientación de la descripción sea inequívocamente comparable con la cámara.\n"
        "6. Usa insufficient si la imagen es lejana, parcial, ambigua, de baja calidad "
        "o solo permite coincidencias genéricas. Ante la duda, unverifiable e insufficient.\n"
        "7. strong_match requiere varios rasgos distintivos visibles; partial_match "
        "requiere al menos un rasgo específico visible; contradiction requiere una "
        "incompatibilidad visible fuerte.\n"
        "Devuelve solo JSON válido, sin Markdown, con exactamente: "
        "{\"matches\":[\"...\"],\"contradictions\":[\"...\"],"
        "\"unverifiable\":[\"...\"],\"verification_level\":\"strong_match|"
        "partial_match|insufficient|contradiction\"}.\n"
        f"candidate_id opaco: {candidate_id}\nDescripción: {description}"
    )


def strict_proxy_level(utility: str) -> str:
    """Proxy descriptivo; utilidad fotográfica y compatibilidad no son equivalentes."""
    return {
        "useful": "strong_match",
        "partially_useful": "partial_match",
        "not_useful": "insufficient",
        "unverifiable": "insufficient",
    }[utility]


def parse_verification(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise VLMSmokeError("salida VLM no es JSON válido") from error
    expected = {"matches", "contradictions", "unverifiable", "verification_level"}
    if not isinstance(value, dict) or set(value) != expected:
        raise VLMSmokeError("campos de salida VLM incompatibles")
    if value["verification_level"] not in LEVELS:
        raise VLMSmokeError("verification_level inválido")
    for field in ("matches", "contradictions", "unverifiable"):
        if not isinstance(value[field], list) or not all(isinstance(item, str) and item.strip() for item in value[field]):
            raise VLMSmokeError(f"{field} debe ser una lista de textos no vacíos")
    return value


def expected_level_for_utility(utility: str) -> set[str]:
    return {
        "useful": {"strong_match", "partial_match"},
        "partially_useful": {"partial_match"},
        "not_useful": {"insufficient"},
        "unverifiable": {"insufficient"},
    }[utility]


def compare_human(vlm: Mapping[str, Any], human: Mapping[str, Any]) -> dict[str, Any]:
    utility = human["utility"]
    expected = expected_level_for_utility(utility)
    human_matches = [item for item in human.get("matches", []) if item.casefold() != "ninguna"]
    return {
        "human_utility": utility,
        "expected_vlm_levels": sorted(expected),
        "vlm_level": vlm["verification_level"],
        "level_agreement": vlm["verification_level"] in expected,
        "human_match_count": len(human_matches),
        "vlm_match_count": len(vlm["matches"]),
        "human_contradiction_count": len(human.get("contradictions", [])),
        "vlm_contradiction_count": len(vlm["contradictions"]),
    }
