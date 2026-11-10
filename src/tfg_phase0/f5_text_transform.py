"""Transformación textual F5.2 desacoplada, reproducible y sin red implícita."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import sys
import time
from typing import Any, Mapping, Protocol, Sequence

from .f5_textual_variants import F5ValidationError, textual_variant_dataset_id


PROMPT_VERSION = "f52-text-transform-v1"
PROMPT_VERSION_V2 = "f53b-text-transform-v2"
RUN_PREFIX = "f5-transformation-run-sha256-"
TASK_TO_KIND = {
    "cartographic_rewrite_es": "es_cartographic",
    "translate_en_conventional": "en_conventional",
    "translate_en_preserve_toponyms": "en_toponym_preserved",
    "translate_en_cartographic": "en_cartographic",
}
KIND_TO_TASK = {value: key for key, value in TASK_TO_KIND.items()}
PLACEHOLDER_RE = re.compile(r"__TOPONYM_(\d{3})__")
NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?(?:\s*(?:m|km|metros?|kilómetros?|meters?|kilometers?))?", re.IGNORECASE)
NEGATION_ES = re.compile(r"\b(?:no|sin|nunca|ningun[oa]s?)\b", re.IGNORECASE)
NEGATION_EN = re.compile(r"\b(?:no|not|cannot|without|never|none)\b", re.IGNORECASE)
ORIENTATION_CONCEPTS = {
    "north": (r"\bnorte\b", r"\bnorth\b"), "south": (r"\bsur\b", r"\bsouth\b"),
    "east": (r"\beste\b", r"\beast\b"), "west": (r"\boeste\b", r"\bwest\b"),
    "right": (r"\bderecha\b", r"\bright\b"), "left": (r"\bizquierda\b", r"\bleft\b"),
    "front": (r"\bdelante\b", r"\b(?:in front|ahead)\b"), "behind": (r"\bdetr[aá]s\b", r"\bbehind\b"),
}
GEO_CONCEPTS = {
    "square": (r"\bplaza\b", r"\bsquare\b"), "park": (r"\bparque\b", r"\bpark\b"),
    "station": (r"\bestaci[oó]n\b", r"\bstation\b"), "avenue": (r"\bavenida\b", r"\bavenue\b"),
    "street": (r"\bcalle\b", r"\bstreet\b"), "intersection": (r"\bintersecci[oó]n\b", r"\bintersection\b"),
    "building": (r"\bedificios?\b", r"\bbuildings?\b"), "water": (r"\bagua\b", r"\bwater\b"),
}
VISUAL_CONCEPTS = {
    "clock": (r"\breloj\b", r"\bclock\b"), "sign": (r"\bcartel\b", r"\bsign\b"),
    "facade": (r"\bfachada\b", r"\bfacade\b"), "red": (r"\broj[oa]s?\b", r"\bred\b"),
    "brick": (r"\bladrillo\b", r"\bbrick\b"), "illuminated": (r"\bluminos[oa]\b", r"\billuminated\b"),
}


class TextTransformationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GenerationConfig:
    max_new_tokens: int = 256
    seed: int = 0
    do_sample: bool = False
    temperature: float = 0.0
    enable_thinking: bool = False
    max_output_characters: int = 2400
    max_length_ratio: float = 2.5

    def __post_init__(self):
        if self.max_new_tokens < 1 or self.max_output_characters < 1 or self.max_length_ratio < 1:
            raise ValueError("configuración de generación fuera de rango")
        if self.do_sample or self.temperature != 0 or self.enable_thinking:
            raise ValueError("F5.2 requiere decodificación no-thinking determinista")


@dataclass(frozen=True)
class TransformerMetadata:
    adapter: str
    model_id: str
    revision: str
    tokenizer_id: str
    tokenizer_revision: str
    artifact_manifest_sha256: str
    real_model_inference: bool


@dataclass(frozen=True)
class TransformResult:
    text: str
    raw_output: str
    duration_ms: float


class TextTransformer(Protocol):
    @property
    def metadata(self) -> TransformerMetadata: ...
    @property
    def resource_usage(self) -> Mapping[str, Any]: ...
    def transform(self, original_text: str, task: str, protected_toponyms: Sequence[str], config: GenerationConfig) -> TransformResult: ...
    def close(self) -> None: ...


class FakeTransformer:
    """Doble determinista; nunca debe presentarse como inferencia de modelo real."""

    def __init__(self, outputs: Mapping[str, str] | None = None):
        self._outputs = dict(outputs or {})
        self._closed = False
        self._metadata = TransformerMetadata("fake-deterministic-v1", "fake/f52", "test-v1", "fake/f52", "test-v1", "0" * 64, False)
        self._resource_usage = {"model_load_ms": 0.0, "cuda_before_load": {"allocated_bytes": None, "reserved_bytes": None}, "cuda_after_load": {"allocated_bytes": None, "reserved_bytes": None}, "cuda_peak_allocated_bytes": None, "cuda_after_close": {"allocated_bytes": None, "reserved_bytes": None}}

    @property
    def metadata(self) -> TransformerMetadata:
        return self._metadata

    @property
    def resource_usage(self) -> Mapping[str, Any]:
        return self._resource_usage

    def transform(self, original_text: str, task: str, protected_toponyms: Sequence[str], config: GenerationConfig) -> TransformResult:
        if self._closed:
            raise TextTransformationError("transformador cerrado")
        if task not in TASK_TO_KIND:
            raise TextTransformationError(f"tarea no soportada: {task}")
        started = time.perf_counter()
        text = self._outputs.get(task, original_text)
        return TransformResult(text, text, (time.perf_counter() - started) * 1000)

    def close(self) -> None:
        self._closed = True


class QwenTransformersAdapter:
    """Adaptador local-only para Qwen3-8B; imports y carga son perezosos."""

    def __init__(self, model_path: Path, *, model_id: str, revision: str, device: str = "cuda"):
        if not model_path.is_dir():
            raise TextTransformationError(f"snapshot Qwen local ausente: {model_path}")
        try:
            import torch
            import transformers
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as error:
            raise TextTransformationError("entorno Qwen incompleto; se requieren torch y transformers compatibles") from error
        self._torch, self._transformers, self._closed = torch, transformers, False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        before = self._cuda_memory()
        load_started = time.perf_counter()
        self._tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
        self._model = AutoModelForCausalLM.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False, torch_dtype="auto", device_map=device)
        self._model.eval()
        loaded_at = time.perf_counter()
        manifest_hash = hash_tree_manifest(model_path)
        tokenizer_revision = getattr(self._tokenizer, "init_kwargs", {}).get("revision") or revision
        self._metadata = TransformerMetadata("transformers-qwen3-v1", model_id, revision, model_id, str(tokenizer_revision), manifest_hash, True)
        self._resource_usage = {"model_load_ms": (loaded_at - load_started) * 1000, "cuda_before_load": before, "cuda_after_load": self._cuda_memory(), "cuda_peak_allocated_bytes": int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else None, "cuda_after_close": {"allocated_bytes": None, "reserved_bytes": None}}

    @property
    def metadata(self) -> TransformerMetadata:
        return self._metadata

    @property
    def resource_usage(self) -> Mapping[str, Any]:
        if self._torch.cuda.is_available():
            self._resource_usage["cuda_peak_allocated_bytes"] = max(self._resource_usage["cuda_peak_allocated_bytes"] or 0, int(self._torch.cuda.max_memory_allocated()))
        return self._resource_usage

    def transform(self, original_text: str, task: str, protected_toponyms: Sequence[str], config: GenerationConfig) -> TransformResult:
        if self._closed:
            raise TextTransformationError("transformador Qwen cerrado")
        prompt, mapping = prepare_prompt(original_text, task, protected_toponyms)
        return self.generate_prompt(prompt, config, restore_mapping=mapping)

    def generate_prompt(self, prompt: str, config: GenerationConfig, *, restore_mapping: Mapping[str, str] | None = None, prefix_allowed_tokens_fn=None) -> TransformResult:
        """Genera desde un prompt versionado reutilizando modelo y tokenizer cargados."""
        if self._closed:
            raise TextTransformationError("transformador Qwen cerrado")
        started = time.perf_counter()
        random.seed(config.seed)
        self._torch.manual_seed(config.seed)
        messages = [{"role": "user", "content": prompt}]
        try:
            rendered = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            rendered = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer(rendered, return_tensors="pt").to(self._model.device)
        with self._torch.inference_mode():
            generated = self._model.generate(**inputs, max_new_tokens=config.max_new_tokens, do_sample=False, temperature=None, prefix_allowed_tokens_fn=prefix_allowed_tokens_fn)
        output_tokens = generated[0, inputs["input_ids"].shape[1]:]
        raw = self._tokenizer.decode(output_tokens, skip_special_tokens=True).strip()
        text = restore_toponyms(raw, restore_mapping) if restore_mapping else raw
        return TransformResult(text, raw, (time.perf_counter() - started) * 1000)

    def close(self) -> None:
        if not self._closed:
            self._model = None
            self._tokenizer = None
            if self._torch.cuda.is_available():
                self._torch.cuda.empty_cache()
            self._resource_usage["cuda_after_close"] = self._cuda_memory()
            self._closed = True

    def _cuda_memory(self) -> dict[str, int | None]:
        if not self._torch.cuda.is_available():
            return {"allocated_bytes": None, "reserved_bytes": None}
        return {"allocated_bytes": int(self._torch.cuda.memory_allocated()), "reserved_bytes": int(self._torch.cuda.memory_reserved())}


def hash_tree_manifest(root: Path) -> str:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and ".cache" not in item.relative_to(root).parts):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        rows.append({"path": relative, "size": path.stat().st_size, "sha256": digest.hexdigest()})
    if not rows:
        raise TextTransformationError("snapshot de modelo vacío")
    return hashlib.sha256(_canonical_bytes(rows)).hexdigest()


def protect_toponyms(text: str, toponyms: Sequence[str]) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    protected = text
    spans = []
    for index, mention in enumerate(toponyms):
        matches = list(re.finditer(re.escape(mention), text))
        if len(matches) != 1:
            raise TextTransformationError(f"topónimo protegido debe aparecer exactamente una vez: {mention}")
        match = matches[0]
        placeholder = f"__TOPONYM_{index:03d}__"
        mapping[placeholder] = mention
        spans.append((match.start(), match.end(), placeholder))
    for start, end, placeholder in sorted(spans, reverse=True):
        protected = protected[:start] + placeholder + protected[end:]
    return protected, mapping


def restore_toponyms(text: str, mapping: Mapping[str, str]) -> str:
    found = PLACEHOLDER_RE.findall(text)
    expected = {key.removeprefix("__TOPONYM_").removesuffix("__") for key in mapping}
    if set(found) != expected or len(found) != len(mapping):
        raise TextTransformationError("placeholders de topónimos perdidos, duplicados o inventados")
    restored = text
    for placeholder, mention in mapping.items():
        if restored.count(placeholder) != 1:
            raise TextTransformationError(f"placeholder inválido: {placeholder}")
        restored = restored.replace(placeholder, mention)
    if PLACEHOLDER_RE.search(restored):
        raise TextTransformationError("quedan placeholders sin restaurar")
    return restored


def build_prompt(text: str, task: str, protected_placeholders: Sequence[str] = ()) -> str:
    if task not in TASK_TO_KIND:
        raise TextTransformationError(f"tarea no soportada: {task}")
    common = "Devuelve únicamente el texto transformado, sin explicación, listas, comillas ni metacomentarios. No inventes objetos, relaciones, números, distancias, negaciones u orientaciones."
    instructions = {
        "cartographic_rewrite_es": "Reescribe en español conservando topónimos, calles, cruces, plazas, parques, edificios, estaciones, relaciones espaciales, negaciones y orientación explícita. Elimina solo detalles visuales sin representación cartográfica evidente.",
        "translate_en_conventional": "Traduce convencionalmente al inglés conservando significado, relaciones espaciales, negaciones, números y distancias. Los nombres propios pueden seguir la traducción convencional.",
        "translate_en_preserve_toponyms": "Traduce al inglés conservando exactamente cada placeholder protegido. No traduzcas, alteres, dupliques ni elimines placeholders.",
        "translate_en_cartographic": "Traduce y reformula en inglés cartográfico. Conserva exactamente cada placeholder protegido, entidades y relaciones representables en OSM, relaciones espaciales, negaciones, números, distancias y orientación explícita. Elimina solo detalles visuales sin representación cartográfica evidente. No añadas ni infieras información.",
    }[task]
    protected = f"\nPlaceholders obligatorios: {', '.join(protected_placeholders)}" if protected_placeholders else ""
    return f"{common}\nTarea: {instructions}{protected}\nTexto:\n{text}"


def prepare_prompt(original_text: str, task: str, protected_toponyms: Sequence[str]) -> tuple[str, dict[str, str]]:
    protected_text, mapping = protect_toponyms(original_text, protected_toponyms) if task in {"translate_en_preserve_toponyms", "translate_en_cartographic"} else (original_text, {})
    return build_prompt(protected_text, task, tuple(mapping)), mapping


def validate_transformation(original: str, output: str, task: str, protected_toponyms: Sequence[str], config: GenerationConfig) -> dict[str, Any]:
    issues = []
    cleaned = output.strip()
    if not cleaned:
        issues.append(_issue("empty_output", "error", "La salida está vacía."))
    if len(cleaned) > config.max_output_characters or len(cleaned) > max(1, int(len(original) * config.max_length_ratio)):
        issues.append(_issue("excessive_length", "error", "La salida supera el límite de longitud."))
    expected_language = "es" if task == "cartographic_rewrite_es" else "en"
    detected = heuristic_language(cleaned)
    if detected not in {expected_language, "unknown"}:
        issues.append(_issue("language_mismatch", "error", f"Idioma heurístico {detected}; se esperaba {expected_language}."))
    original_numbers, output_numbers = NUMBER_RE.findall(original), NUMBER_RE.findall(cleaned)
    if sorted(value.casefold() for value in original_numbers) != sorted(value.casefold() for value in output_numbers):
        issues.append(_issue("numbers_changed", "error", "Se perdieron o modificaron números/distancias."))
    input_negative = bool(NEGATION_ES.search(original) or NEGATION_EN.search(original))
    output_negative = bool(NEGATION_ES.search(cleaned) or NEGATION_EN.search(cleaned))
    if input_negative != output_negative:
        issues.append(_issue("negation_changed", "error", "Cambió la presencia de una negación explícita."))
    for concept, patterns in ORIENTATION_CONCEPTS.items():
        if any(re.search(pattern, original, re.IGNORECASE) for pattern in patterns) and not any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in patterns):
            issues.append(_issue("orientation_lost", "error", f"Se perdió la orientación o relación {concept}."))
    original_geo = {concept for concept, patterns in GEO_CONCEPTS.items() if any(re.search(pattern, original, re.IGNORECASE) for pattern in patterns)}
    output_geo = {concept for concept, patterns in GEO_CONCEPTS.items() if any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in patterns)}
    for concept in sorted(output_geo - original_geo):
        issues.append(_issue("possible_geographic_invention", "warning", f"Aparece un elemento geográfico no detectado en el original: {concept}."))
    for mention in protected_toponyms:
        if cleaned.count(mention) != 1:
            issues.append(_issue("protected_toponym_changed", "error", f"El topónimo protegido no aparece exactamente una vez: {mention}."))
    return {"structurally_valid": not any(issue["severity"] == "error" for issue in issues), "human_review_required": True, "issues": issues}


def heuristic_language(text: str) -> str:
    words = set(re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE))
    es = len(words & {"estoy", "una", "un", "hay", "junto", "calle", "plaza", "parque", "edificio", "derecha", "izquierda", "norte", "sur", "sin"})
    en = len(words & {"i", "am", "a", "an", "there", "next", "street", "square", "park", "building", "right", "left", "north", "south", "without"})
    if es == en:
        return "unknown"
    return "es" if es > en else "en"


def materialize_variants(source_sidecar: Mapping[str, Any], transformer: TextTransformer, config: GenerationConfig, *, source_logical_path: str, source_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    derived = json.loads(json.dumps(source_sidecar, ensure_ascii=False))
    prompt_version = PROMPT_VERSION_V2 if source_sidecar["contract_version"] == "f5-textual-variant-dataset-v2" else PROMPT_VERSION
    records = []
    for observation in derived["observations"]:
        original = next(variant for variant in observation["variants"] if variant["kind"] == "es_original")
        proper = [item["mention"] for item in observation["toponyms"] if item["name_kind"] == "proper_name" and item["review_status"] == "reviewed"]
        for variant in observation["variants"]:
            if variant["kind"] == "es_original" or variant["status"] != "pending":
                continue
            task = KIND_TO_TASK[variant["kind"]]
            protected = proper if task in {"translate_en_preserve_toponyms", "translate_en_cartographic"} else []
            prompt, _ = prepare_prompt(original["text"], task, protected)
            started = time.perf_counter()
            try:
                result = transformer.transform(original["text"], task, protected, config)
                validation = validate_transformation(original["text"], result.text, task, protected, config)
                status = "generated" if validation["structurally_valid"] else "rejected"
                output, raw, duration = result.text, result.raw_output, result.duration_ms
            except Exception as error:
                validation = {"structurally_valid": False, "human_review_required": True, "issues": [_issue("transformer_error", "error", str(error))]}
                status, output, raw, duration = "error", None, None, (time.perf_counter() - started) * 1000
            variant_id = f"{observation['source_query_id']}-{variant['kind']}-f52-v1" if output is not None else None
            if output is not None:
                preserved, removed, modified = transformation_elements(original["text"], output, variant["kind"], proper)
                variant.update({
                    "variant_id": variant_id, "status": "generated" if status == "generated" else "rejected", "text": output,
                    "generation": {"method": "model_assisted_cartographic_rewrite" if variant["kind"] == "es_cartographic" else "model_assisted_translation", "tool_or_model": transformer.metadata.model_id, "version": transformer.metadata.revision, "configuration_or_prompt": prompt_version, "transformation_time_ms": None},
                    "review_status": "pending" if status == "generated" else "rejected",
                    "transformations": ["cartographic_filter"] if variant["kind"] == "es_cartographic" else (["translation", "cartographic_filter", "toponym_protection"] if variant["kind"] == "en_cartographic" else (["translation", "toponym_protection"] if variant["kind"] == "en_toponym_preserved" else ["translation"])),
                    "preserved_elements": preserved, "removed_elements": removed, "modified_elements": modified, "protected_toponyms": list(protected),
                })
            records.append({
                "source_query_id": observation["source_query_id"], "variant_id": variant_id, "kind": variant["kind"], "task": task, "status": status,
                "input_text_sha256": _sha256_text(original["text"]), "output_text_sha256": _sha256_text(output) if output is not None else None,
                "protected_toponyms": list(protected), "prompt_sha256": _sha256_text(prompt), "raw_output_sha256": _sha256_text(raw) if raw is not None else None,
                "duration_ms": duration, "validation": validation,
            })
    derived["dataset_version"] = source_sidecar["dataset_version"] + "-f52"
    derived["dataset_id"] = textual_variant_dataset_id(derived)
    derived_raw = _canonical_bytes(derived)
    run = {
        "schema_version": "1.0", "contract_version": "f5-transformation-run-v1", "run_id": RUN_PREFIX + "0" * 64,
        "source_sidecar": {"logical_path": source_logical_path, "dataset_id": source_sidecar["dataset_id"], "sha256": source_sha256},
        "derived_sidecar": {"logical_path": "derived-sidecar.json", "dataset_id": derived["dataset_id"], "sha256": hashlib.sha256(derived_raw).hexdigest()},
        "transformer": transformer.metadata.__dict__,
        "generation": {"prompt_version": prompt_version, "do_sample": config.do_sample, "temperature": config.temperature, "seed": config.seed, "max_new_tokens": config.max_new_tokens, "enable_thinking": config.enable_thinking},
        "environment": environment_metadata(transformer.metadata.real_model_inference),
        "resource_usage": json.loads(json.dumps(transformer.resource_usage)),
        "records": records,
        "limitations": ["automatic_heuristics_do_not_guarantee_semantic_equivalence", "human_review_required", "no_ground_truth_used", "no_osm_preselection_or_reranking"],
    }
    run["run_id"] = transformation_run_id(run)
    return derived, run


def transformation_run_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "source_sidecar", "derived_sidecar", "transformer", "generation", "environment", "resource_usage", "records", "limitations")}
    return RUN_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def finalize_transformation_run_resources(document: dict[str, Any], transformer: TextTransformer) -> None:
    """Captura memoria tras close y recalcula la identidad del manifiesto."""
    document["resource_usage"] = json.loads(json.dumps(transformer.resource_usage))
    document["run_id"] = transformation_run_id(document)


def transformation_elements(original: str, output: str, kind: str, proper_toponyms: Sequence[str]) -> tuple[list[str], list[str], list[dict[str, str]]]:
    concepts = {**GEO_CONCEPTS, **VISUAL_CONCEPTS, **ORIENTATION_CONCEPTS}
    original_elements = {name for name, patterns in concepts.items() if any(re.search(pattern, original, re.IGNORECASE) for pattern in patterns)}
    output_elements = {name for name, patterns in concepts.items() if any(re.search(pattern, output, re.IGNORECASE) for pattern in patterns)}
    preserved = sorted(original_elements & output_elements)
    removed = sorted(original_elements - output_elements)
    modified = []
    for mention in proper_toponyms:
        if mention in output:
            preserved.append(mention)
        elif kind == "en_conventional":
            modified.append({"from": mention, "to": "<not preserved literally>", "reason": "conventional_translation_toponym_changed_or_omitted"})
        else:
            removed.append(mention)
    return sorted(set(preserved)), sorted(set(removed)), modified


def environment_metadata(real: bool) -> dict[str, Any]:
    torch_version = transformers_version = None
    if real:
        try:
            import torch, transformers
            torch_version, transformers_version = torch.__version__, transformers.__version__
        except ImportError:
            pass
    return {"python_version": platform.python_version(), "torch_version": torch_version, "transformers_version": transformers_version, "device": "cuda" if real else "cpu-fake", "hardware": platform.machine()}


def _issue(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
