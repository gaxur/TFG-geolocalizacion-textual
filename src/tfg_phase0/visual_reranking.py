"""Contratos mínimos para evidencia visual atómica y reranking offline."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .f4_evaluation import haversine_m
from .mapillary_visual_pilot import angular_difference, bearing_degrees, reject_ground_truth


VERDICTS = {"supported", "contradicted", "unverifiable"}
LIMITATIONS = {
    "none", "partial_view", "out_of_frame", "occluded", "too_far",
    "low_resolution", "unreadable_text", "orientation_not_comparable",
    "generation_failed",
}
GENERIC_OBJECTS = {"street", "building", "balcony", "tree", "person", "vehicle"}
OBJECT_PATTERNS = (
    ("pharmacy", r"\bfarmacia\b"), ("church", r"\biglesia\b"),
    ("theater", r"\bteatro\b"),
    ("hotel", r"\bhotel\b"), ("station", r"\b(?:metro|estaci[oó]n)\b"),
    ("square", r"\bplaza\b"), ("intersection", r"\bintersecci[oó]n\b"),
    ("street", r"\bcalle\b"), ("building", r"\bedificio\b"),
    ("balcony", r"\bbalcones?\b"), ("tree", r"\b[áa]rbol(?:es)?\b"),
    ("shop", r"\b(?:tienda|comercio|establecimiento)\b"),
    ("vehicle", r"\b(?:coche|coches|veh[ií]culo|veh[ií]culos|motocicleta|motocicletas)\b"),
    ("person", r"\b(?:persona|personas|gente|peat[oó]n|peatones)\b"),
    ("stairs", r"\bescaleras?\b"), ("tower", r"\btorre\b"),
    ("cross", r"\bcruz\b"), ("arch", r"\barco\b"),
    ("dome", r"\bc[uú]pula\b"), ("flag", r"\bbanderas?\b"),
    ("advertising_sign", r"\bcarteles?(?:\s+publicitarios?)?\b"),
)
ATTRIBUTE_PATTERNS = (
    ("surface", "cobblestone", r"\b(?:adoquinad[ao]s?|empedrad[ao]s?|adoquines)\b"),
    ("material", "brick", r"\b(?:ladrillo|ladrillos)\b"),
    ("material", "stone", r"\bpiedra\b"),
    ("color", "white", r"\bblanc[oa]s?\b"),
    ("color", "green", r"\bverde\b"),
    ("shape", "arched", r"\b(?:arco|arquead[ao])\b"),
    ("light", "illuminated", r"\b(?:luminosa?|luminoso|iluminad[ao])\b"),
)
RELATION_PATTERNS = (
    ("right_of_observer", r"\ba mi derecha\b"),
    ("left_of_observer", r"\ba mi izquierda\b"),
    ("in_front_of_observer", r"\b(?:enfrente|frente a m[ií])\b"),
    ("behind_observer", r"\bdetr[aá]s(?: de m[ií])?\b"),
)


class VisualRerankingError(ValueError):
    """Un artefacto visual o ranking experimental incumple su contrato."""


def compact_atomic_verdict_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "observed_evidence", "ocr_text", "limitations"],
        "properties": {
            "verdict": {"enum": sorted(VERDICTS)},
            "observed_evidence": {"type": ["string", "null"], "maxLength": 120},
            "ocr_text": {"type": ["string", "null"], "maxLength": 160},
            "limitations": {"type": "array", "maxItems": 2, "uniqueItems": True, "items": {"enum": sorted(LIMITATIONS - {"generation_failed"})}},
        },
    }


def verdict_only_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["verdict"], "properties": {"verdict": {"enum": sorted(VERDICTS)}}}


def verdict_only_prompt(claim: Mapping[str, Any]) -> str:
    return (
        "Clasifica UNA afirmación usando solo esta fotografía. "
        "supported: evidencia visual específica a favor. "
        "contradicted: evidencia visible explícitamente incompatible; la mera ausencia no contradice. "
        "unverifiable: ausencia, fuera de campo, oclusión, distancia, resolución o duda. "
        "Devuelve exactamente un JSON con un único campo verdict. "
        f"Tipo: {claim['kind']}. Afirmación: {json.dumps(claim['value'], ensure_ascii=False)}. "
        f"Texto fuente: {json.dumps(claim['evidence']['text'], ensure_ascii=False)}."
    )


def explanation_prompt(claim: Mapping[str, Any], verdict: str) -> str:
    return (
        f"El veredicto congelado es {verdict}. Justifícalo usando solo la fotografía en una frase breve. "
        "No cambies el veredicto. Si no hay evidencia visible suficiente, responde exactamente: no verificable. "
        f"Afirmación: {json.dumps(claim['value'], ensure_ascii=False)}."
    )


def parse_verdict_only(raw: str) -> str:
    if raw != raw.strip() or raw.startswith("```") or len(raw) > 80:
        raise VisualRerankingError("veredicto mínimo no es JSON estricto")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise VisualRerankingError("veredicto mínimo no es JSON") from error
    if not isinstance(value, dict) or set(value) != {"verdict"} or value["verdict"] not in VERDICTS:
        raise VisualRerankingError("veredicto mínimo incompatible")
    return value["verdict"]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _claim_id(payload: Mapping[str, Any]) -> str:
    return "visual-claim-sha256-" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _claim(source_sha: str, kind: str, value: Mapping[str, Any], text: str, start: int, end: int, *, specificity: str, requires_ocr: bool = False, requires_orientation: bool = False) -> dict[str, Any]:
    payload = {"source_text_sha256": source_sha, "kind": kind, "value": dict(value), "evidence": {"text": text[start:end], "span": {"start": start, "end": end}}, "specificity": specificity, "requires_ocr": requires_ocr, "requires_orientation": requires_orientation}
    return {"claim_id": _claim_id(payload), **payload}


def compile_atomic_claims(text: str, proper_toponyms: Sequence[str] = ()) -> dict[str, Any]:
    """Compila pistas literales mediante reglas; no interpreta relaciones implícitas."""
    if not isinstance(text, str) or not text.strip():
        raise VisualRerankingError("texto vacío")
    source_sha = hashlib.sha256(text.encode()).hexdigest()
    claims = []
    entity_mentions = []
    for object_type, pattern in OBJECT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            specificity = "generic" if object_type in GENERIC_OBJECTS else "distinctive"
            claims.append(_claim(source_sha, "object_presence", {"object_type": object_type}, text, match.start(), match.end(), specificity=specificity))
            entity_mentions.append((match.start(), object_type, match.start(), match.end()))
    for key, value, pattern in ATTRIBUTE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            preceding = [item for item in entity_mentions if item[0] <= match.start()]
            subject = preceding[-1][1] if preceding else "scene"
            claims.append(_claim(source_sha, "attribute", {"subject_type": subject, "attribute": key, "attribute_value": value}, text, match.start(), match.end(), specificity="distinctive"))
    for relation, pattern in RELATION_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            following = [item for item in entity_mentions if item[0] >= match.end()]
            subject = following[0][1] if following else "unknown"
            claims.append(_claim(source_sha, "egocentric_relation", {"subject_type": subject, "relation": relation}, text, match.start(), match.end(), specificity="distinctive", requires_orientation=True))
    for name in proper_toponyms:
        for match in re.finditer(re.escape(name), text, re.IGNORECASE):
            claims.append(_claim(source_sha, "visible_text", {"text": match.group(0)}, text, match.start(), match.end(), specificity="distinctive", requires_ocr=True))
    unique = {row["claim_id"]: row for row in claims}
    ordered = sorted(unique.values(), key=lambda row: (row["evidence"]["span"]["start"], row["evidence"]["span"]["end"], row["kind"], row["claim_id"]))
    document = {"schema_version": "1.0", "contract_version": "visual-atomic-claims-v1", "source_text": text, "source_text_sha256": source_sha, "claims": ordered, "extractor": {"kind": "deterministic_rules", "version": "visual-atomic-rules-v1"}}
    validate_atomic_claims(document)
    return document


def validate_atomic_claims(document: Mapping[str, Any]) -> None:
    if document.get("contract_version") != "visual-atomic-claims-v1" or hashlib.sha256(document.get("source_text", "").encode()).hexdigest() != document.get("source_text_sha256"):
        raise VisualRerankingError("contrato o hash textual inválido")
    seen = set()
    for row in document.get("claims", []):
        expected = {"claim_id", "source_text_sha256", "kind", "value", "evidence", "specificity", "requires_ocr", "requires_orientation"}
        if set(row) != expected or row["claim_id"] in seen or row["specificity"] not in {"generic", "distinctive"}:
            raise VisualRerankingError("claim inválido o duplicado")
        seen.add(row["claim_id"])
        span = row["evidence"]["span"]
        if document["source_text"][span["start"]:span["end"]] != row["evidence"]["text"] or row["source_text_sha256"] != document["source_text_sha256"]:
            raise VisualRerankingError("evidencia literal inválida")
        payload = {key: row[key] for key in row if key != "claim_id"}
        if row["claim_id"] != _claim_id(payload):
            raise VisualRerankingError("claim_id no corresponde al contenido")


def atomic_verification_prompt(claim: Mapping[str, Any], *, candidate_id: str, image_id: str, orientation_comparable: bool = False) -> str:
    """Prompt pequeño: una afirmación, una imagen y una decisión cerrada."""
    return (
        "Verifica UNA afirmación usando solo esta fotografía. No adivines lugares, "
        "comercios ni texto. Ausencia, fuera de campo, oclusión, distancia o duda "
        "implican unverifiable, nunca contradicted. contradicted exige una evidencia "
        "visible incompatible. supported exige evidencia visible específica. Para "
        "visible_text, supported exige copiar el rótulo legible en ocr_text. La "
        f"orientación comparable ha sido fijada externamente a {str(orientation_comparable).lower()}; "
        "no la cambies. Devuelve solo un JSON compacto, sin Markdown, con exactamente "
        "claim_id,candidate_id,image_id,verdict,observed_evidence,ocr_text,"
        "orientation_comparable,limitations. verdict: supported|contradicted|unverifiable. "
        "observed_evidence: una frase breve o null. limitations: máximo cuatro valores "
        "de none|partial_view|out_of_frame|occluded|too_far|low_resolution|unreadable_text|"
        "orientation_not_comparable|generation_failed.\n"
        f"claim_id: {claim['claim_id']}\ncandidate_id: {candidate_id}\nimage_id: {image_id}\n"
        f"tipo: {claim['kind']}\nafirmación: {json.dumps(claim['value'], ensure_ascii=False)}\n"
        f"texto fuente literal: {json.dumps(claim['evidence']['text'], ensure_ascii=False)}"
    )


def compact_atomic_verification_prompt(claim: Mapping[str, Any], *, orientation_comparable: bool = False) -> str:
    """Variante compacta: los IDs conocidos se añaden fuera del modelo."""
    return (
        "Verifica UNA afirmación usando solo esta fotografía. No adivines. La ausencia, "
        "duda, oclusión o fuera de campo es unverifiable, nunca contradicted. "
        "contradicted exige una incompatibilidad visible. supported exige evidencia "
        "visible específica. Devuelve SOLO una línea JSON compacta, sin Markdown, con "
        "exactamente estos campos: verdict,observed_evidence,ocr_text,limitations. "
        "verdict es supported|contradicted|unverifiable. observed_evidence es una frase "
        "de máximo 120 caracteres o null. ocr_text es texto literalmente legible o null. "
        "limitations contiene máximo dos valores de none|partial_view|out_of_frame|"
        "occluded|too_far|low_resolution|unreadable_text|orientation_not_comparable. "
        f"La orientación comparable está fijada externamente a {str(orientation_comparable).lower()}. "
        f"Tipo: {claim['kind']}. Afirmación: {json.dumps(claim['value'], ensure_ascii=False)}. "
        f"Texto fuente: {json.dumps(claim['evidence']['text'], ensure_ascii=False)}."
    )


def parse_compact_atomic_verdict(raw: str, claim: Mapping[str, Any], *, candidate_id: str, image_id: str, orientation_comparable_allowed: bool = False) -> dict[str, Any]:
    if raw != raw.strip() or raw.startswith("```") or len(raw) > 700:
        raise VisualRerankingError("salida compacta no es JSON estricto o excede tamaño")
    try:
        compact = json.loads(raw)
    except json.JSONDecodeError as error:
        raise VisualRerankingError("salida compacta no es JSON") from error
    expected = {"verdict", "observed_evidence", "ocr_text", "limitations"}
    if not isinstance(compact, dict) or set(compact) != expected:
        raise VisualRerankingError("campos de salida compacta incompatibles")
    if isinstance(compact.get("observed_evidence"), str) and len(compact["observed_evidence"]) > 120:
        raise VisualRerankingError("evidencia compacta demasiado larga")
    if not isinstance(compact.get("limitations"), list) or len(compact["limitations"]) > 2:
        raise VisualRerankingError("limitaciones compactas inválidas")
    envelope = {
        "claim_id": claim["claim_id"],
        "candidate_id": candidate_id,
        "image_id": image_id,
        "verdict": compact.get("verdict"),
        "observed_evidence": compact.get("observed_evidence"),
        "ocr_text": compact.get("ocr_text"),
        "orientation_comparable": orientation_comparable_allowed,
        "limitations": compact.get("limitations"),
    }
    return parse_atomic_verdict(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")), claim, candidate_id=candidate_id, image_id=image_id, orientation_comparable_allowed=orientation_comparable_allowed)


def parse_atomic_verdict(raw: str, claim: Mapping[str, Any], *, candidate_id: str, image_id: str, orientation_comparable_allowed: bool = False) -> dict[str, Any]:
    """Parseo estricto: no acepta fences, substring JSON ni reparación."""
    if raw != raw.strip() or raw.startswith("```") or len(raw) > 1200:
        raise VisualRerankingError("salida no es JSON estricto o excede tamaño")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise VisualRerankingError("salida atómica no es JSON") from error
    expected = {"claim_id", "candidate_id", "image_id", "verdict", "observed_evidence", "ocr_text", "orientation_comparable", "limitations"}
    if not isinstance(value, dict) or set(value) != expected or value["claim_id"] != claim["claim_id"] or value["candidate_id"] != candidate_id or value["image_id"] != image_id:
        raise VisualRerankingError("IDs o campos de veredicto incompatibles")
    if value["verdict"] not in VERDICTS or not isinstance(value["orientation_comparable"], bool) or not isinstance(value["limitations"], list) or len(value["limitations"]) > 4 or len(value["limitations"]) != len(set(value["limitations"])) or not set(value["limitations"]) <= LIMITATIONS or ("none" in value["limitations"] and len(value["limitations"]) != 1):
        raise VisualRerankingError("veredicto o limitaciones inválidos")
    if value["ocr_text"] is not None and (not isinstance(value["ocr_text"], str) or not value["ocr_text"].strip() or len(value["ocr_text"]) > 160):
        raise VisualRerankingError("ocr_text inválido")
    evidence = value["observed_evidence"]
    if evidence is not None and (not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 240):
        raise VisualRerankingError("evidencia observada inválida")
    if value["verdict"] in {"supported", "contradicted"} and evidence is None:
        raise VisualRerankingError("support/contradiction requiere evidencia visible")
    if value["orientation_comparable"] != orientation_comparable_allowed:
        raise VisualRerankingError("el VLM alteró la comparabilidad de orientación fijada externamente")
    if value["verdict"] == "contradicted" and set(value["limitations"]) & {"partial_view", "out_of_frame", "occluded", "too_far", "low_resolution"}:
        raise VisualRerankingError("contradicción basada en visibilidad insuficiente")
    if claim["requires_orientation"] and not value["orientation_comparable"] and value["verdict"] != "unverifiable":
        raise VisualRerankingError("relación egocéntrica sin orientación comparable debe abstenerse")
    if claim["requires_ocr"] and value["verdict"] == "supported":
        required = str(claim["value"]["text"]).casefold()
        if not isinstance(value["ocr_text"], str) or required not in value["ocr_text"].casefold():
            raise VisualRerankingError("texto visible sin OCR literal suficiente")
    return value


def atomic_annotation_template(claim_sets: Sequence[Mapping[str, Any]], associations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    claims_by_query = {row["query_id"]: row["claims"] for row in claim_sets}
    records = []
    for association in associations:
        query_id = association["query_id"]
        for claim in claims_by_query.get(query_id, []):
            records.append({"query_id": query_id, "candidate_id": association["candidate_id"], "image_id": association["image_id"], "claim_id": claim["claim_id"], "human_verdict": None, "observed_evidence": None, "reason": None, "review_status": "pending", "reviewer": None, "reviewed_at_utc": None})
    return {"schema_version": "1.0", "contract_version": "visual-atomic-human-annotations-v1", "records": records, "instructions": {"absence_is_unverifiable": True, "orientation_must_be_externally_comparable": True, "one_record_per_claim_image": True}}


def aggregate_candidate_evidence(claims: Sequence[Mapping[str, Any]], associations: Sequence[Mapping[str, Any]], verdicts: Sequence[Mapping[str, Any]], *, candidate_ids: Sequence[str] | None = None) -> dict[str, Any]:
    claim_by = {row["claim_id"]: row for row in claims}
    association_by = {(row["candidate_id"], row["image_id"]): row for row in associations}
    candidates = list(candidate_ids) if candidate_ids is not None else sorted({row["candidate_id"] for row in associations})
    if len(candidates) != len(set(candidates)):
        raise VisualRerankingError("candidate_ids agregados duplicados")
    output = []
    for candidate_id in candidates:
        rows = [row for row in verdicts if row.get("candidate_id") == candidate_id and row.get("status") == "valid"]
        per_claim = []
        positive = negative = 0.0
        for claim_id, claim in claim_by.items():
            claim_rows = [row for row in rows if row.get("claim_id") == claim_id]
            sequences = {}
            for row in claim_rows:
                association = association_by.get((candidate_id, row["image_id"]))
                if association is None:
                    raise VisualRerankingError("veredicto sin asociación candidato-imagen")
                key = association.get("sequence_id") or f"image:{row['image_id']}"
                sequences.setdefault(key, []).append(row)
            sequence_rows = []
            for key, items in sequences.items():
                verdict_set = {row["verdict"] for row in items}
                state = "conflict" if {"supported", "contradicted"} <= verdict_set else "supported" if "supported" in verdict_set else "contradicted" if "contradicted" in verdict_set else "unverifiable"
                sequence_rows.append((key, state, items))
            supported = [row for _, state, items in sequence_rows if state == "supported" for row in items if row["verdict"] == "supported"]
            contradicted = [row for _, state, items in sequence_rows if state == "contradicted" for row in items if row["verdict"] == "contradicted"]
            weight = 0.5 if claim["specificity"] == "generic" else 1.0
            state = "conflict" if supported and contradicted else "supported" if supported else "contradicted" if contradicted else "unverifiable"
            if state == "supported": positive += weight
            if state == "contradicted": negative += weight
            per_claim.append({"claim_id": claim_id, "state": state, "weight": weight, "supporting_image_ids": [row["image_id"] for row in supported], "contradicting_image_ids": [row["image_id"] for row in contradicted], "independent_sequences": len(sequences), "conflicting_sequences": sum(sequence_state == "conflict" for _, sequence_state, _ in sequence_rows)})
        total_weight = sum(0.5 if row["specificity"] == "generic" else 1.0 for row in claims) or 1.0
        output.append({"candidate_id": candidate_id, "positive_evidence": positive / total_weight, "negative_evidence": negative / total_weight, "claims": per_claim, "valid_verdicts": len(rows), "coverage_status": "available" if any(row["candidate_id"] == candidate_id for row in associations) else "no_coverage", "failed_or_missing_verdicts_are_neutral": True})
    return {"schema_version": "1.0", "contract_version": "visual-candidate-aggregate-v1", "candidates": output, "policy": {"sequence_deduplication": True, "generic_weight": 0.5, "distinctive_weight": 1.0, "conflict_is_neutral": True, "unverifiable_is_neutral": True}}


def rerank_experimental(baseline: Mapping[str, Any], aggregate: Mapping[str, Any], *, enabled: bool = False, lambda_pos: float = 0.0, lambda_neg: float = 0.0) -> dict[str, Any]:
    reject_ground_truth(baseline, path="baseline")
    reject_ground_truth(aggregate, path="aggregate")
    results = baseline.get("results", [])
    if not results or any(not math.isfinite(float(row["cosine_similarity"])) for row in results):
        raise VisualRerankingError("baseline vacío o con scores inválidos")
    if lambda_pos < 0 or lambda_neg < 0 or not all(math.isfinite(value) for value in (lambda_pos, lambda_neg)):
        raise VisualRerankingError("lambdas deben ser finitos y no negativos")
    evidence = {row["candidate_id"]: row for row in aggregate.get("candidates", [])}
    scores = [float(row["cosine_similarity"]) for row in results]
    low, high = min(scores), max(scores)
    rows = []
    for row in results:
        normalized = 0.5 if high == low else (float(row["cosine_similarity"]) - low) / (high - low)
        visual = evidence.get(row["candidate_id"], {"positive_evidence": 0.0, "negative_evidence": 0.0})
        modifier = lambda_pos * visual["positive_evidence"] - lambda_neg * visual["negative_evidence"] if enabled else 0.0
        rows.append({"candidate_id": row["candidate_id"], "baseline_rank": row["rank"], "baseline_cosine_similarity": row["cosine_similarity"], "baseline_normalized": normalized, "positive_evidence": visual["positive_evidence"], "negative_evidence": visual["negative_evidence"], "visual_modifier": modifier, "experimental_score": normalized + modifier})
    ordered = sorted(rows, key=lambda row: (-row["experimental_score"], row["baseline_rank"], row["candidate_id"]))
    for rank, row in enumerate(ordered, 1): row["experimental_rank"] = rank
    return {"schema_version": "1.0", "contract_version": "visual-experimental-reranking-v1", "enabled": enabled, "ranking_method": "minmax_baseline_plus_visual_evidence", "parameters": {"lambda_pos": lambda_pos, "lambda_neg": lambda_neg}, "baseline_immutable": True, "results": ordered, "limitations": ["scores_are_not_probabilities", "weights_require_development_calibration", "top_k_set_is_unchanged"]}


def evaluate_topk_transition(baseline: Sequence[Mapping[str, Any]], experimental: Sequence[Mapping[str, Any]], *, reference_latitude: float, reference_longitude: float) -> dict[str, Any]:
    base_ids = [row["candidate_id"] for row in baseline]
    exp_ids = [row["candidate_id"] for row in experimental]
    if len(base_ids) != len(exp_ids) or len(set(base_ids)) != len(base_ids) or set(base_ids) != set(exp_ids):
        raise VisualRerankingError("el conjunto Top-K cambió")
    coords = {row["candidate_id"]: (row["latitude"], row["longitude"]) for row in baseline}
    def metrics(ids):
        distances = [haversine_m(reference_latitude, reference_longitude, *coords[candidate_id]) for candidate_id in ids]
        nearest = min(range(len(ids)), key=lambda index: distances[index])
        return {"top1_candidate_id": ids[0], "top1_distance_m": distances[0], "geo1_50": distances[0] <= 50, "geo1_100": distances[0] <= 100, "minimum_top10_distance_m": distances[nearest], "nearest_candidate_id": ids[nearest], "nearest_rank": nearest + 1, "geo10_50": distances[nearest] <= 50, "geo10_100": distances[nearest] <= 100}
    base, reranked = metrics(base_ids), metrics(exp_ids)
    delta = reranked["top1_distance_m"] - base["top1_distance_m"]
    return {"baseline": base, "experimental": reranked, "transition": {"top1_distance_delta_m": delta, "top1": "improved" if delta < 0 else "regressed" if delta > 0 else "tied", "geo10_50_invariant": base["geo10_50"] == reranked["geo10_50"], "geo10_100_invariant": base["geo10_100"] == reranked["geo10_100"], "top10_set_invariant": True, "unrecoverable_by_reranking_50m": not base["geo10_50"]}}


def plan_multiview_associations(candidates: Sequence[Mapping[str, Any]], images: Sequence[Mapping[str, Any]], *, max_distance_m: float = 100.0, max_images_per_candidate: int = 3) -> dict[str, Any]:
    reject_ground_truth(candidates, path="candidates")
    reject_ground_truth(images, path="images")
    if not 0 < max_distance_m <= 200 or not 1 <= max_images_per_candidate <= 5:
        raise VisualRerankingError("política multivista fuera de rango")
    associations = []
    for candidate in candidates:
        nearby = []
        for image in images:
            distance = haversine_m(candidate["latitude"], candidate["longitude"], image["latitude"], image["longitude"])
            if distance > max_distance_m: continue
            bearing = bearing_degrees(image["latitude"], image["longitude"], candidate["latitude"], candidate["longitude"])
            difference = angular_difference(image["orientation_degrees"], bearing) if image.get("orientation_degrees") is not None else None
            panoramic = image.get("camera_type") in {"equirectangular", "spherical", "cylindrical"}
            orientation_band = 0 if panoramic else 1 if difference is not None and difference <= 45 else 2 if difference is not None and difference <= 90 else 3
            nearby.append({"candidate_id": candidate["candidate_id"], "image_id": image["image_id"], "distance_to_candidate_m": distance, "bearing_to_candidate_degrees": bearing, "angular_difference_degrees": difference, "sequence_id": image.get("sequence_id"), "camera_type": image.get("camera_type"), "quality_score": image.get("quality_score"), "orientation_band": orientation_band})
        nearby.sort(key=lambda row: (row["orientation_band"], row["distance_to_candidate_m"], -(row["quality_score"] or -1), row["image_id"]))
        chosen, sequences = [], set()
        for strict in (True, False):
            for row in nearby:
                if row in chosen or (strict and row["sequence_id"] in sequences and row["sequence_id"] is not None): continue
                chosen.append(row); sequences.add(row["sequence_id"])
                if len(chosen) == max_images_per_candidate: break
            if len(chosen) == max_images_per_candidate: break
        associations.extend(chosen)
    assets = sorted({row["image_id"] for row in associations})
    covered = {row["candidate_id"] for row in associations}
    policy_version = "mapillary-multiview-selection-v2" if max_images_per_candidate == 5 else "mapillary-multiview-selection-v1"
    return {"schema_version": "1.0", "contract_version": "mapillary-multiview-plan-v1", "policy": {"version": policy_version, "max_distance_m": max_distance_m, "max_images_per_candidate": max_images_per_candidate, "ground_truth_used": False, "perspective_orientation_priority_degrees": [45, 90], "panoramic_orientation_priority": True, "sequence_diversity_first": True}, "candidate_count": len(candidates), "covered_candidate_count": len(covered), "uncovered_candidate_ids": sorted({row["candidate_id"] for row in candidates} - covered), "association_count": len(associations), "unique_asset_count": len(assets), "asset_image_ids": assets, "associations": associations}
