"""Extracción geográfica estructurada F5.3 con evidencia textual verificable."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import time
from typing import Any, Mapping, Protocol, Sequence

from .f5_text_transform import GenerationConfig, QwenTransformersAdapter, TransformerMetadata
from .f5_textual_variants import F5ValidationError


PROMPT_VERSION = "f53-geographic-extraction-v1"
EXTRACTION_PREFIX = "f5-geographic-extractions-sha256-"
COMPARISON_PREFIX = "f5-geographic-extraction-comparison-sha256-"
ENTITY_TYPES = {"street", "road", "intersection", "square", "park", "building", "church", "station", "bridge", "river", "monument", "other", "unknown"}
PREDICATES = {"near", "next_to", "inside", "between", "in_front_of", "behind", "left_of_observer", "right_of_observer", "north_of", "south_of", "east_of", "west_of", "intersects", "unknown"}
CARDINAL_PREDICATES = {"north_of", "south_of", "east_of", "west_of"}
EGOCENTRIC_PREDICATES = {"in_front_of", "behind", "left_of_observer", "right_of_observer"}
NEGATION_RE = re.compile(r"\b(?:no|sin|nunca|ningun[oa]s?|not|without|never|none)\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?")


class GeographicExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractionConfig:
    max_new_tokens: int = 768
    seed: int = 0
    max_attempts: int = 2

    def __post_init__(self):
        if self.max_new_tokens < 1 or not 1 <= self.max_attempts <= 2:
            raise ValueError("configuración F5.3 fuera de rango")

    def generation_config(self) -> GenerationConfig:
        return GenerationConfig(max_new_tokens=self.max_new_tokens, seed=self.seed, max_output_characters=12000, max_length_ratio=20.0)


@dataclass(frozen=True)
class ExtractionResult:
    raw_outputs: tuple[str, ...]
    extraction: Mapping[str, Any] | None
    validation: Mapping[str, Any]
    duration_ms: float


class GeographicExtractor(Protocol):
    @property
    def metadata(self) -> TransformerMetadata: ...
    @property
    def resource_usage(self) -> Mapping[str, Any]: ...
    def extract(self, text: str, language: str, protected_toponyms: Sequence[str], config: ExtractionConfig) -> ExtractionResult: ...
    def close(self) -> None: ...


class FakeGeographicExtractor:
    """Doble determinista con outputs JSON por texto; no representa Qwen real."""

    def __init__(self, outputs: Mapping[str, str | Sequence[str]]):
        self._outputs = {key: (value,) if isinstance(value, str) else tuple(value) for key, value in outputs.items()}
        self._metadata = TransformerMetadata("fake-geographic-extractor-v1", "fake/f53", "test-v1", "fake/f53", "test-v1", "0" * 64, False)
        self._resource_usage = {"model_load_ms": 0.0, "cuda_before_load": {"allocated_bytes": None, "reserved_bytes": None}, "cuda_after_load": {"allocated_bytes": None, "reserved_bytes": None}, "cuda_peak_allocated_bytes": None, "cuda_after_close": {"allocated_bytes": None, "reserved_bytes": None}}
        self._closed = False

    @property
    def metadata(self) -> TransformerMetadata:
        return self._metadata

    @property
    def resource_usage(self) -> Mapping[str, Any]: return self._resource_usage

    def extract(self, text: str, language: str, protected_toponyms: Sequence[str], config: ExtractionConfig) -> ExtractionResult:
        if self._closed:
            raise GeographicExtractionError("extractor cerrado")
        try:
            outputs = self._outputs[text]
        except KeyError as error:
            raise GeographicExtractionError("fixture fake sin output para el texto") from error
        return extract_from_raw_outputs(text, language, protected_toponyms, outputs[:config.max_attempts])

    def close(self) -> None:
        self._closed = True


class QwenGeographicExtractor:
    """Extractor real que reutiliza una única instancia QwenTransformersAdapter."""

    def __init__(self, adapter: QwenTransformersAdapter):
        self._adapter = adapter

    @property
    def metadata(self) -> TransformerMetadata:
        return self._adapter.metadata

    @property
    def resource_usage(self) -> Mapping[str, Any]: return self._adapter.resource_usage

    def extract(self, text: str, language: str, protected_toponyms: Sequence[str], config: ExtractionConfig) -> ExtractionResult:
        prompt = build_extraction_prompt(text, language, protected_toponyms)
        raw_outputs = []
        started = time.perf_counter()
        for attempt in range(config.max_attempts):
            result = self._adapter.generate_prompt(prompt, config.generation_config())
            raw_outputs.append(result.raw_output)
            parsed, validation = parse_and_validate_extraction(text, language, protected_toponyms, result.raw_output)
            if parsed is not None and validation["structurally_valid"] and validation["semantically_valid"]:
                return ExtractionResult(tuple(raw_outputs), parsed, validation, (time.perf_counter() - started) * 1000)
            if attempt + 1 < config.max_attempts:
                codes = ", ".join(issue["code"] for issue in validation["issues"] if issue["severity"] == "error") or "invalid_json"
                prompt = build_retry_prompt(prompt, result.raw_output, codes)
        return ExtractionResult(tuple(raw_outputs), None, validation, (time.perf_counter() - started) * 1000)

    def close(self) -> None:
        self._adapter.close()


def build_extraction_prompt(text: str, language: str, protected_toponyms: Sequence[str]) -> str:
    protected = json.dumps(list(protected_toponyms), ensure_ascii=False)
    indexed = " ".join(f"{index}:{json.dumps(character, ensure_ascii=False)}" for index, character in enumerate(text))
    return f"""Extrae únicamente información geográfica explícita del texto y devuelve solo JSON válido, sin Markdown ni explicación.
No inventes coordenadas, distancias, nombres, objetos, orientación o relaciones. No conviertas izquierda/derecha/delante/detrás a cardinales. Los spans usan índices Unicode sobre el texto exacto, start inclusivo y end exclusivo. evidence.text DEBE ser exactamente text[start:end], no la frase completa salvo que start=0 y end sea la longitud total. Usa exclusivamente el mapa de caracteres proporcionado para calcular spans; end es el índice posterior al último carácter. Cada entidad, atributo, relación y negación debe incluir evidencia literal. Usa entity_id e1,e2..., relation_id r1,r2..., attribute_id at1,at2..., negation_id n1,n2... y ambiguity_id a1,a2.... Referencias permitidas: observer o IDs declarados. object_ids contiene uno o dos IDs; usa dos solo para between. Si between menciona tres elementos, representa dos en la relación y registra la incompletitud en ambiguities. Una ausencia negada debe usar entity.negated=true y una entrada negations con target_kind y target_id; no uses campos entity_id/negated dentro de negations y no la uses como evidencia positiva. reference_frame solo puede ser none, egocentric, cardinal o unknown. Usa egocentric para izquierda/derecha/delante/detrás y cardinal para norte/sur/este/oeste. observer_orientation solo puede ser reported si el texto declara hacia dónde mira el observador; una relación norte_de entre entidades no es la orientación del observador. En otro caso usa unknown. No uses status verified. Si no hay elementos geográficos, deja entities, relations y negations vacíos y añade una ambiguity insufficient_information; no copies entidades del ejemplo de formato.
Tipos de entidad: street, road, intersection, square, park, building, church, station, bridge, river, monument, other, unknown.
Predicados: near, next_to, inside, between, in_front_of, behind, left_of_observer, right_of_observer, north_of, south_of, east_of, west_of, intersects, unknown.
Topónimos propios protegidos: {protected}
Idioma: {language}
Texto exacto: {json.dumps(text, ensure_ascii=False)}
Mapa índice:carácter del texto exacto: {indexed}
Formato obligatorio. El siguiente JSON muestra solo la estructura; no reutilices sus entidades, atributos o valores si no aparecen en el texto. evidence siempre tiene text, span {{start,end}} y support explicit o linguistic_interpretation:
{{"schema_version":"1.0","entities":[{{"entity_id":"e1","type":"square","name":null,"negated":false,"attributes":[{{"attribute_id":"at1","key":"width","value":"narrow","negated":false,"evidence":{{"text":"estrecha","span":{{"start":15,"end":23}},"support":"explicit"}}}}],"evidence":{{"text":"una plaza","span":{{"start":5,"end":14}},"support":"explicit"}}}}],"relations":[{{"relation_id":"r1","subject":"observer","predicate":"near","object_ids":["e1"],"negated":false,"reference_frame":"none","evidence":{{"text":"junto a","span":{{"start":0,"end":7}},"support":"explicit"}}}}],"negations":[],"observer_orientation":{{"status":"unknown","cardinal":null,"bearing_degrees":null,"reference_frame":"unknown","evidence":null}},"ambiguities":[]}}"""


def build_retry_prompt(original_prompt: str, raw_output: str, error_codes: str) -> str:
    return f"""{original_prompt}
El intento anterior fue rechazado por: {error_codes}.
Salida anterior: {json.dumps(raw_output, ensure_ascii=False)}
Genera de nuevo desde cero. Devuelve solo un objeto JSON válido y no copies texto fuera del JSON."""


def parse_and_validate_extraction(text: str, language: str, protected_toponyms: Sequence[str], raw_output: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    issues = []
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as error:
        return None, validation_result(False, False, [issue("invalid_json", "error", f"JSON inválido: {error.msg}")])
    if not isinstance(parsed, dict):
        return None, validation_result(False, False, [issue("root_not_object", "error", "La raíz debe ser un objeto JSON.")])
    structural = validate_extraction_structure(parsed)
    issues.extend(structural)
    if any(row["severity"] == "error" for row in issues):
        return parsed, validation_result(False, False, issues)
    issues.extend(validate_extraction_semantics(text, language, protected_toponyms, parsed))
    semantic = not any(row["severity"] == "error" for row in issues)
    return parsed, validation_result(True, semantic, issues)


def validate_extraction_structure(extraction: Mapping[str, Any]) -> list[dict[str, str]]:
    issues = []
    root_fields = {"schema_version", "entities", "relations", "negations", "observer_orientation", "ambiguities"}
    if set(extraction) != root_fields or extraction.get("schema_version") != "1.0":
        return [issue("invalid_root_fields", "error", "Campos raíz o schema_version incompatibles.")]
    if not all(isinstance(extraction[field], list) for field in ("entities", "relations", "negations", "ambiguities")) or not isinstance(extraction["observer_orientation"], Mapping):
        return [issue("invalid_root_types", "error", "Colecciones u orientación con tipo incompatible.")]
    entity_ids, relation_ids, attribute_ids, negation_ids, ambiguity_ids = set(), set(), set(), set(), set()
    for entity in extraction["entities"]:
        required = {"entity_id", "type", "name", "negated", "attributes", "evidence"}
        if not isinstance(entity, Mapping) or set(entity) != required or not re.fullmatch(r"e[1-9][0-9]*", str(entity.get("entity_id", ""))) or entity.get("type") not in ENTITY_TYPES or not isinstance(entity.get("negated"), bool) or not isinstance(entity.get("attributes"), list):
            issues.append(issue("invalid_entity", "error", "Entidad incompatible con el contrato.")); continue
        if entity["entity_id"] in entity_ids: issues.append(issue("duplicate_entity_id", "error", f"ID duplicado: {entity['entity_id']}"))
        entity_ids.add(entity["entity_id"])
        if entity["name"] is not None and (not isinstance(entity["name"], str) or not entity["name"]): issues.append(issue("invalid_entity_name", "error", "Nombre de entidad inválido."))
        issues.extend(validate_evidence_shape(entity["evidence"], "entity"))
        for attribute in entity["attributes"]:
            required_attribute = {"attribute_id", "key", "value", "negated", "evidence"}
            if not isinstance(attribute, Mapping) or set(attribute) != required_attribute or not re.fullmatch(r"at[1-9][0-9]*", str(attribute.get("attribute_id", ""))) or not isinstance(attribute.get("key"), str) or not attribute.get("key") or not isinstance(attribute.get("value"), str) or not attribute.get("value") or not isinstance(attribute.get("negated"), bool):
                issues.append(issue("invalid_attribute", "error", "Atributo incompatible con el contrato.")); continue
            if attribute["attribute_id"] in attribute_ids: issues.append(issue("duplicate_attribute_id", "error", f"ID duplicado: {attribute['attribute_id']}"))
            attribute_ids.add(attribute["attribute_id"]); issues.extend(validate_evidence_shape(attribute["evidence"], "attribute"))
    references = entity_ids | {"observer"}
    for relation in extraction["relations"]:
        required = {"relation_id", "subject", "predicate", "object_ids", "negated", "reference_frame", "evidence"}
        if not isinstance(relation, Mapping) or set(relation) != required or not re.fullmatch(r"r[1-9][0-9]*", str(relation.get("relation_id", ""))) or relation.get("predicate") not in PREDICATES or relation.get("reference_frame") not in {"none", "egocentric", "cardinal", "unknown"} or not isinstance(relation.get("negated"), bool):
            issues.append(issue("invalid_relation", "error", "Relación incompatible con el contrato.")); continue
        if relation["relation_id"] in relation_ids: issues.append(issue("duplicate_relation_id", "error", f"ID duplicado: {relation['relation_id']}"))
        relation_ids.add(relation["relation_id"])
        if relation["subject"] not in references or not isinstance(relation["object_ids"], list) or not 1 <= len(relation["object_ids"]) <= 2 or len(relation["object_ids"]) != len(set(relation["object_ids"])) or any(value not in references for value in relation["object_ids"]): issues.append(issue("unknown_relation_reference", "error", f"Relación {relation['relation_id']} referencia IDs inexistentes o inválidos."))
        if relation["predicate"] == "between" and len(relation["object_ids"]) != 2: issues.append(issue("between_requires_two_objects", "error", "between requiere dos object_ids."))
        if relation["predicate"] != "between" and len(relation["object_ids"]) != 1: issues.append(issue("relation_requires_one_object", "error", "La relación requiere un object_id."))
        issues.extend(validate_evidence_shape(relation["evidence"], "relation"))
    targets = entity_ids | relation_ids | attribute_ids
    for negation in extraction["negations"]:
        required = {"negation_id", "target_kind", "target_id", "evidence"}
        if not isinstance(negation, Mapping) or set(negation) != required or not re.fullmatch(r"n[1-9][0-9]*", str(negation.get("negation_id", ""))) or negation.get("target_kind") not in {"entity", "relation", "attribute"}:
            issues.append(issue("invalid_negation", "error", "Negación incompatible con el contrato.")); continue
        if negation["negation_id"] in negation_ids: issues.append(issue("duplicate_negation_id", "error", f"ID duplicado: {negation['negation_id']}"))
        negation_ids.add(negation["negation_id"])
        if negation["target_id"] not in targets: issues.append(issue("unknown_negation_target", "error", f"Negación {negation['negation_id']} referencia un ID inexistente."))
        issues.extend(validate_evidence_shape(negation["evidence"], "negation"))
    orientation = extraction["observer_orientation"]
    required_orientation = {"status", "cardinal", "bearing_degrees", "reference_frame", "evidence"}
    if set(orientation) != required_orientation or orientation.get("status") not in {"unknown", "reported", "verified"} or orientation.get("cardinal") not in {None, "north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"} or orientation.get("reference_frame") not in {"unknown", "cardinal"}:
        issues.append(issue("invalid_observer_orientation", "error", "Orientación incompatible con el contrato."))
    elif orientation["evidence"] is not None: issues.extend(validate_evidence_shape(orientation["evidence"], "orientation"))
    for ambiguity in extraction["ambiguities"]:
        required = {"ambiguity_id", "kind", "description", "entity_ids", "relation_ids", "evidence"}
        if not isinstance(ambiguity, Mapping) or set(ambiguity) != required or not re.fullmatch(r"a[1-9][0-9]*", str(ambiguity.get("ambiguity_id", ""))) or ambiguity.get("kind") not in {"ambiguous_reference", "incomplete_relation", "uncertain_entity_type", "insufficient_information", "other"} or not isinstance(ambiguity.get("description"), str) or not ambiguity.get("description"):
            issues.append(issue("invalid_ambiguity", "error", "Ambigüedad incompatible con el contrato.")); continue
        if ambiguity["ambiguity_id"] in ambiguity_ids: issues.append(issue("duplicate_ambiguity_id", "error", f"ID duplicado: {ambiguity['ambiguity_id']}"))
        ambiguity_ids.add(ambiguity["ambiguity_id"])
        if any(value not in entity_ids for value in ambiguity["entity_ids"]) or any(value not in relation_ids for value in ambiguity["relation_ids"]): issues.append(issue("unknown_ambiguity_reference", "error", "Ambigüedad referencia IDs inexistentes."))
        if ambiguity["evidence"] is not None: issues.extend(validate_evidence_shape(ambiguity["evidence"], "ambiguity"))
    return issues


def validate_evidence_shape(evidence: Any, owner: str) -> list[dict[str, str]]:
    if not isinstance(evidence, Mapping) or set(evidence) != {"text", "span", "support"} or not isinstance(evidence.get("text"), str) or not evidence.get("text") or evidence.get("support") not in {"explicit", "linguistic_interpretation"}:
        return [issue("invalid_evidence", "error", f"Evidencia inválida para {owner}.")]
    span = evidence.get("span")
    if not isinstance(span, Mapping) or set(span) != {"start", "end"} or isinstance(span.get("start"), bool) or isinstance(span.get("end"), bool) or not isinstance(span.get("start"), int) or not isinstance(span.get("end"), int) or span["start"] < 0 or span["end"] <= span["start"]:
        return [issue("invalid_evidence_span", "error", f"Span inválido para {owner}.")]
    return []


def validate_extraction_semantics(text: str, language: str, protected_toponyms: Sequence[str], extraction: Mapping[str, Any]) -> list[dict[str, str]]:
    issues = []
    evidences = []
    for entity in extraction["entities"]:
        evidences.append(entity["evidence"]); evidences.extend(attribute["evidence"] for attribute in entity["attributes"])
    evidences.extend(relation["evidence"] for relation in extraction["relations"])
    evidences.extend(negation["evidence"] for negation in extraction["negations"])
    evidences.extend(ambiguity["evidence"] for ambiguity in extraction["ambiguities"] if ambiguity["evidence"] is not None)
    if extraction["observer_orientation"]["evidence"] is not None: evidences.append(extraction["observer_orientation"]["evidence"])
    for evidence in evidences:
        start, end = evidence["span"]["start"], evidence["span"]["end"]
        if end > len(text) or text[start:end] != evidence["text"]:
            issues.append(issue("evidence_span_mismatch", "error", f"La evidencia no coincide con text[{start}:{end}]."))
    proper_names = {entity["name"] for entity in extraction["entities"] if entity["name"]}
    for mention in protected_toponyms:
        if mention in text and mention not in proper_names:
            issues.append(issue("protected_toponym_missing", "error", f"Falta el topónimo protegido: {mention}."))
    negated_targets = {row["target_id"] for row in extraction["negations"]}
    declared_negated = {entity["entity_id"] for entity in extraction["entities"] if entity["negated"]}
    declared_negated |= {relation["relation_id"] for relation in extraction["relations"] if relation["negated"]}
    declared_negated |= {attribute["attribute_id"] for entity in extraction["entities"] for attribute in entity["attributes"] if attribute["negated"]}
    if negated_targets != declared_negated:
        issues.append(issue("negation_index_mismatch", "error", "Negations no corresponde exactamente a los elementos negados."))
    entity_ids = {entity["entity_id"] for entity in extraction["entities"]}
    relation_ids = {relation["relation_id"] for relation in extraction["relations"]}
    attribute_ids = {attribute["attribute_id"] for entity in extraction["entities"] for attribute in entity["attributes"]}
    valid_targets = {"entity": entity_ids, "relation": relation_ids, "attribute": attribute_ids}
    for negation in extraction["negations"]:
        if negation["target_id"] not in valid_targets[negation["target_kind"]]:
            issues.append(issue("negation_target_kind_mismatch", "error", "target_kind no corresponde al tipo del target negado."))
    if NEGATION_RE.search(text) and not extraction["negations"]:
        issues.append(issue("negation_lost", "error", "El texto contiene negación, pero la extracción no la representa."))
    orientation = extraction["observer_orientation"]
    if orientation["status"] == "verified": issues.append(issue("orientation_cannot_be_verified_from_text", "error", "El modelo textual no puede declarar orientación verificada."))
    if orientation["status"] == "unknown" and any(value is not None for value in (orientation["cardinal"], orientation["bearing_degrees"], orientation["evidence"])):
        issues.append(issue("unknown_orientation_has_values", "error", "Orientación unknown contiene valores."))
    if orientation["status"] == "reported" and orientation["evidence"] is None:
        issues.append(issue("reported_orientation_without_evidence", "error", "Orientación reportada sin evidencia."))
    for relation in extraction["relations"]:
        expected_frame = "egocentric" if relation["predicate"] in EGOCENTRIC_PREDICATES else ("cardinal" if relation["predicate"] in CARDINAL_PREDICATES else relation["reference_frame"])
        if relation["predicate"] in EGOCENTRIC_PREDICATES and relation["reference_frame"] != expected_frame: issues.append(issue("egocentric_frame_mismatch", "error", "Relación egocéntrica sin frame egocentric."))
        if relation["predicate"] in CARDINAL_PREDICATES and relation["reference_frame"] != expected_frame: issues.append(issue("cardinal_frame_mismatch", "error", "Relación cardinal sin frame cardinal."))
    if any(key in json.dumps(extraction, ensure_ascii=False).casefold() for key in ("latitude", "longitude", "distance_m", "meters", "metros")):
        issues.append(issue("forbidden_numeric_geography", "error", "La extracción contiene coordenadas o distancia numérica no permitida."))
    if not extraction["entities"] and not extraction["ambiguities"]:
        issues.append(issue("no_geographic_content", "warning", "No se extrajeron entidades ni ambigüedades."))
    return issues


def extract_from_raw_outputs(text: str, language: str, protected_toponyms: Sequence[str], raw_outputs: Sequence[str]) -> ExtractionResult:
    started = time.perf_counter(); validation = validation_result(False, False, [issue("no_output", "error", "Sin salida.")]); extraction = None
    for raw in raw_outputs:
        extraction, validation = parse_and_validate_extraction(text, language, protected_toponyms, raw)
        if extraction is not None and validation["structurally_valid"] and validation["semantically_valid"]: break
    return ExtractionResult(tuple(raw_outputs), extraction if validation["structurally_valid"] else None, validation, (time.perf_counter() - started) * 1000)


def materialize_extractions(sidecar: Mapping[str, Any], extractor: GeographicExtractor, config: ExtractionConfig, *, sidecar_logical_path: str, sidecar_sha256: str) -> dict[str, Any]:
    records = []
    for observation in sidecar["observations"]:
        protected = [item["mention"] for item in observation["toponyms"] if item["name_kind"] == "proper_name" and item["review_status"] == "reviewed"]
        for variant in observation["variants"]:
            if variant["status"] != "reviewed" or not variant["variant_id"] or not variant["text"]: continue
            try:
                result = extractor.extract(variant["text"], variant["language"], protected, config)
                status = "valid" if result.extraction is not None and result.validation["semantically_valid"] else "rejected"
            except Exception as error:
                result = ExtractionResult((str(error),), None, validation_result(False, False, [issue("extractor_error", "error", str(error))]), 0.0); status = "error"
            records.append({"source_query_id": observation["source_query_id"], "derivation_group_id": observation["derivation_group_id"], "partition": observation["partition"], "variant_id": variant["variant_id"], "variant_kind": variant["kind"], "language": variant["language"], "input_text": variant["text"], "input_text_sha256": sha256_text(variant["text"]), "protected_toponyms": protected, "status": status, "attempt_count": len(result.raw_outputs), "raw_outputs": list(result.raw_outputs), "raw_outputs_sha256": [sha256_text(raw) for raw in result.raw_outputs], "prompt_sha256": sha256_text(build_extraction_prompt(variant["text"], variant["language"], protected)), "duration_ms": result.duration_ms, "extraction": result.extraction, "validation": result.validation, "provenance": {"model_id": extractor.metadata.model_id, "revision": extractor.metadata.revision, "tokenizer_id": extractor.metadata.tokenizer_id, "tokenizer_revision": extractor.metadata.tokenizer_revision, "artifact_manifest_sha256": extractor.metadata.artifact_manifest_sha256, "prompt_version": PROMPT_VERSION, "do_sample": False, "temperature": 0, "seed": config.seed, "enable_thinking": False, "real_model_inference": extractor.metadata.real_model_inference}})
    document = {"schema_version": "1.0", "contract_version": "f5-geographic-extraction-set-v1", "extraction_set_id": EXTRACTION_PREFIX + "0" * 64, "protocol_version": PROMPT_VERSION, "source_sidecar": {"dataset_id": sidecar["dataset_id"], "sha256": sidecar_sha256, "logical_path": sidecar_logical_path}, "extractor": extractor.metadata.__dict__, "generation": {"prompt_version": PROMPT_VERSION, "do_sample": False, "temperature": 0, "seed": config.seed, "max_new_tokens": config.max_new_tokens, "enable_thinking": False, "max_attempts": config.max_attempts}, "resource_usage": json.loads(json.dumps(extractor.resource_usage)), "records": records, "limitations": ["heuristics_do_not_guarantee_semantic_correctness", "human_review_required", "no_ground_truth_accuracy", "no_osm_filtering_or_reranking"]}
    document["extraction_set_id"] = extraction_set_id(document)
    return document


def validate_extraction_set_against_sidecar(document: Mapping[str, Any], sidecar: Mapping[str, Any], *, sidecar_sha256: str) -> None:
    expected_source = {"dataset_id": sidecar["dataset_id"], "sha256": sidecar_sha256, "logical_path": document["source_sidecar"]["logical_path"]}
    if document["source_sidecar"] != expected_source:
        raise GeographicExtractionError("la extracción no referencia el sidecar proporcionado")
    variants = {(observation["source_query_id"], variant["variant_id"]): (observation, variant) for observation in sidecar["observations"] for variant in observation["variants"] if variant["status"] == "reviewed" and variant["variant_id"] and variant["text"]}
    records = {(record["source_query_id"], record["variant_id"]): record for record in document["records"]}
    if set(records) != set(variants):
        raise GeographicExtractionError("records F5.3 no corresponden exactamente a variantes revisadas")
    for key, record in records.items():
        observation, variant = variants[key]
        proper = sorted(item["mention"] for item in observation["toponyms"] if item["name_kind"] == "proper_name" and item["review_status"] == "reviewed")
        if record["derivation_group_id"] != observation["derivation_group_id"] or record["partition"] != observation["partition"] or record["variant_kind"] != variant["kind"] or record["language"] != variant["language"] or record["input_text"] != variant["text"] or record["input_text_sha256"] != sha256_text(variant["text"]) or sorted(record["protected_toponyms"]) != proper:
            raise GeographicExtractionError("provenance F5.3 no corresponde al sidecar")


def extraction_set_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "protocol_version", "source_sidecar", "extractor", "generation", "resource_usage", "records", "limitations")}
    return EXTRACTION_PREFIX + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def finalize_extraction_resources(document: dict[str, Any], extractor: GeographicExtractor) -> None:
    document["resource_usage"] = json.loads(json.dumps(extractor.resource_usage)); document["extraction_set_id"] = extraction_set_id(document)


def compare_extraction_set(document: Mapping[str, Any], *, extraction_set_sha256: str) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for record in document["records"]:
        if record["status"] == "valid" and record["extraction"] is not None:
            groups.setdefault(record["source_query_id"], []).append(record)
    rows = []
    for source_query_id, records in sorted(groups.items()):
        anchors = [record for record in records if record["variant_kind"] == "es_original"]
        if len(anchors) != 1:
            continue
        anchor = anchors[0]
        for variant in sorted((record for record in records if record is not anchor), key=lambda record: record["variant_kind"]):
            rows.append(compare_extractions(source_query_id, anchor, variant))
    report = {"schema_version": "1.0", "contract_version": "f5-geographic-extraction-comparison-v1", "comparison_id": COMPARISON_PREFIX + "0" * 64, "extraction_set_id": document["extraction_set_id"], "extraction_set_sha256": extraction_set_sha256, "comparisons": rows, "accuracy_available": False, "limitations": ["descriptive_extraction_consistency_only", "no_reference_annotations", "no_ground_truth_accuracy", "local_ids_compared_by_semantic_signature"]}
    report["comparison_id"] = extraction_comparison_id(report)
    return report


def compare_extractions(source_query_id: str, anchor: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    left, right = anchor["extraction"], variant["extraction"]
    left_entities, right_entities = entity_signatures(left), entity_signatures(right)
    left_relations, right_relations = relation_signatures(left), relation_signatures(right)
    left_names = {entity["name"] for entity in left["entities"] if entity["name"]}
    right_names = {entity["name"] for entity in right["entities"] if entity["name"]}
    left_negations, right_negations = negation_signatures(left), negation_signatures(right)
    entity_common = len(left_entities & right_entities)
    relation_common = len(left_relations & right_relations)
    return {
        "source_query_id": source_query_id,
        "anchor_variant_id": anchor["variant_id"],
        "variant_id": variant["variant_id"],
        "variant_kind": variant["variant_kind"],
        "entities_anchor": len(left_entities), "entities_variant": len(right_entities), "entities_common": entity_common,
        "entity_jaccard": jaccard(left_entities, right_entities),
        "entities_omitted": sorted(signature_text(value) for value in left_entities - right_entities),
        "entities_added": sorted(signature_text(value) for value in right_entities - left_entities),
        "toponyms_anchor": sorted(left_names), "toponyms_variant": sorted(right_names), "toponyms_preserved": sorted(left_names & right_names),
        "relations_anchor": len(left_relations), "relations_variant": len(right_relations), "relations_common": relation_common,
        "relation_jaccard": jaccard(left_relations, right_relations),
        "negations_anchor": len(left_negations), "negations_variant": len(right_negations), "negations_common": len(left_negations & right_negations),
        "orientation_changed": orientation_signature(left) != orientation_signature(right),
        "potential_contradictions": potential_contradictions(left, right),
        "anchor_warning_count": sum(issue_row["severity"] == "warning" for issue_row in anchor["validation"]["issues"]),
        "variant_warning_count": sum(issue_row["severity"] == "warning" for issue_row in variant["validation"]["issues"]),
        "anchor_duration_ms": anchor["duration_ms"], "variant_duration_ms": variant["duration_ms"],
    }


def entity_signatures(extraction: Mapping[str, Any]) -> set[tuple[str, str | None, bool]]:
    return {(entity["type"], normalize_value(entity["name"]) if entity["name"] else None, entity["negated"]) for entity in extraction["entities"]}


def relation_signatures(extraction: Mapping[str, Any]) -> set[tuple[Any, ...]]:
    entities = {entity["entity_id"]: (entity["type"], normalize_value(entity["name"]) if entity["name"] else None, entity["negated"]) for entity in extraction["entities"]}
    def ref(value: str): return ("observer",) if value == "observer" else entities.get(value, ("unknown", value))
    return {(ref(relation["subject"]), relation["predicate"], tuple(ref(value) for value in relation["object_ids"]), relation["negated"], relation["reference_frame"]) for relation in extraction["relations"]}


def negation_signatures(extraction: Mapping[str, Any]) -> set[tuple[str, str]]:
    entities = {entity["entity_id"]: signature_text((entity["type"], normalize_value(entity["name"]) if entity["name"] else None, entity["negated"])) for entity in extraction["entities"]}
    relations = {relation["relation_id"]: relation["predicate"] for relation in extraction["relations"]}
    attributes = {attribute["attribute_id"]: f"{attribute['key']}={attribute['value']}" for entity in extraction["entities"] for attribute in entity["attributes"]}
    maps = {"entity": entities, "relation": relations, "attribute": attributes}
    return {(row["target_kind"], maps[row["target_kind"]].get(row["target_id"], row["target_id"])) for row in extraction["negations"]}


def orientation_signature(extraction: Mapping[str, Any]) -> tuple[Any, ...]:
    value = extraction["observer_orientation"]
    return value["status"], value["cardinal"], value["bearing_degrees"], value["reference_frame"]


def potential_contradictions(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    opposite = {"north_of": "south_of", "south_of": "north_of", "east_of": "west_of", "west_of": "east_of", "left_of_observer": "right_of_observer", "right_of_observer": "left_of_observer", "in_front_of": "behind", "behind": "in_front_of"}
    left_predicates = {relation["predicate"] for relation in left["relations"]}
    right_predicates = {relation["predicate"] for relation in right["relations"]}
    rows = [f"{value}_vs_{opposite[value]}" for value in sorted(left_predicates) if opposite.get(value) in right_predicates]
    left_entities = {(entity["type"], normalize_value(entity["name"]) if entity["name"] else None): entity["negated"] for entity in left["entities"]}
    right_entities = {(entity["type"], normalize_value(entity["name"]) if entity["name"] else None): entity["negated"] for entity in right["entities"]}
    rows.extend(f"entity_negation_changed:{key[0]}:{key[1]}" for key in sorted(set(left_entities) & set(right_entities), key=str) if left_entities[key] != right_entities[key])
    return rows


def extraction_comparison_id(document: Mapping[str, Any]) -> str:
    identity = {key: document[key] for key in ("contract_version", "extraction_set_id", "extraction_set_sha256", "comparisons", "accuracy_available", "limitations")}
    return COMPARISON_PREFIX + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def normalize_value(value: str) -> str: return " ".join(value.casefold().split())
def signature_text(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def jaccard(left: set[Any], right: set[Any]) -> float: return len(left & right) / len(left | right) if left or right else 1.0


def validation_result(structural: bool, semantic: bool, issues: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    return {"structurally_valid": structural, "semantically_valid": semantic, "human_review_required": True, "issues": [dict(row) for row in issues]}


def issue(code: str, severity: str, message: str) -> dict[str, str]: return {"code": code, "severity": severity, "message": message}
def sha256_text(value: str) -> str: return hashlib.sha256(value.encode()).hexdigest()
def canonical_bytes(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
