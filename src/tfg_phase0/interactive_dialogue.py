"""MVP de un turno para recuperación geográfica interactiva sin ground truth."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Mapping, Protocol, Sequence

from .crs import wgs84_to_epsg25830
from .f5_text_transform import GenerationConfig, QwenTransformersAdapter


CONTRACT_VERSION = "interactive-dialogue-session-v1"
POLICY_VERSION = "deterministic-positive-f3-question-v1"
QWEN_MODEL_ID = "Qwen/Qwen3-8B"
QWEN_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
QWEN_ARTIFACT_MANIFEST_SHA256 = "d95b2ee5a666c88adcb53094740c1002718f28e0dcabad56a508a9c66dce1570"
EVIDENCE_STATES = {"supported", "contradicted", "unknown", "unobservable", "low_confidence"}
UNINFORMATIVE_ANSWERS = {
    "no se", "no sé", "no lo se", "no lo sé", "no puedo comprobarlo",
    "no puedo verlo", "no lo puedo ver", "desconocido",
}
QUESTION_LABELS = {
    "square": "una plaza o espacio peatonal amplio",
    "church": "una iglesia o lugar de culto",
    "monument": "un monumento o elemento histórico",
    "intersection": "una intersección de varias calles",
    "park": "un parque o jardín",
    "commercial": "un comercio o equipamiento identificable",
}
FEATURE_TERMS = {
    "square": {"plaza", "plazoleta"},
    "church": {"iglesia", "templo", "parroquia", "culto"},
    "monument": {"monumento", "estatua", "memorial"},
    "intersection": {"interseccion", "intersección", "cruce", "esquina"},
    "park": {"parque", "jardin", "jardín"},
    "commercial": {"comercio", "tienda", "restaurante", "farmacia", "banco"},
}
SPECIFICITY = {"monument": 6, "church": 5, "square": 4, "intersection": 3, "park": 2, "commercial": 1}


class InteractiveDialogueError(ValueError):
    """El estado o una salida de componente no cumple el contrato del MVP."""


class DialogueStateError(InteractiveDialogueError):
    """La transición solicitada no está permitida."""


class Retriever(Protocol):
    gallery_id: str

    @property
    def metadata(self) -> Mapping[str, Any]: ...

    def retrieve_full(self, *, query_id: str, text: str, language: str) -> dict[str, Any]: ...


class TextDialogueAdapter(Protocol):
    @property
    def metadata(self) -> Mapping[str, Any]: ...

    def redact_question(self, intent: "QuestionIntent") -> str: ...
    def rewrite_query(self, original: str, clarification: str) -> str: ...


@dataclass(frozen=True)
class DialoguePolicyConfig:
    reserve_size: int = 20
    cluster_radius_m: float = 75.0
    minimum_hypotheses: int = 2
    minimum_supported_hypotheses: int = 1
    maximum_supported_fraction: float = 0.75
    allow_qwen_question: bool = True
    enable_controlled_rewrite: bool = True

    def __post_init__(self) -> None:
        if self.reserve_size < 2 or self.cluster_radius_m <= 0 or self.minimum_hypotheses < 2:
            raise InteractiveDialogueError("configuración de diálogo fuera de rango")
        if self.minimum_supported_hypotheses < 1 or not 0 < self.maximum_supported_fraction < 1:
            raise InteractiveDialogueError("umbrales de pregunta fuera de rango")


@dataclass(frozen=True)
class CandidateFeature:
    feature: str
    label: str
    source_refs: tuple[str, ...]
    ambiguous: bool


@dataclass(frozen=True)
class SpatialHypothesis:
    hypothesis_id: str
    candidate_ids: tuple[str, ...]
    best_rank: int
    centroid_easting_m: float
    centroid_northing_m: float
    features: tuple[CandidateFeature, ...]


@dataclass(frozen=True)
class QuestionIntent:
    intent_id: str
    feature: str
    label: str
    supported_hypothesis_ids: tuple[str, ...]
    unknown_hypothesis_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    deterministic_question: str
    utility: tuple[float, ...]


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise InteractiveDialogueError("documento interactivo no serializable") from error
    return (text + ("\n" if newline else "")).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-záéíóúüñ0-9]+", text.casefold()))


def _normalized_answer(text: str) -> str:
    return " ".join(text.casefold().strip().rstrip(".!?").split())


def is_uninformative_answer(text: str) -> bool:
    normalized = _normalized_answer(text)
    return (
        not normalized
        or normalized in UNINFORMATIVE_ANSWERS
        or normalized.startswith(("no puedo comprobarlo", "no puedo verlo", "no estoy seguro", "no estoy segura", "no se distingue", "no sé si", "no se si"))
    )


class ResidentCT2LAdapter:
    """Frontera mínima sobre el runtime residente; siempre recupera la galería completa."""

    def __init__(self, runtime: Any, gallery_id: str):
        self.runtime = runtime
        self.gallery_id = gallery_id
        try:
            gallery = runtime._galleries[gallery_id]
            encoder = runtime._encoder
            self._identity = {
                "expected_gallery_count": len(gallery.candidate_ids),
                "candidate_universe_sha256": _sha256(sorted(gallery.candidate_ids)),
                "catalog_manifest_id": gallery.catalog.manifest_id,
                "catalog_manifest_sha256": gallery.catalog.sha256,
                "embedding_dataset_id": gallery.embedding_manifest["embedding_dataset_id"],
                "checkpoint_sha256": encoder.checkpoint_sha256,
                "model_name": encoder.model_name,
                "cvg_utils_sha256": gallery.embedding_manifest["model"]["cvg_utils_sha256"],
            }
        except (AttributeError, KeyError) as error:
            raise InteractiveDialogueError("runtime CT2L no expone identidad reproducible") from error
        self._calls: list[dict[str, Any]] = []

    @property
    def metadata(self) -> Mapping[str, Any]:
        return {
            "adapter": "resident-crosstext2loc-v1",
            "ranking_method": "exhaustive_cosine",
            "tie_break": "candidate_id_ascending",
            "text_context_tokens": 300,
            "truncate": True,
            "truncation_side": "right",
            **self._identity,
            "calls": list(self._calls),
        }

    def count_tokens(self, text: str) -> int | None:
        tokenizer = getattr(getattr(self.runtime._encoder, "_clip", None), "_tokenizer", None)
        return len(tokenizer.encode(text)) + 2 if tokenizer is not None else None

    def truncate_to_tokens(self, text: str, maximum: int) -> str:
        tokenizer = getattr(getattr(self.runtime._encoder, "_clip", None), "_tokenizer", None)
        if tokenizer is None or not hasattr(tokenizer, "decode"):
            raise InteractiveDialogueError("tokenizer CT2L no permite truncamiento explícito")
        return tokenizer.decode(tokenizer.encode(text)[:max(0, maximum - 2)]).strip()

    def retrieve_full(self, *, query_id: str, text: str, language: str) -> dict[str, Any]:
        count = self.runtime.gallery_count(self.gallery_id)
        tokenizer = getattr(getattr(self.runtime, "_encoder", None), "_clip", None)
        tokenizer = getattr(tokenizer, "_tokenizer", None)
        token_count = len(tokenizer.encode(text)) + 2 if tokenizer is not None else None
        started = time.perf_counter()
        response = self.runtime.retrieve(
            gallery_id=self.gallery_id,
            query_id=query_id,
            text=text,
            language=language,
            k=count,
        )
        if response["gallery_count"] != count or response["effective_k"] != count:
            raise InteractiveDialogueError("CT2L no devolvió un ranking exhaustivo")
        self._calls.append({
            "query_id": query_id,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "text_characters": len(text),
            "pre_truncation_token_count": token_count,
            "truncated": token_count is not None and token_count > 300,
        })
        return response


class QwenDialogueAdapter:
    """Reutiliza una única instancia textual Qwen con prompts separados y cerrados."""

    def __init__(self, runtime: QwenTransformersAdapter):
        metadata = runtime.metadata
        if (
            metadata.model_id != QWEN_MODEL_ID
            or metadata.revision != QWEN_REVISION
            or metadata.artifact_manifest_sha256 != QWEN_ARTIFACT_MANIFEST_SHA256
            or metadata.real_model_inference is not True
        ):
            raise InteractiveDialogueError("identidad Qwen incompatible con el MVP")
        self.runtime = runtime
        self._calls: list[dict[str, Any]] = []

    @property
    def metadata(self) -> Mapping[str, Any]:
        value = self.runtime.metadata
        resource_usage = dict(self.runtime.resource_usage)
        return {
            "adapter": value.adapter,
            "model_id": value.model_id,
            "revision": value.revision,
            "artifact_manifest_sha256": value.artifact_manifest_sha256,
            "real_model_inference": value.real_model_inference,
            "resource_usage": resource_usage,
            "calls": list(self._calls),
        }

    def _generate(self, *, task: str, prompt: str, max_new_tokens: int) -> str:
        tokenizer = self.runtime._tokenizer
        messages = [{"role": "user", "content": prompt}]
        try:
            rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        input_tokens = len(tokenizer(rendered)["input_ids"])
        generation = GenerationConfig(max_new_tokens=max_new_tokens)
        result = self.runtime.generate_prompt(prompt, generation)
        self._calls.append({
            "task": task,
            "task_prompt": prompt,
            "prompt_effective": rendered,
            "raw_output": result.raw_output,
            "duration_ms": result.duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": len(tokenizer(result.raw_output)["input_ids"]),
            "max_new_tokens": max_new_tokens,
            "do_sample": False,
            "enable_thinking": False,
            "seed": generation.seed,
        })
        return result.text

    def redact_question(self, intent: QuestionIntent) -> str:
        prompt = (
            "Redacta una sola pregunta neutral en español sobre la intención indicada. "
            "No añadas nombres propios, lugares, atributos, direcciones ni hechos. "
            "No afirmes que el elemento existe o debería verse. Incluye literalmente las "
            "opciones 'sí', 'no' y 'no puedo comprobarlo'. Devuelve solo la pregunta.\n"
            f"Intención autorizada: preguntar si la persona puede ver {intent.label}."
        )
        return self._generate(task="redact_question", prompt=prompt, max_new_tokens=96)

    def rewrite_query(self, original: str, clarification: str) -> str:
        prompt = (
            "Reescribe en español esta descripción para recuperación cartográfica. "
            "Conserva toda la información original e incorpora solo la aclaración humana. "
            "No añadas nombres propios, lugares, entidades, números, orientación ni certeza. "
            "No incluyas la pregunta del sistema. Devuelve solo la descripción.\n"
            f"Descripción original: {json.dumps(original, ensure_ascii=False)}\n"
            f"Aclaración validada: {json.dumps(clarification, ensure_ascii=False)}"
        )
        return self._generate(task="rewrite_query", prompt=prompt, max_new_tokens=256)


class FakeTextDialogueAdapter:
    """Doble CPU explícito; nunca representa inferencia Qwen real."""

    def __init__(self, *, question: str | None = None, rewrite: str | None = None, fail: bool = False):
        self.question = question
        self.rewrite = rewrite
        self.fail = fail

    @property
    def metadata(self) -> Mapping[str, Any]:
        return {"adapter": "fake-dialogue-v1", "model_id": "fake/qwen3-8b", "revision": "test", "artifact_manifest_sha256": "0" * 64, "real_model_inference": False}

    def redact_question(self, intent: QuestionIntent) -> str:
        if self.fail:
            raise RuntimeError("fake question failure")
        return self.question if self.question is not None else intent.deterministic_question

    def rewrite_query(self, original: str, clarification: str) -> str:
        if self.fail:
            raise RuntimeError("fake rewrite failure")
        return self.rewrite if self.rewrite is not None else literal_query(original, clarification)


class F3EvidenceIndex:
    """Índice read-only de evidencia cartográfica positiva por candidato."""

    def __init__(self, *, dataset_id: str, features_by_candidate: Mapping[str, Sequence[CandidateFeature]], source_hashes: Mapping[str, str], catalog_manifest_id: str | None = None, catalog_manifest_sha256: str | None = None):
        self.dataset_id = dataset_id
        self.features_by_candidate = {key: tuple(value) for key, value in features_by_candidate.items()}
        self.source_hashes = dict(source_hashes)
        self.catalog_manifest_id = catalog_manifest_id
        self.catalog_manifest_sha256 = catalog_manifest_sha256

    @classmethod
    def from_documents(
        cls,
        *,
        dataset_id: str,
        objects: Sequence[Mapping[str, Any]],
        associations: Sequence[Mapping[str, Any]],
        source_hashes: Mapping[str, str] | None = None,
        catalog_manifest_id: str | None = None,
        catalog_manifest_sha256: str | None = None,
    ) -> "F3EvidenceIndex":
        object_by_ref = {row["osm_ref"]: row for row in objects}
        raw_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
        street_refs: dict[str, set[str]] = defaultdict(set)
        for association in associations:
            candidate_id = association["candidate_id"]
            obj = object_by_ref.get(association["osm_ref"])
            if obj is None or obj.get("geometry_status") != "valid":
                continue
            if association.get("boundary_contact_only"):
                continue
            semantic_type = _classify_object(obj)
            if semantic_type is None or _association_relation(association) is None:
                continue
            if semantic_type == "street":
                street_refs[candidate_id].add(obj["osm_ref"])
                continue
            if semantic_type not in QUESTION_LABELS:
                continue
            raw_by_candidate[candidate_id].append({"feature": semantic_type, "osm_ref": obj["osm_ref"]})
        for candidate_id, refs in street_refs.items():
            if len(refs) >= 2:
                raw_by_candidate[candidate_id].append({"feature": "intersection", "osm_ref": "+".join(sorted(refs))})
        features: dict[str, tuple[CandidateFeature, ...]] = {}
        for candidate_id, rows in raw_by_candidate.items():
            grouped: dict[str, set[str]] = defaultdict(set)
            for row in rows:
                grouped[row["feature"]].add(row["osm_ref"])
            features[candidate_id] = tuple(
                CandidateFeature(feature=feature, label=QUESTION_LABELS[feature], source_refs=tuple(sorted(refs)), ambiguous=len(refs) > 4)
                for feature, refs in sorted(grouped.items())
            )
        return cls(dataset_id=dataset_id, features_by_candidate=features, source_hashes=source_hashes or {}, catalog_manifest_id=catalog_manifest_id, catalog_manifest_sha256=catalog_manifest_sha256)

    @classmethod
    def load_bundle(cls, path: Path) -> "F3EvidenceIndex":
        required = ("provenance.json", "osm_objects.jsonl", "candidate_osm_associations.jsonl", "relation_context.jsonl", "sha256.txt")
        if any(not (path / name).is_file() for name in required):
            raise InteractiveDialogueError("bundle F3 incompleto")
        provenance = json.loads((path / "provenance.json").read_text(encoding="utf-8"))
        if provenance.get("contract_version") != "f3-associations-v1" or provenance.get("schema_version") != "1.0":
            raise InteractiveDialogueError("provenance F3 incompatible")
        checksums = {}
        for line in (path / "sha256.txt").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 2:
                raise InteractiveDialogueError("manifest de checksums F3 inválido")
            checksums[parts[1].lstrip("*")] = parts[0]
        for name in ("provenance.json", "osm_objects.jsonl", "candidate_osm_associations.jsonl", "relation_context.jsonl"):
            if checksums.get(name) != _sha256_file(path / name):
                raise InteractiveDialogueError(f"checksum F3 incorrecto: {name}")
        objects = _read_jsonl(path / "osm_objects.jsonl")
        associations = _read_jsonl(path / "candidate_osm_associations.jsonl")
        hashes = {name: _sha256_file(path / name) for name in required}
        return cls.from_documents(
            dataset_id=provenance["f3_dataset_id"],
            objects=objects,
            associations=associations,
            source_hashes=hashes,
            catalog_manifest_id=provenance["inputs"]["catalog"]["manifest_id"],
            catalog_manifest_sha256=provenance["inputs"]["catalog"]["sha256"],
        )

    def features(self, candidate_id: str) -> tuple[CandidateFeature, ...]:
        return self.features_by_candidate.get(candidate_id, ())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise InteractiveDialogueError(f"JSONL F3 inválido: {path.name}") from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _classify_object(obj: Mapping[str, Any]) -> str | None:
    tags = obj["tags"]
    if tags.get("place") == "square" or tags.get("highway") == "pedestrian" and "plaza" in tags.get("name", "").casefold():
        return "square"
    if tags.get("leisure") in {"park", "garden"}:
        return "park"
    if tags.get("amenity") == "place_of_worship":
        return "church"
    if tags.get("historic") in {"monument", "memorial"} or tags.get("tourism") == "artwork":
        return "monument"
    if obj["geometry_role"] == "line" and tags.get("highway") in {"residential", "tertiary", "pedestrian", "living_street", "footway", "service"}:
        return "street"
    if "shop" in tags or tags.get("amenity") in {"restaurant", "cafe", "bar", "pub", "school", "college", "library", "theatre", "marketplace", "pharmacy", "bank"}:
        return "commercial"
    return None


def _association_relation(row: Mapping[str, Any]) -> str | None:
    for field in ("touches", "contains", "within", "crosses", "overlaps", "intersects"):
        if row.get(field):
            return field
    return None


def cluster_ranked_candidates(ranking: Mapping[str, Any], evidence: F3EvidenceIndex, *, reserve_size: int, radius_m: float) -> tuple[SpatialHypothesis, ...]:
    rows = ranking["results"][:reserve_size]
    projected = []
    for row in rows:
        easting, northing = wgs84_to_epsg25830(row["latitude"], row["longitude"])
        projected.append((row, easting, northing))
    parent = list(range(len(projected)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(projected)):
        for right in range(left + 1, len(projected)):
            if math.dist(projected[left][1:], projected[right][1:]) <= radius_m:
                a, b = root(left), root(right)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    groups: dict[int, list[tuple[Mapping[str, Any], float, float]]] = defaultdict(list)
    for index, item in enumerate(projected):
        groups[root(index)].append(item)
    hypotheses = []
    ordered_groups = sorted(groups.values(), key=lambda group: min(item[0]["rank"] for item in group))
    for position, group in enumerate(ordered_groups, start=1):
        candidates = tuple(item[0]["candidate_id"] for item in sorted(group, key=lambda item: item[0]["rank"]))
        feature_rows: dict[str, list[CandidateFeature]] = defaultdict(list)
        for candidate_id in candidates:
            for feature in evidence.features(candidate_id):
                feature_rows[feature.feature].append(feature)
        merged = tuple(
            CandidateFeature(
                feature=feature,
                label=rows_for_feature[0].label,
                source_refs=tuple(sorted({ref for row in rows_for_feature for ref in row.source_refs})),
                ambiguous=any(row.ambiguous for row in rows_for_feature),
            )
            for feature, rows_for_feature in sorted(feature_rows.items())
        )
        hypotheses.append(SpatialHypothesis(
            hypothesis_id=f"hypothesis-{position:03d}",
            candidate_ids=candidates,
            best_rank=min(item[0]["rank"] for item in group),
            centroid_easting_m=round(sum(item[1] for item in group) / len(group), 6),
            centroid_northing_m=round(sum(item[2] for item in group) / len(group), 6),
            features=merged,
        ))
    return tuple(hypotheses)


def select_question_intent(description: str, hypotheses: Sequence[SpatialHypothesis], config: DialoguePolicyConfig) -> QuestionIntent | None:
    if len(hypotheses) < config.minimum_hypotheses:
        return None
    description_tokens = _tokens(description)
    by_feature: dict[str, list[SpatialHypothesis]] = defaultdict(list)
    for hypothesis in hypotheses:
        for feature in hypothesis.features:
            if not feature.ambiguous:
                by_feature[feature.feature].append(hypothesis)
    candidates = []
    for feature, supported in by_feature.items():
        if feature not in QUESTION_LABELS or description_tokens & FEATURE_TERMS[feature]:
            continue
        supported_ids = tuple(row.hypothesis_id for row in supported)
        unknown_ids = tuple(row.hypothesis_id for row in hypotheses if row.hypothesis_id not in supported_ids)
        fraction = len(supported_ids) / len(hypotheses)
        if len(supported_ids) < config.minimum_supported_hypotheses or not unknown_ids or fraction > config.maximum_supported_fraction:
            continue
        balance = min(len(supported_ids), len(unknown_ids)) / len(hypotheses)
        rank_weight = sum(1 / row.best_rank for row in supported)
        refs = tuple(sorted({ref for row in supported for value in row.features if value.feature == feature for ref in value.source_refs}))
        utility = (float(SPECIFICITY[feature]), balance, rank_weight, -float(len(refs)))
        candidates.append((utility, feature, supported_ids, unknown_ids, refs))
    if not candidates:
        return None
    utility, feature, supported_ids, unknown_ids, refs = max(candidates, key=lambda row: (row[0], row[1]))
    label = QUESTION_LABELS[feature]
    question = f"Sin cambiar de posición, ¿puedes ver {label}? Responde sí, no o no puedo comprobarlo."
    identity = {"policy": POLICY_VERSION, "feature": feature, "supported": supported_ids, "unknown": unknown_ids, "evidence_refs": refs}
    return QuestionIntent(
        intent_id="question-intent-sha256-" + _sha256(identity),
        feature=feature,
        label=label,
        supported_hypothesis_ids=supported_ids,
        unknown_hypothesis_ids=unknown_ids,
        evidence_refs=refs,
        deterministic_question=question,
        utility=utility,
    )


def validate_question_redaction(text: str, intent: QuestionIntent) -> tuple[bool, str | None]:
    normalized = " ".join(text.strip().split())
    lowered = normalized.casefold()
    if not normalized.endswith("?") and "?" not in normalized:
        return False, "not_a_question"
    if len(normalized) > 240:
        return False, "too_long"
    if intent.label.casefold() not in lowered:
        return False, "intent_changed"
    if any(option not in lowered for option in ("sí", "no", "no puedo comprobarlo")):
        return False, "missing_abstention_option"
    suggestive = ("confirmas", "deberías", "seguramente", "parece que estás", "sabemos que", "cerca de ti hay")
    if any(value in lowered for value in suggestive):
        return False, "suggestive_wording"
    if lowered.startswith("¿no ") or normalized.count("?") != 1 or normalized.count("¿") > 1:
        return False, "leading_or_multiple_question"
    allowed = _tokens(intent.deterministic_question) | _tokens(intent.label) | {"ves", "ver", "observas", "observar", "puedes", "desde", "donde", "estas", "estás", "ahora", "mismo"}
    if _tokens(normalized) - allowed:
        return False, "unauthorized_content"
    return True, None


def clarification_from_answer(answer: str, intent: QuestionIntent) -> str:
    normalized = _normalized_answer(answer)
    if normalized in {"si", "sí"}:
        return f"La persona indica que puede ver {intent.label}."
    if normalized == "no":
        return f"La persona indica que no puede ver {intent.label} desde su posición."
    return answer.strip()


def literal_query(original: str, clarification: str) -> str:
    # CT2L trunca a la derecha a 300 tokens; ante entradas largas se protege primero
    # la información nueva sin dejar de conservar el original en el registro.
    return f"[ACLARACIÓN VALIDADA]\n{clarification.strip()}\n[DESCRIPCIÓN ORIGINAL]\n{original.strip()}"


def validate_controlled_rewrite(original: str, clarification: str, rewritten: str) -> tuple[bool, str | None]:
    value = " ".join(rewritten.strip().split())
    if not value or len(value) > max(2400, int((len(original) + len(clarification)) * 2.5)):
        return False, "invalid_length"
    if original.strip() not in rewritten:
        return False, "original_information_lost"
    if clarification.strip() not in rewritten:
        return False, "clarification_lost"
    without_sources = rewritten.replace(original.strip(), "", 1).replace(clarification.strip(), "", 1)
    if _tokens(without_sources) - {"y", "ademas", "además", "tambien", "también"}:
        return False, "invented_content"
    return True, None


def compare_rankings(initial: Mapping[str, Any], updated: Mapping[str, Any]) -> dict[str, Any]:
    initial_rank = {row["candidate_id"]: row["rank"] for row in initial["results"]}
    updated_rank = {row["candidate_id"]: row["rank"] for row in updated["results"]}
    if set(initial_rank) != set(updated_rank):
        raise InteractiveDialogueError("los rankings no cubren la misma galería")
    top10_initial = tuple(row["candidate_id"] for row in initial["results"][:10])
    top10_updated = tuple(row["candidate_id"] for row in updated["results"][:10])
    entered = tuple(value for value in top10_updated if value not in top10_initial)
    left = tuple(value for value in top10_initial if value not in top10_updated)
    changed = sum(initial_rank[key] != updated_rank[key] for key in initial_rank)
    return {
        "top1_changed": top10_initial[0] != top10_updated[0],
        "top10_entered": list(entered),
        "top10_left": list(left),
        "changed_candidate_count": changed,
        "spearman_footrule": sum(abs(initial_rank[key] - updated_rank[key]) for key in initial_rank),
        "geographic_improvement_evaluated": False,
    }


def _validate_ranking_document(ranking: Mapping[str, Any], gallery_id: str) -> None:
    forbidden = {"ground_truth", "gt", "reference_coordinate", "target_candidate_id"}
    if forbidden & set(ranking):
        raise InteractiveDialogueError("ranking operativo contiene ground truth")
    required = {"gallery_id", "gallery_count", "effective_k", "ranking_method", "tie_break", "results"}
    if not required <= set(ranking) or ranking["gallery_id"] != gallery_id:
        raise InteractiveDialogueError("respuesta CT2L incompatible")
    if ranking["effective_k"] != ranking["gallery_count"] or len(ranking["results"]) != ranking["gallery_count"]:
        raise InteractiveDialogueError("el ranking CT2L no es global")
    if ranking["ranking_method"] != "exhaustive_cosine" or ranking["tie_break"] != "candidate_id_ascending":
        raise InteractiveDialogueError("método CT2L no permitido")
    if [row["rank"] for row in ranking["results"]] != list(range(1, len(ranking["results"]) + 1)):
        raise InteractiveDialogueError("ranks CT2L no consecutivos")
    candidate_ids = [row["candidate_id"] for row in ranking["results"]]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise InteractiveDialogueError("ranking CT2L contiene candidatos duplicados")


class OneTurnDialogueOrchestrator:
    def __init__(self, *, retriever: Retriever, evidence: F3EvidenceIndex, config: DialoguePolicyConfig, text_adapter: TextDialogueAdapter | None = None):
        self.retriever = retriever
        self.evidence = evidence
        self.config = config
        self.text_adapter = text_adapter

    def start(self, *, session_label: str, description: str, language: str = "es") -> dict[str, Any]:
        if not session_label.strip() or not description.strip() or len(language.strip()) < 2:
            raise InteractiveDialogueError("entrada inicial inválida")
        identity = {
            "label": session_label,
            "description": description,
            "language": language,
            "gallery_id": self.retriever.gallery_id,
            "policy": self._policy_document(),
            "f3_dataset_id": self.evidence.dataset_id,
            "retrieval": dict(self.retriever.metadata),
            "text_model": dict(self.text_adapter.metadata) if self.text_adapter is not None else None,
        }
        session_id = "dialogue-session-sha256-" + _sha256(identity)
        ranking = self.retriever.retrieve_full(query_id=f"{session_id}-initial", text=description, language=language)
        self._validate_ranking(ranking)
        hypotheses = cluster_ranked_candidates(ranking, self.evidence, reserve_size=self.config.reserve_size, radius_m=self.config.cluster_radius_m)
        intent = select_question_intent(description, hypotheses, self.config)
        events: list[dict[str, Any]] = []
        self._append_event(events, "session_started", {"description": description, "language": language})
        self._append_event(events, "initial_retrieval_completed", {"query": description, "ranking_sha256": _sha256(ranking), "gallery_count": ranking["gallery_count"]})
        self._append_event(events, "ambiguity_analyzed", {"hypothesis_count": len(hypotheses), "reserve_size": min(self.config.reserve_size, len(ranking["results"])), "cluster_radius_m": self.config.cluster_radius_m})
        question_record = None
        status = "awaiting_answer"
        stop_reason = None
        if intent is None:
            status, stop_reason = "completed", "no_discriminative_question"
            self._append_event(events, "session_stopped", {"reason": stop_reason})
        else:
            question = intent.deterministic_question
            source = "deterministic_template"
            fallback_reason = None
            if self.config.allow_qwen_question and self.text_adapter is not None:
                try:
                    proposed = self.text_adapter.redact_question(intent)
                    valid, reason = validate_question_redaction(proposed, intent)
                    if valid:
                        question, source = " ".join(proposed.strip().split()), "qwen_validated"
                    else:
                        fallback_reason = reason
                except Exception as error:
                    fallback_reason = f"runtime_error:{type(error).__name__}"
            question_record = self._question_document(intent, question, source, fallback_reason)
            self._append_event(events, "question_selected", {"intent_id": intent.intent_id, "question": question, "source": source, "fallback_reason": fallback_reason})
        session = {
            "schema_version": "1.0",
            "contract_version": CONTRACT_VERSION,
            "session_id": session_id,
            "status": status,
            "turn_limit": 1,
            "turns_used": 0,
            "gallery_id": self.retriever.gallery_id,
            "policy": self._policy_document(),
            "models": {"text": dict(self.text_adapter.metadata) if self.text_adapter is not None else None, "retrieval": dict(self.retriever.metadata), "vlm": {"enabled": False, "reason": "out_of_scope"}},
            "inputs": {"description": {"text": description, "language": language, "source": "human_literal", "sha256": hashlib.sha256(description.encode()).hexdigest()}},
            "f3": {"dataset_id": self.evidence.dataset_id, "catalog_manifest_id": self.evidence.catalog_manifest_id, "catalog_manifest_sha256": self.evidence.catalog_manifest_sha256, "source_hashes": self.evidence.source_hashes, "absence_semantics": "unknown_not_contradicted", "visibility_inferred": False},
            "initial_ranking": ranking,
            "hypotheses": [self._hypothesis_document(value) for value in hypotheses],
            "selected_question": question_record,
            "human_answer": None,
            "query_updates": [],
            "updated_rankings": [],
            "comparisons": [],
            "stop_reason": stop_reason,
            "events": events,
            "limitations": ["infrastructure_validation_only", "no_ground_truth_in_operational_contract", "ct2l_scores_not_probabilities", "f3_association_not_visibility", "no_vlm", "one_clarification_turn"],
        }
        validate_session(session)
        return session

    def answer(self, session: Mapping[str, Any], answer: str) -> dict[str, Any]:
        validate_session(session)
        if session["status"] != "awaiting_answer" or session["turns_used"] != 0 or session["selected_question"] is None:
            raise DialogueStateError("la sesión no admite otra respuesta")
        if not answer.strip():
            raise DialogueStateError("la respuesta humana no puede estar vacía")
        result = json.loads(json.dumps(session, ensure_ascii=False))
        result["turns_used"] = 1
        result["human_answer"] = {"text": answer, "source": "human_literal", "sha256": hashlib.sha256(answer.encode()).hexdigest(), "informative": not is_uninformative_answer(answer)}
        self._append_event(result["events"], "human_answer_recorded", {"answer": answer, "answer_sha256": result["human_answer"]["sha256"], "informative": result["human_answer"]["informative"]})
        if not result["human_answer"]["informative"]:
            result["status"] = "completed"
            result["stop_reason"] = "human_could_not_answer"
            self._append_event(result["events"], "session_stopped", {"reason": result["stop_reason"]})
            validate_session(result)
            return result
        original = result["inputs"]["description"]["text"]
        selected = result["selected_question"]
        intent = QuestionIntent(selected["intent_id"], selected["feature"], selected["label"], tuple(selected["supported_hypothesis_ids"]), tuple(selected["unknown_hypothesis_ids"]), tuple(selected["evidence_refs"]), selected["question"], ())
        clarification = clarification_from_answer(answer, intent)
        result["human_answer"]["validated_clarification"] = clarification
        literal = literal_query(original, clarification)
        updates = [{"variant": "literal_concatenation", "text": literal, "status": "accepted", "source": "deterministic", "failure_reason": None}]
        if self.config.enable_controlled_rewrite and self.text_adapter is not None:
            try:
                proposed = self.text_adapter.rewrite_query(original, clarification)
                valid, reason = validate_controlled_rewrite(original, clarification, proposed)
                updates.append({"variant": "controlled_rewrite", "text": proposed if valid else None, "raw_proposal": proposed, "status": "accepted" if valid else "rejected", "source": "qwen_proposal", "failure_reason": reason})
            except Exception as error:
                updates.append({"variant": "controlled_rewrite", "text": None, "raw_proposal": None, "status": "failed", "source": "qwen_proposal", "failure_reason": f"runtime_error:{type(error).__name__}"})
        result["query_updates"] = updates
        for update in updates:
            self._append_event(result["events"], "query_update_validated", {"variant": update["variant"], "status": update["status"], "failure_reason": update["failure_reason"], "text_sha256": hashlib.sha256(update["text"].encode()).hexdigest() if update["text"] is not None else None})
            if update["status"] != "accepted":
                continue
            ranking = self.retriever.retrieve_full(query_id=f"{result['session_id']}-{update['variant']}", text=update["text"], language=result["inputs"]["description"]["language"])
            self._validate_ranking(ranking)
            result["updated_rankings"].append({"variant": update["variant"], "ranking": ranking})
            comparison = {"variant": update["variant"], **compare_rankings(result["initial_ranking"], ranking)}
            result["comparisons"].append(comparison)
            self._append_event(result["events"], "updated_retrieval_completed", {"variant": update["variant"], "query_sha256": hashlib.sha256(update["text"].encode()).hexdigest(), "ranking_sha256": _sha256(ranking)})
        result["status"] = "completed"
        result["stop_reason"] = "turn_limit_reached"
        result["models"]["retrieval"] = dict(self.retriever.metadata)
        if self.text_adapter is not None:
            result["models"]["text"] = dict(self.text_adapter.metadata)
        self._append_event(result["events"], "session_stopped", {"reason": result["stop_reason"]})
        validate_session(result)
        return result

    def _validate_ranking(self, ranking: Mapping[str, Any]) -> None:
        _validate_ranking_document(ranking, self.retriever.gallery_id)

    def _append_event(self, events: list[dict[str, Any]], kind: str, payload: Mapping[str, Any]) -> None:
        previous = events[-1]["event_hash"] if events else None
        preimage = {"sequence": len(events), "kind": kind, "payload": dict(payload), "previous_event_hash": previous, "recorded_at_utc": _utc_now()}
        events.append({**preimage, "event_hash": "dialogue-event-sha256-" + _sha256(preimage)})

    def _policy_document(self) -> dict[str, Any]:
        return {"version": POLICY_VERSION, "reserve_size": self.config.reserve_size, "cluster_radius_m": self.config.cluster_radius_m, "minimum_hypotheses": self.config.minimum_hypotheses, "minimum_supported_hypotheses": self.config.minimum_supported_hypotheses, "maximum_supported_fraction": self.config.maximum_supported_fraction, "allow_qwen_question": self.config.allow_qwen_question, "enable_controlled_rewrite": self.config.enable_controlled_rewrite, "scores_are_probabilities": False}

    @staticmethod
    def _hypothesis_document(value: SpatialHypothesis) -> dict[str, Any]:
        return {"hypothesis_id": value.hypothesis_id, "candidate_ids": list(value.candidate_ids), "best_rank": value.best_rank, "centroid_epsg25830": {"easting_m": value.centroid_easting_m, "northing_m": value.centroid_northing_m}, "features": [{"feature": row.feature, "label": row.label, "state": "supported", "source": "osm_f3_association", "source_refs": list(row.source_refs), "visibility_inferred": False, "ambiguous": row.ambiguous} for row in value.features]}

    @staticmethod
    def _question_document(intent: QuestionIntent, question: str, source: str, fallback_reason: str | None) -> dict[str, Any]:
        return {"intent_id": intent.intent_id, "feature": intent.feature, "label": intent.label, "supported_hypothesis_ids": list(intent.supported_hypothesis_ids), "unknown_hypothesis_ids": list(intent.unknown_hypothesis_ids), "evidence_refs": list(intent.evidence_refs), "question": question, "source": source, "fallback_reason": fallback_reason, "absence_used_as_contradiction": False}


def validate_session(session: Mapping[str, Any]) -> None:
    forbidden = {"ground_truth", "ground_truth_candidate", "target_candidate_id", "reference_coordinate", "correct_candidate", "gt"}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            if forbidden & set(value):
                raise InteractiveDialogueError("el contrato operativo no admite ground truth")
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(session)
    required = {"schema_version", "contract_version", "session_id", "status", "turn_limit", "turns_used", "gallery_id", "policy", "models", "inputs", "f3", "initial_ranking", "hypotheses", "selected_question", "human_answer", "query_updates", "updated_rankings", "comparisons", "stop_reason", "events", "limitations"}
    if set(session) != required or session["schema_version"] != "1.0" or session["contract_version"] != CONTRACT_VERSION:
        raise InteractiveDialogueError("contrato de sesión incompatible")
    if session["status"] not in {"awaiting_answer", "completed"} or session["turn_limit"] != 1 or session["turns_used"] not in {0, 1}:
        raise InteractiveDialogueError("estado de sesión inválido")
    if session["status"] == "awaiting_answer" and (session["selected_question"] is None or session["turns_used"] != 0):
        raise InteractiveDialogueError("sesión en espera incoherente")
    if session["turns_used"] == 1 and session["human_answer"] is None:
        raise InteractiveDialogueError("turno consumido sin respuesta literal")
    retrieval_metadata = session["models"]["retrieval"]
    if session["initial_ranking"]["gallery_count"] != retrieval_metadata.get("expected_gallery_count"):
        raise InteractiveDialogueError("cardinalidad de galería no coincide con la identidad CT2L")
    _validate_ranking_document(session["initial_ranking"], session["gallery_id"])
    initial_ids = {row["candidate_id"] for row in session["initial_ranking"]["results"]}
    ordered_initial_ids = [row["candidate_id"] for row in sorted(session["initial_ranking"]["results"], key=lambda row: row["candidate_id"])]
    expected_universe = retrieval_metadata.get("candidate_universe_sha256")
    if expected_universe != _sha256(ordered_initial_ids):
        raise InteractiveDialogueError("universo de candidatos no coincide con la identidad CT2L")
    for updated in session["updated_rankings"]:
        _validate_ranking_document(updated["ranking"], session["gallery_id"])
        if {row["candidate_id"] for row in updated["ranking"]["results"]} != initial_ids:
            raise InteractiveDialogueError("ranking posterior no cubre la misma galería")
    previous = None
    for sequence, event in enumerate(session["events"]):
        if event["sequence"] != sequence or event["previous_event_hash"] != previous:
            raise InteractiveDialogueError("cadena de eventos inválida")
        preimage = {key: event[key] for key in ("sequence", "kind", "payload", "previous_event_hash", "recorded_at_utc")}
        expected = "dialogue-event-sha256-" + _sha256(preimage)
        if event["event_hash"] != expected:
            raise InteractiveDialogueError("hash de evento inválido")
        previous = expected
    retrieval_events = [event for event in session["events"] if event["kind"] in {"initial_retrieval_completed", "updated_retrieval_completed"}]
    expected_hashes = [_sha256(session["initial_ranking"])] + [_sha256(row["ranking"]) for row in session["updated_rankings"]]
    if [event["payload"].get("ranking_sha256") for event in retrieval_events] != expected_hashes:
        raise InteractiveDialogueError("eventos y rankings persistidos no coinciden")
    started = next(event for event in session["events"] if event["kind"] == "session_started")
    description = session["inputs"]["description"]
    if started["payload"].get("description") != description["text"] or description["sha256"] != hashlib.sha256(description["text"].encode()).hexdigest():
        raise InteractiveDialogueError("descripción literal y evento no coinciden")
    answer_events = [event for event in session["events"] if event["kind"] == "human_answer_recorded"]
    if session["human_answer"] is not None:
        if len(answer_events) != 1 or answer_events[0]["payload"].get("answer") != session["human_answer"]["text"] or session["human_answer"]["sha256"] != hashlib.sha256(session["human_answer"]["text"].encode()).hexdigest():
            raise InteractiveDialogueError("respuesta literal y evento no coinciden")
    update_events = [event for event in session["events"] if event["kind"] == "query_update_validated"]
    update_by_variant = {row["variant"]: row for row in session["query_updates"]}
    for event in update_events:
        update = update_by_variant.get(event["payload"].get("variant"))
        text_hash = hashlib.sha256(update["text"].encode()).hexdigest() if update and update["text"] is not None else None
        if update is None or text_hash != event["payload"].get("text_sha256") or update["status"] != event["payload"].get("status"):
            raise InteractiveDialogueError("actualización textual y evento no coinciden")


def write_session(session: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    validate_session(session)
    output_dir.mkdir(parents=True, exist_ok=False)
    session_path = output_dir / "session.json"
    events_path = output_dir / "events.jsonl"
    session_path.write_bytes(_canonical_json_bytes(session, newline=True))
    events_path.write_bytes(b"".join(_canonical_json_bytes(row, newline=True) for row in session["events"]))
    return session_path, events_path
