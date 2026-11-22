"""Nucleo offline para preparar DialogueVPR visual sin activar el runtime D098."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.tfg_phase0.camera_candidate_spatial import (
    annotate_ambiguity,
    classify_camera_candidate,
)


CONTEXT_CONTRACT = "dialogue-visual-generative-context-v1"
REQUEST_CONTRACT = "dialogue-visual-generative-worker-request-v1"
DECISION_CONTRACT = "dialogue-visual-generative-decision-v1"
POLICY_ID = "dialogue-vpr-visual-generative-offline-v1"
MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
MODEL_REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
STOP_REASONS = {
    "NO_CACHED_IMAGES",
    "INSUFFICIENT_CANDIDATE_COVERAGE",
    "NO_DISCRIMINATIVE_VISIBLE_FEATURE",
    "IMAGE_QUALITY_INSUFFICIENT",
    "AMBIGUOUS_OR_SHARED_EVIDENCE",
    "OUTPUT_INVALID",
    "WORKER_TIMEOUT",
    "BUDGET_EXHAUSTED",
    "POLICY_BLOCKED",
}
FORBIDDEN_KEYS = {
    "ground_truth",
    "ground_truth_candidate",
    "target_candidate_id",
    "correct_candidate",
    "reference_coordinate",
    "evaluation_metrics",
}
UNCERTAIN_PATTERNS = (
    r"\bno\s+(?:lo\s+)?s[eé]\b",
    r"\bno\s+estoy\s+segur[oa]\b",
    r"\bni\s+idea\b",
    r"\bno\s+recuerdo\b",
)
UNOBSERVABLE_PATTERNS = (
    r"\bno\s+(?:lo\s+)?(?:puedo|consigo)\s+(?:ver|verlo|observar|observarlo|comprobar|comprobarlo|distinguir|distinguirlo)\b",
    r"\bno\s+se\s+(?:ve|distingue|aprecia)\b",
    r"\bqueda\s+fuera\s+de\s+(?:mi\s+)?vista\b",
)
STOP_PATTERNS = (
    r"\b(?:quiero|prefiero)\s+(?:parar|terminar|detener)\b",
    r"\btermina(?:r)?\s+(?:el\s+)?di[aá]logo\b",
    r"\bno\s+quiero\s+seguir\b",
)
CORRECTION_PATTERNS = (r"\bme\s+corrijo\b", r"\bcorrecci[oó]n\b", r"\ben\s+realidad\b")


class VisualDialogueContractError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def content_id(prefix: str, value: Any) -> str:
    return f"{prefix}-sha256-{hashlib.sha256(canonical_bytes(value)).hexdigest()}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_sha256(path: Path) -> str:
    if path.is_file():
        return file_sha256(path)
    if not path.is_dir():
        raise VisualDialogueContractError(f"artefacto ausente: {path}")
    rows = [
        {"path": item.relative_to(path).as_posix(), "sha256": file_sha256(item)}
        for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file())
    ]
    if not rows:
        raise VisualDialogueContractError(f"directorio de artefacto vacio: {path}")
    return hashlib.sha256(canonical_bytes(rows)).hexdigest()


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(char for char in normalized if not unicodedata.combining(char)).split())


def reject_forbidden_inputs(value: Any, path: str = "input") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).casefold()
            if lowered in FORBIDDEN_KEYS or re.fullmatch(r"h(?:3[8-9]|[4-5][0-9]|6[0-1])", lowered):
                raise VisualDialogueContractError(f"campo prohibido en {path}: {key}")
            reject_forbidden_inputs(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            reject_forbidden_inputs(child, f"{path}[{index}]")
    elif isinstance(value, str) and re.search(r"\bH(?:3[8-9]|[4-5][0-9]|6[0-1])\b", value, re.IGNORECASE):
        raise VisualDialogueContractError(f"conjunto reservado en {path}")


def interpret_free_answer(literal: str) -> dict[str, Any]:
    value = " ".join(str(literal).split())
    if not value or len(value) > 1200:
        raise VisualDialogueContractError("respuesta literal invalida")
    folded = _fold(value)
    if any(re.search(pattern, folded) for pattern in STOP_PATTERNS):
        kind = "stop"
    elif any(re.search(pattern, folded) for pattern in UNOBSERVABLE_PATTERNS):
        kind = "unobservable"
    elif any(re.search(pattern, folded) for pattern in UNCERTAIN_PATTERNS):
        kind = "unknown"
    elif any(re.search(pattern, folded) for pattern in CORRECTION_PATTERNS):
        kind = "correction"
    elif len(folded.split()) < 2 or folded in {"si", "no", "quizas", "puede ser"}:
        kind = "ambiguous"
    else:
        kind = "informative"
    return {
        "contract_version": "dialogue-free-answer-interpretation-v1",
        "literal": value,
        "literal_sha256": hashlib.sha256(value.encode()).hexdigest(),
        "kind": kind,
        "negative_evidence_permitted": kind not in {"unknown", "unobservable", "ambiguous"},
        "blocks_equivalent_follow_up": kind in {"unknown", "unobservable"},
    }


def _validate_ranking(ranking: Mapping[str, Any], reserve_size: int) -> list[dict[str, Any]]:
    reject_forbidden_inputs(ranking, "ranking")
    rows = ranking.get("results")
    if not isinstance(rows, list) or len(rows) < reserve_size:
        raise VisualDialogueContractError("ranking insuficiente")
    output = []
    seen = set()
    for index, row in enumerate(rows[:reserve_size], start=1):
        if (
            row.get("rank") != index
            or not isinstance(row.get("candidate_id"), str)
            or row["candidate_id"] in seen
            or not all(isinstance(row.get(key), (int, float)) and math.isfinite(row[key]) for key in ("latitude", "longitude", "cosine_similarity"))
        ):
            raise VisualDialogueContractError("fila de ranking invalida")
        seen.add(row["candidate_id"])
        output.append(dict(row))
    return output


def select_diverse_candidates(
    ranking: Mapping[str, Any],
    *,
    reserve_size: int = 20,
    protected_count: int = 3,
    panel_candidates: int = 6,
) -> list[dict[str, Any]]:
    if not 1 <= protected_count <= panel_candidates <= reserve_size:
        raise VisualDialogueContractError("presupuesto de candidatos invalido")
    rows = _validate_ranking(ranking, reserve_size)
    selected = list(rows[:protected_count])
    remaining = rows[protected_count:]
    while len(selected) < panel_candidates and remaining:
        def utility(row: Mapping[str, Any]) -> tuple[float, int]:
            minimum = min(
                _haversine_m(row["latitude"], row["longitude"], prior["latitude"], prior["longitude"])
                for prior in selected
            )
            return minimum, -int(row["rank"])

        next_row = max(remaining, key=utility)
        selected.append(next_row)
        remaining = [row for row in remaining if row["candidate_id"] != next_row["candidate_id"]]
    return selected


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def load_cache_manifest(cache_root: Path) -> dict[str, dict[str, Any]]:
    root = cache_root.resolve()
    metadata_root = root / "metadata"
    if not metadata_root.is_dir():
        raise VisualDialogueContractError("metadata de cache ausente")
    assets = {}
    for metadata_path in sorted(metadata_root.glob("*.json")):
        row = json.loads(metadata_path.read_text(encoding="utf-8"))
        reject_forbidden_inputs(row, f"cache.{metadata_path.name}")
        image_id = str(row.get("image_id", ""))
        logical = Path(str(row.get("logical_path", "")))
        path = (root / logical).resolve()
        if (
            not image_id
            or logical.is_absolute()
            or ".." in logical.parts
            or root not in path.parents
            or not path.is_file()
            or path.is_symlink()
            or row.get("sha256") != file_sha256(path)
            or row.get("size_bytes") != path.stat().st_size
        ):
            continue
        assets[image_id] = {**row, "cache_path": path}
    return assets


def _association_priority(row: Mapping[str, Any]) -> tuple[Any, ...]:
    category = {
        "camera_inside_candidate": 0,
        "camera_outside_view_compatible": 1,
        "spatially_ambiguous": 2,
        "insufficient_orientation_metadata": 3,
        "orientation_incompatible": 4,
        "not_eligible": 5,
    }.get(row["classification"], 6)
    return (
        category,
        row.get("competing_candidate_count", 0),
        row["surface_distance_m"],
        row["center_distance_m"],
        -(row.get("quality_score") if row.get("quality_score") is not None else -1),
        -((row.get("width_px") or 0) * (row.get("height_px") or 0)),
        str(row["image_id"]),
    )


def build_cached_visual_context(
    *,
    session_id: str,
    iteration: int,
    description_original: str,
    description_effective: str,
    history: Sequence[Mapping[str, Any]],
    ranking: Mapping[str, Any],
    catalog: Mapping[str, Any],
    inventory: Mapping[str, Any],
    cache_root: Path,
    reserve_size: int = 20,
    panel_candidates: int = 6,
    protected_count: int = 3,
    maximum_images: int = 8,
    maximum_images_per_candidate: int = 2,
    maximum_radius_m: float = 100.0,
) -> dict[str, Any]:
    if not session_id or iteration not in range(4) or not description_original or not description_effective:
        raise VisualDialogueContractError("identidad o texto de contexto invalido")
    if maximum_images > 8 or maximum_images_per_candidate > 2 or maximum_images < panel_candidates:
        raise VisualDialogueContractError("presupuesto visual invalido")
    reject_forbidden_inputs(history, "history")
    reject_forbidden_inputs(inventory, "inventory")
    selected = select_diverse_candidates(
        ranking,
        reserve_size=reserve_size,
        protected_count=protected_count,
        panel_candidates=panel_candidates,
    )
    catalog_rows = {row["candidate_id"]: row for row in catalog.get("candidates", [])}
    if any(row["candidate_id"] not in catalog_rows for row in selected):
        raise VisualDialogueContractError("candidato sin geometria de catalogo")
    cached = load_cache_manifest(cache_root)
    inventory_images = [dict(row) for row in inventory.get("images", []) if str(row.get("image_id")) in cached]
    associations = []
    for candidate in selected:
        geometry = catalog_rows[candidate["candidate_id"]]
        for image in inventory_images:
            spatial = classify_camera_candidate(
                image,
                geometry,
                cell_size_m=50.0,
                round_radius_m=maximum_radius_m,
            )
            if not spatial["within_round"]:
                continue
            associations.append(
                {
                    "global_record_id": str(image["image_id"]),
                    "image_id": str(image["image_id"]),
                    "candidate_id": candidate["candidate_id"],
                    "candidate_rank": candidate["rank"],
                    "sequence_id": image.get("sequence_id"),
                    "quality_score": image.get("quality_score"),
                    "width_px": image.get("width_px"),
                    "height_px": image.get("height_px"),
                    **spatial,
                }
            )
    associations = annotate_ambiguity(associations)
    by_candidate = {}
    for candidate in selected:
        rows = [row for row in associations if row["candidate_id"] == candidate["candidate_id"]]
        by_candidate[candidate["candidate_id"]] = sorted(rows, key=_association_priority)

    chosen = []
    chosen_ids = set()
    chosen_by_candidate: dict[str, list[dict[str, Any]]] = {row["candidate_id"]: [] for row in selected}

    def add_for(candidate_id: str, row: Mapping[str, Any]) -> bool:
        if len(chosen) >= maximum_images or len(chosen_by_candidate[candidate_id]) >= maximum_images_per_candidate:
            return False
        if row["image_id"] in chosen_ids:
            return False
        chosen_ids.add(row["image_id"])
        chosen.append(dict(row))
        chosen_by_candidate[candidate_id].append(dict(row))
        return True

    for candidate in selected:
        rows = by_candidate[candidate["candidate_id"]]
        if rows:
            add_for(candidate["candidate_id"], rows[0])
    for candidate in selected:
        if len(chosen) >= maximum_images:
            break
        candidate_id = candidate["candidate_id"]
        sequences = {row.get("sequence_id") for row in chosen_by_candidate[candidate_id]}
        for row in by_candidate[candidate_id][1:]:
            if row.get("sequence_id") not in sequences and add_for(candidate_id, row):
                break

    images = []
    for row in chosen:
        metadata = cached[row["image_id"]]
        images.append(
            {
                "image_id": row["image_id"],
                "sha256": metadata["sha256"],
                "logical_path": metadata["logical_path"],
                "media_type": metadata["media_type"],
                "size_bytes": metadata["size_bytes"],
                "license": metadata.get("license"),
                "attribution": metadata.get("attribution"),
                "source_page_url": metadata.get("source_page_url"),
                "cache_status": "reused_verified_cache",
            }
        )
    candidates = []
    for position, candidate in enumerate(selected, start=1):
        candidate_id = candidate["candidate_id"]
        candidate_images = chosen_by_candidate[candidate_id]
        candidates.append(
            {
                "slot_id": f"candidate-{position:02d}",
                "candidate_id": candidate_id,
                "ct2l_rank": candidate["rank"],
                "ct2l_score": candidate["cosine_similarity"],
                "protected_top3": candidate["rank"] <= protected_count,
                "coverage_status": "selected" if candidate_images else "insufficient_evidence",
                "selected_image_ids": [row["image_id"] for row in candidate_images],
            }
        )
    context = {
        "schema_version": "1.0",
        "contract_version": CONTEXT_CONTRACT,
        "context_id": "",
        "policy_id": POLICY_ID,
        "session_id": session_id,
        "iteration": iteration,
        "question_budget": {"maximum": 3, "used": len(history), "remaining": max(0, 3 - len(history))},
        "description_original": description_original,
        "description_effective": description_effective,
        "history": [dict(row) for row in history],
        "ranking": {
            "gallery_id": ranking.get("gallery_id", "madrid-50m"),
            "ranking_sha256": hashlib.sha256(canonical_bytes(ranking)).hexdigest(),
            "reserve_size": reserve_size,
            "candidate_count": len(ranking.get("results", [])),
        },
        "selection": {
            "panel_candidates": panel_candidates,
            "protected_top3": protected_count,
            "maximum_images": maximum_images,
            "maximum_images_per_candidate": maximum_images_per_candidate,
            "candidate_method": "top3_plus_spatial_farthest_first_without_gt",
            "image_method": "geometry_metadata_cache_first_sequence_diversity",
        },
        "candidates": candidates,
        "images": images,
        "associations": [
            {
                "candidate_id": row["candidate_id"],
                "candidate_rank": row["candidate_rank"],
                "image_id": row["image_id"],
                "within_round": row["within_round"],
                "classification": row["classification"],
                "surface_distance_m": round(row["surface_distance_m"], 6),
                "center_distance_m": round(row["center_distance_m"], 6),
                "orientation_status": row["fov_basis"],
                "ambiguity_status": row["ambiguity_status"],
                "competing_candidate_ids": row["competing_candidate_ids"],
                "limitations": row["limitations"],
            }
            for row in chosen
        ],
        "protocol": {
            "ground_truth_used": False,
            "evaluation_metrics_used": False,
            "reference_images_used": False,
            "reserved_sets_used": False,
            "network_used": False,
            "pixels_used_for_selection": False,
            "vlm_outputs_used_for_selection": False,
            "ranking_scores_modified": False,
        },
        "coverage_summary": {
            "requested_candidates": panel_candidates,
            "covered_candidates": sum(bool(row["selected_image_ids"]) for row in candidates),
            "selected_images": len(images),
            "evidence_sufficient_for_vlm": len(images) >= 2 and sum(bool(row["selected_image_ids"]) for row in candidates) >= 2,
        },
    }
    context["context_id"] = content_id("dialogue-visual-context", {key: value for key, value in context.items() if key != "context_id"})
    return context


def build_question_prompt(context: Mapping[str, Any]) -> str:
    history = "\n".join(
        f"Pregunta {index}: {row.get('question', '')}\nRespuesta literal: {row.get('answer_literal', '')}\nInterpretacion: {row.get('answer_interpretation', {}).get('kind', 'unknown')}"
        for index, row in enumerate(context.get("history", []), start=1)
    ) or "Sin turnos anteriores."
    slots = "\n".join(
        f"{row['slot_id']}: imagenes {', '.join(row['selected_image_ids']) or 'ninguna'}; cobertura {row['coverage_status']}"
        for row in context["candidates"]
    )
    return f"""Eres el modulo visual de preguntas de un sistema de recuperacion geografica. CrossText2Loc ya ha recuperado candidatos; no debes adivinar una ubicacion ni cambiar sus scores.

Compara exclusivamente las fotografias candidatas suministradas y el historial. Formula como maximo una pregunta natural en espanol que una persona en el lugar pueda responder y que distinga al menos dos candidatos. No afirmes que una fotografia reproduce la perspectiva exacta del usuario. No inventes elementos, nombres ni texto. No repitas preguntas equivalentes ni insistas en algo que la persona declaro desconocido o no observable. Si la evidencia es compartida, ambigua, insuficiente o no permite una pregunta respondible, devuelve STOP.

No expongas candidate_id, image_id, ranks, scores, coordenadas o razonamiento interno. La explicacion auditable debe citar solo IDs de entrada y claims visuales breves. Devuelve un unico JSON que cumpla el schema ASK/STOP, sin markdown.

Descripcion original:
{context['description_original']}

Descripcion efectiva de recuperacion:
{context['description_effective']}

Historial:
{history}

Slots visuales:
{slots}
"""


def build_compact_question_prompt(context: Mapping[str, Any]) -> str:
    history = " | ".join(
        f"P{index}:{row.get('question','')} R{index}:{row.get('answer_literal','')} ({row.get('answer_interpretation',{}).get('kind','unknown')})"
        for index,row in enumerate(context.get("history",[]),1)
    ) or "ninguno"
    image_numbers={row["image_id"]:index for index,row in enumerate(context["images"],1)}
    slots="; ".join(f"{row['slot_id']}=imagenes {','.join(str(image_numbers[value]) for value in row['selected_image_ids']) or 'ninguna'}" for row in context["candidates"])
    return f"""Genera la siguiente pregunta visual de DialogueVPR. CrossText2Loc ya recuperó candidatos: no adivines ubicación ni alteres scores.
Usa solo las imágenes, descripción e historial. Devuelve un único JSON ASK/STOP del schema. ASK: una pregunta natural en español que distinga al menos dos slots, cite evidencia visible de imágenes de entrada, no invente ni revele slots/IDs/ranks/coordenadas y permita «no lo sé/no puedo comprobarlo». No repitas ni insistas en algo no observable. STOP si no hay diferencia visible, grounded y respondible. Sin razonamiento interno ni markdown.
Original: {context['description_original']}
Texto CT2L: {context['description_effective']}
Historial: {history}
Panel: {slots}"""


def build_worker_request(context: Mapping[str, Any], *, max_new_tokens: int = 512, prompt_variant: str = "full") -> dict[str, Any]:
    if not context.get("coverage_summary", {}).get("evidence_sufficient_for_vlm"):
        raise VisualDialogueContractError("contexto sin evidencia suficiente para VLM")
    if max_new_tokens not in {256,512}:raise VisualDialogueContractError("presupuesto de generacion visual no versionado")
    if prompt_variant not in {"full","compact"}:raise VisualDialogueContractError("variante de prompt visual invalida")
    prompt = build_compact_question_prompt(context) if prompt_variant=="compact" else build_question_prompt(context)
    request = {
        "schema_version": "1.0",
        "contract_version": REQUEST_CONTRACT,
        "request_id": "",
        "context_id": context["context_id"],
        "model": {
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "dtype": "bfloat16",
            "attention": "sdpa",
            "local_files_only": True,
        },
        "prompt_version": "dialogue-visual-generative-question-compact-v1" if prompt_variant=="compact" else "dialogue-visual-generative-question-v1",
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "images": [
            {key: row[key] for key in ("image_id", "sha256", "logical_path", "media_type", "size_bytes")}
            for row in context["images"]
        ],
        "candidate_slots": [
            {key: row[key] for key in ("slot_id", "selected_image_ids", "coverage_status")}
            for row in context["candidates"]
        ],
        "generation": {"do_sample": False, "max_new_tokens": max_new_tokens, "batch_size": 1},
        "constraints": {
            "network_permitted": False,
            "ground_truth_permitted": False,
            "reserved_sets_permitted": False,
            "automatic_retries": 0,
            "maximum_inferences": 1,
        },
    }
    request["request_id"] = content_id("dialogue-visual-request", {key: value for key, value in request.items() if key != "request_id"})
    return request


def _question_tokens(text: str) -> set[str]:
    aliases = {"ves": "ver", "veo": "ver", "puedes": "", "puedo": "", "una": "", "uno": "", "con": ""}
    return {
        aliases.get(token, token)
        for token in re.findall(r"[a-z0-9]+", _fold(text))
        if len(token) > 2 and aliases.get(token, token)
    }


def questions_equivalent(left: str, right: str, threshold: float = 0.72) -> bool:
    a, b = _question_tokens(left), _question_tokens(right)
    return bool(a and b) and len(a & b) / len(a | b) >= threshold


def validate_decision(decision: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    allowed_top = {
        "schema_version",
        "contract_version",
        "action",
        "question",
        "intent_summary",
        "candidate_contrast",
        "expected_answer_type",
        "abstention_reason",
    }
    if set(decision) != allowed_top or decision.get("schema_version") != "1.0" or decision.get("contract_version") != DECISION_CONTRACT:
        raise VisualDialogueContractError("decision visual incompatible")
    action = decision.get("action")
    if action not in {"ASK", "STOP"}:
        raise VisualDialogueContractError("accion visual invalida")
    valid_candidates = {row["candidate_id"] for row in context["candidates"]}
    valid_slots = {row["slot_id"] for row in context["candidates"]}
    valid_images = {row["image_id"] for row in context["images"]}
    if action == "STOP":
        if decision.get("question") is not None or decision.get("intent_summary") is not None or decision.get("candidate_contrast") != [] or decision.get("expected_answer_type") is not None or decision.get("abstention_reason") not in STOP_REASONS:
            raise VisualDialogueContractError("STOP visual incompatible")
        return dict(decision)
    question = decision.get("question")
    if not isinstance(question, str) or not 8 <= len(question) <= 280 or "?" not in question:
        raise VisualDialogueContractError("pregunta visual invalida")
    folded = _fold(question)
    if any(candidate_id.casefold() in question.casefold() for candidate_id in valid_candidates) or any(slot.casefold() in question.casefold() for slot in valid_slots) or any(image_id in question for image_id in valid_images) or re.search(r"-?\d{1,3}\.\d{3,}", question):
        raise VisualDialogueContractError("pregunta filtra identificadores o coordenadas")
    if not any(term in folded for term in ("no lo se", "no lo sabes", "no puedo", "no se distingue", "no puedo comprobar")):
        raise VisualDialogueContractError("pregunta sin opcion de desconocimiento")
    prior_questions = [row.get("question", "") for row in context.get("history", [])]
    if any(questions_equivalent(question, prior) for prior in prior_questions if prior):
        raise VisualDialogueContractError("pregunta visual repetida")
    contrasts = decision.get("candidate_contrast")
    if not isinstance(contrasts, list) or not contrasts:
        raise VisualDialogueContractError("ASK sin contraste auditable")
    contrasted_candidates = set()
    for contrast in contrasts:
        if set(contrast) != {"candidate_ids", "image_ids", "visual_claim", "evidence_status"}:
            raise VisualDialogueContractError("contraste visual incompatible")
        candidates = contrast["candidate_ids"]
        images = contrast["image_ids"]
        if not isinstance(candidates, list) or not candidates or not set(candidates) <= valid_slots or not isinstance(images, list) or not images or not set(images) <= valid_images or contrast["evidence_status"] not in {"visible", "uncertain"} or not isinstance(contrast["visual_claim"], str) or not contrast["visual_claim"].strip():
            raise VisualDialogueContractError("contraste sin evidencia de entrada")
        contrasted_candidates.update(candidates)
    if len(contrasted_candidates) < 2 or decision.get("expected_answer_type") != "free_text" or decision.get("abstention_reason") is not None or not isinstance(decision.get("intent_summary"), str):
        raise VisualDialogueContractError("ASK no discrimina dos candidatos")
    return dict(decision)


def fail_closed_stop(reason: str) -> dict[str, Any]:
    if reason not in STOP_REASONS:
        reason = "OUTPUT_INVALID"
    return {
        "schema_version": "1.0",
        "contract_version": DECISION_CONTRACT,
        "action": "STOP",
        "question": None,
        "intent_summary": None,
        "candidate_contrast": [],
        "expected_answer_type": None,
        "abstention_reason": reason,
    }
