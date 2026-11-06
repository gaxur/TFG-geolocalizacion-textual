"""Contratos puros para la rama DialogueVPR ``en_cartographic`` E0-E3."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .f4_evaluation import haversine_m


PROMPT_VERSION = "dialogue-en-cartographic-visibility-v1"
LANGUAGE_POLICY_V1 = "dialogue-language-heuristic-v1"
LANGUAGE_POLICY_V2 = "dialogue-language-evidence-v2"
INPUT_CONTRACT = "dialogue-v3-en-cartographic-frozen-inputs-v1"
QUERY_CONTRACT = "dialogue-v3-en-cartographic-query-construction-v1"
QUERY_BUNDLE_CONTRACT = "dialogue-v3-en-cartographic-query-bundle-v1"
RETRIEVAL_BUNDLE_CONTRACT = "dialogue-v3-en-cartographic-retrieval-bundle-v1"
CONTINUATION_BUNDLE_CONTRACT = "dialogue-v3-en-cartographic-query-continuation-v2"
COMPOSED_BUNDLE_CONTRACT = "dialogue-v3-en-cartographic-query-bundle-v2"
ROUNDS = ("E0", "E1", "E2", "E3")
EXPECTED_TURNS = ((), (1,), (1, 2), (1, 2, 3))
EXPECTED_CLAIMS = ((), ("claim-001",), ("claim-001", "claim-002"), ("claim-001", "claim-002", "claim-003"))
COORDINATE_RE = re.compile(r"(?<![\w.])[+-]?\d{1,3}[.,]\d{3,}(?!\w)")
INTERNAL_ID_RE = re.compile(r"(?:MADP_|candidate[_ -]?id|mapillary|145528217588574|dialogue-session|claim-\d|E[0-3]\b)", re.I)
FORBIDDEN_TOPONYM_RE = re.compile(r"\b(?:Madrid|Plaza Mayor)\b", re.I)
CAPITALIZED_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
GENERIC_CAPITALIZED = {"The", "There", "This", "From", "Around", "Buildings", "Building", "Monument", "Historic", "Church", "Park", "Garden", "Square", "Not", "Unable"}
SPANISH_RE = re.compile(r"\b(?:estoy|plaza|edificios|persona|iglesia|parque|jardín|puede|posición)\b", re.I)
SHARED_LANGUAGE_WORDS = {"plaza", "patio", "hotel", "metro", "monument", "hospital", "central", "local", "area", "bar", "radio", "terrace"}
SPANISH_STRONG_WORDS = {"estoy", "soy", "rodeado", "rodeada", "edificios", "balcones", "persona", "iglesia", "parque", "jardín", "puede", "puedo", "posición", "desde", "ninguna", "ningún", "ver", "veo", "una", "que", "con", "sin"}
ENGLISH_STRONG_WORDS = {"observer", "surrounded", "buildings", "balconies", "visible", "cannot", "unable", "church", "worship", "park", "garden", "square", "historic", "feature", "from", "with", "nearby", "see"}
ENGLISH_PHRASES = ("i am", "there is", "there are", "from the", "surrounded by", "can see", "cannot see", "can't see", "not visible", "in view", "place of worship")
SPANISH_PHRASES = ("estoy en", "la persona", "puede ver", "no puede ver", "desde su posición", "rodeado de", "rodeada de", "lugar de culto")
SQUARE_RE = re.compile(r"\b(?:square|plaza)\b", re.I)
BUILDING_RE = re.compile(r"\bbuildings?\b", re.I)
SURROUND_RE = re.compile(r"\b(?:surrounded by|among|around me|encircled by)\b", re.I)
MONUMENT_RE = re.compile(r"\b(?:monument|historic(?:al)? (?:element|feature|site)|memorial)\b", re.I)
CHURCH_RE = re.compile(r"\b(?:church|place of worship|religious building)\b", re.I)
PARK_RE = re.compile(r"\b(?:park|garden|green space)\b", re.I)
VISIBLE_RE = re.compile(r"\b(?:visible|can see|is seen|in view)\b", re.I)
NOT_VISIBLE_RE = re.compile(r"\b(?:not visible|cannot see|can't see|not in view|unable to see)\b", re.I)
ABSENCE_RE = re.compile(r"\b(?:there (?:is|are) no|no .{0,40} exists?|without any|absent from|none nearby|no .{0,30} in the area)\b", re.I)


class DialogueEnCartographicError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class FrozenRound:
    round_id: str
    source_text: str
    source_sha256: str
    available_turns: tuple[int, ...]
    required_claim_ids: tuple[str, ...]


def load_plan(plan_root: Path) -> tuple[dict[str, Any], dict[str, Any], tuple[FrozenRound, ...]]:
    frozen_path = plan_root / "frozen-inputs.json"
    contract_path = plan_root / "query-construction-contract.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if frozen.get("contract_version") != INPUT_CONTRACT or frozen.get("status") != "FROZEN_BEFORE_NEW_INFERENCE":
        raise DialogueEnCartographicError("inputs congelados incompatibles")
    if contract.get("contract_version") != QUERY_CONTRACT or contract.get("experiment_prompt_version") != PROMPT_VERSION:
        raise DialogueEnCartographicError("contrato de consulta incompatible")
    if sha256_text(contract["prompt_text"]) != contract.get("prompt_sha256"):
        raise DialogueEnCartographicError("hash del prompt divergente")
    description = frozen["description"]
    if sha256_text(description["text"]) != description["sha256"]:
        raise DialogueEnCartographicError("hash de descripción divergente")
    turns = frozen["turns"]
    if len(turns) != 3 or [row["index"] for row in turns] != [1, 2, 3]:
        raise DialogueEnCartographicError("turnos congelados incompatibles")
    for row in turns:
        if sha256_text(row["answer_literal"]) != row["answer_sha256"]:
            raise DialogueEnCartographicError("hash de respuesta divergente")
    source_rows = frozen["round_sources"]
    contract_rows = contract["rounds"]
    if len(source_rows) != 4 or len(contract_rows) != 4:
        raise DialogueEnCartographicError("E0-E3 incompletas")
    rounds = []
    for index, round_id in enumerate(ROUNDS):
        source, spec = source_rows[index], contract_rows[index]
        if source["round"] != round_id or spec["round"] != round_id:
            raise DialogueEnCartographicError("orden E0-E3 inválido")
        available = tuple(source["available_turns"])
        required = tuple(spec["required_claims"])
        if available != EXPECTED_TURNS[index] or required != EXPECTED_CLAIMS[index]:
            raise DialogueEnCartographicError("fuga o pérdida de claims entre rondas")
        if sha256_text(source["text"]) != source["sha256"]:
            raise DialogueEnCartographicError(f"hash de fuente divergente: {round_id}")
        expected_parts = ["[DESCRIPCIÓN ORIGINAL]", description["text"]]
        if available:
            expected_parts.extend(["[ACLARACIONES HUMANAS VALIDADAS]", *(turns[turn - 1]["clarification"] for turn in available)])
        if source["text"] != "\n".join(expected_parts):
            raise DialogueEnCartographicError(f"aislamiento temporal o texto fuente divergente: {round_id}")
        for turn in turns:
            present = turn["clarification"] in source["text"]
            if present != (turn["index"] in available):
                raise DialogueEnCartographicError(f"aislamiento temporal inválido: {round_id}")
        rounds.append(FrozenRound(round_id, source["text"], source["sha256"], available, required))
    controls = frozen.get("controls", {})
    if controls != {
        "answers_reused_literally": True,
        "questions_regenerated": False,
        "future_answers_visible_to_earlier_rounds": False,
        "mapillary_reference_available_to_transformer": False,
        "rankings_available_to_transformer": False,
        "vlm_available_to_transformer": False,
    }:
        raise DialogueEnCartographicError("controles de aislamiento incompatibles")
    return frozen, contract, tuple(rounds)


def build_prompt(prompt_text: str, round_spec: FrozenRound) -> str:
    return f"{prompt_text}\nTexto fuente:\n{round_spec.source_text}"


def _sentences(text: str) -> list[str]:
    return [value.strip() for value in re.split(r"(?<=[.!?;])\s+|\n+", text) if value.strip()]


def _entity_sentences(text: str, pattern: re.Pattern[str]) -> list[str]:
    return [sentence for sentence in _sentences(text) if pattern.search(sentence)]


def _visibility_issue(text: str, pattern: re.Pattern[str], *, negative: bool) -> tuple[bool, list[str]]:
    sentences = _entity_sentences(text, pattern)
    if not sentences:
        return False, []
    if negative:
        valid = [sentence for sentence in sentences if NOT_VISIBLE_RE.search(sentence) and not ABSENCE_RE.search(sentence)]
    else:
        valid = [sentence for sentence in sentences if VISIBLE_RE.search(sentence) and not NOT_VISIBLE_RE.search(sentence)]
    return bool(valid), valid


def detect_language_v1(text: str) -> dict[str, Any]:
    matches=SPANISH_RE.findall(text or "")
    return {"contract_version":LANGUAGE_POLICY_V1,"decision":"es_or_mixed" if matches else "unknown","spanish_evidence":matches,"english_evidence":[],"shared_or_cognate_tokens":[],"fail_closed_pass":not matches}


def detect_language_v2(text: str, *, neutral_spans: Sequence[str] = ()) -> dict[str, Any]:
    normalized=unicodedata.normalize("NFC",text or "")
    masked=normalized
    for span in sorted((value for value in neutral_spans if value),key=len,reverse=True):masked=re.sub(re.escape(unicodedata.normalize("NFC",span))," ",masked,flags=re.I)
    words=re.findall(r"[^\W_]+",masked.casefold(),flags=re.UNICODE)
    shared=sorted({word for word in words if word in SHARED_LANGUAGE_WORDS})
    spanish_words=sorted({word for word in words if word in SPANISH_STRONG_WORDS and word not in SHARED_LANGUAGE_WORDS})
    english_words=sorted({word for word in words if word in ENGLISH_STRONG_WORDS and word not in SHARED_LANGUAGE_WORDS})
    folded=" ".join(words)
    spanish_phrases=[phrase for phrase in SPANISH_PHRASES if phrase in folded]
    english_phrases=[phrase for phrase in ENGLISH_PHRASES if phrase in folded]
    spanish_evidence=[*[f"word:{value}" for value in spanish_words],*[f"phrase:{value}" for value in spanish_phrases]]
    english_evidence=[*[f"word:{value}" for value in english_words],*[f"phrase:{value}" for value in english_phrases]]
    if spanish_evidence and english_evidence:decision="mixed"
    elif spanish_evidence:decision="es"
    elif english_evidence:decision="en"
    else:decision="indeterminate"
    return {"contract_version":LANGUAGE_POLICY_V2,"decision":decision,"english_evidence":english_evidence,"spanish_evidence":spanish_evidence,"shared_or_cognate_tokens":shared,"neutral_spans":list(neutral_spans),"fail_closed_pass":decision=="en"}


def validate_output(round_spec: FrozenRound, output_text: str, *, max_output_characters: int = 2400, max_length_ratio: float = 2.5, language_policy: str = LANGUAGE_POLICY_V2) -> dict[str, Any]:
    text = output_text.strip() if isinstance(output_text, str) else ""
    issues: list[dict[str, Any]] = []
    evidence: dict[str, list[str]] = {}

    def issue(code: str, message: str, claim_id: str | None = None) -> None:
        row = {"code": code, "severity": "error", "message": message}
        if claim_id is not None:
            row["claim_id"] = claim_id
        issues.append(row)

    if not text:
        issue("empty_output", "La salida está vacía.")
    if len(text) > max_output_characters or len(text) > max(1, int(len(round_spec.source_text) * max_length_ratio)):
        issue("excessive_length", "La salida supera el límite congelado.")
    if language_policy==LANGUAGE_POLICY_V1:language=detect_language_v1(text)
    elif language_policy==LANGUAGE_POLICY_V2:language=detect_language_v2(text)
    else:raise DialogueEnCartographicError("política de idioma no soportada")
    if not language["fail_closed_pass"]:
        issue("language_mismatch", f"Idioma no verificable como inglés: {language['decision']}.")
    for code, pattern in (("coordinates_forbidden", COORDINATE_RE), ("internal_id_forbidden", INTERNAL_ID_RE), ("toponym_forbidden", FORBIDDEN_TOPONYM_RE)):
        if pattern.search(text):
            issue(code, "La salida contiene información prohibida o no presente en la fuente.")
    new_names = sorted({value for value in CAPITALIZED_RE.findall(text) if value not in GENERIC_CAPITALIZED})
    if new_names:
        issue("new_proper_name", "La salida introduce nombres propios no presentes: " + ", ".join(new_names))
    square = _entity_sentences(text, SQUARE_RE)
    buildings = [value for value in _entity_sentences(text, BUILDING_RE) if SURROUND_RE.search(value)]
    evidence["square"] = square
    evidence["surrounding_buildings"] = buildings
    if not square:
        issue("square_lost", "No se conserva la plaza.")
    if not buildings:
        issue("surrounding_buildings_lost", "No se conserva que los edificios rodean al observador.")

    required = set(round_spec.required_claim_ids)
    future = set(EXPECTED_CLAIMS[-1]) - required
    monument_ok, monument_evidence = _visibility_issue(text, MONUMENT_RE, negative=False)
    church_ok, church_evidence = _visibility_issue(text, CHURCH_RE, negative=True)
    park_ok, park_evidence = _visibility_issue(text, PARK_RE, negative=True)
    evidence.update({"monument_visibility": monument_evidence, "church_non_visibility": church_evidence, "park_non_visibility": park_evidence})
    checks = (("claim-001", MONUMENT_RE, monument_ok, "monument_visibility_invalid"), ("claim-002", CHURCH_RE, church_ok, "church_visibility_scope_invalid"), ("claim-003", PARK_RE, park_ok, "park_visibility_scope_invalid"))
    for claim_id, pattern, valid, code in checks:
        appears = bool(pattern.search(text))
        if claim_id in required and not valid:
            issue(code, "El claim no conserva entidad, polaridad y alcance de visibilidad.", claim_id)
        if claim_id in future and appears:
            issue("future_claim_leakage", "Aparece un claim de una ronda futura.", claim_id)
    for claim_id, pattern in (("claim-002", CHURCH_RE), ("claim-003", PARK_RE)):
        if claim_id in required and any(ABSENCE_RE.search(sentence) for sentence in _entity_sentences(text, pattern)):
            issue("object_absence_invented", "No visible se convirtió en inexistencia del objeto.", claim_id)
    # La equivalencia semántica nunca se declara automática: un humano debe revisar.
    return {
        "automatic_checks_passed": not issues,
        "human_review_required": True,
        "eligible_for_human_review": not issues,
        "issues": issues,
        "evidence": evidence,
        "language_validation": language,
        "validator_version": "dialogue-en-cartographic-semantic-validator-v2" if language_policy==LANGUAGE_POLICY_V2 else "dialogue-en-cartographic-semantic-validator-v1",
    }


def prepare_query_bundle(plan_root: Path) -> dict[str, Any]:
    frozen, contract, rounds = load_plan(plan_root)
    rows = []
    for spec in rounds:
        prompt = build_prompt(contract["prompt_text"], spec)
        rows.append({
            "round": spec.round_id,
            "source_text": spec.source_text,
            "source_sha256": spec.source_sha256,
            "available_turns": list(spec.available_turns),
            "required_claim_ids": list(spec.required_claim_ids),
            "prompt": prompt,
            "prompt_sha256": sha256_text(prompt),
            "output_text": None,
            "output_sha256": None,
            "automatic_validation": None,
            "review_status": "not_generated",
        })
    return {
        "schema_version": "1.0",
        "contract_version": QUERY_BUNDLE_CONTRACT,
        "status": "PREPARED_NO_INFERENCE",
        "session_id": frozen["session_id"],
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": contract["prompt_sha256"],
        "model": {"model_id": "Qwen/Qwen3-8B", "revision": "b968826d9c46dd6066d109eabc6255188de91218"},
        "generation": {"max_new_tokens": 256, "seed": 0, "do_sample": False, "temperature": 0.0, "enable_thinking": False, "calls": 4, "automatic_retries": 0},
        "rounds": rows,
        "provenance": {"ground_truth_used": False, "rankings_used": False, "mapillary_used": False, "vlm_used": False, "questions_regenerated": False},
    }


def validate_query_bundle(bundle: Mapping[str, Any], *, require_reviewed: bool, require_real: bool) -> None:
    if bundle.get("contract_version") != QUERY_BUNDLE_CONTRACT or bundle.get("prompt_version") != PROMPT_VERSION:
        raise DialogueEnCartographicError("bundle de consultas incompatible")
    rounds = bundle.get("rounds", [])
    if [row.get("round") for row in rounds] != list(ROUNDS):
        raise DialogueEnCartographicError("bundle E0-E3 incompleto")
    if bundle.get("generation") != {"max_new_tokens": 256, "seed": 0, "do_sample": False, "temperature": 0.0, "enable_thinking": False, "calls": 4, "automatic_retries": 0}:
        raise DialogueEnCartographicError("parámetros de generación divergentes")
    forbidden_keys = {"ground_truth", "ground_truth_candidate_id", "reference", "mapillary", "metrics", "literal_metrics", "correct_candidate", "target_candidate_id"}
    if _contains_forbidden_key(bundle, forbidden_keys):
        raise DialogueEnCartographicError("bundle contiene señales de evaluación prohibidas")
    for row in rounds:
        if sha256_text(row["source_text"]) != row["source_sha256"] or sha256_text(row["prompt"]) != row["prompt_sha256"]:
            raise DialogueEnCartographicError("hash de fuente o prompt divergente")
        if require_reviewed:
            if row.get("review_status") != "reviewed" or row.get("output_text") is None or sha256_text(row["output_text"]) != row.get("output_sha256"):
                raise DialogueEnCartographicError("consulta no revisada o hash divergente")
            spec = FrozenRound(row["round"], row["source_text"], row["source_sha256"], tuple(row["available_turns"]), tuple(row["required_claim_ids"]))
            validation = validate_output(spec, row["output_text"])
            if not validation["automatic_checks_passed"]:
                raise DialogueEnCartographicError("consulta revisada no supera controles automáticos")
    if require_real and bundle.get("execution", {}).get("real_model_inference") is not True:
        raise DialogueEnCartographicError("bundle no procede de inferencia real")


def _contains_forbidden_key(value: Any, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).casefold() in forbidden or _contains_forbidden_key(nested, forbidden) for key, nested in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(nested, forbidden) for nested in value)
    return False


def materialize_with_transformer(prepared: Mapping[str, Any], transformer: Any, *, synthetic_fixture: bool) -> dict[str, Any]:
    if prepared.get("status") != "PREPARED_NO_INFERENCE":
        raise DialogueEnCartographicError("materialización requiere bundle preparado")
    rows = []
    calls = 0
    for row in prepared["rounds"]:
        calls += 1
        result = transformer.generate_prompt(row["prompt"], _generation_config())
        validation = validate_output(FrozenRound(row["round"], row["source_text"], row["source_sha256"], tuple(row["available_turns"]), tuple(row["required_claim_ids"])), result.text)
        rows.append({**row, "output_text": result.text, "output_sha256": sha256_text(result.text), "raw_output_sha256": sha256_text(result.raw_output), "duration_ms": result.duration_ms, "automatic_validation": validation, "review_status": "fixture_only" if synthetic_fixture else ("pending" if validation["eligible_for_human_review"] else "rejected")})
        if not validation["automatic_checks_passed"]:
            break
    for row in prepared["rounds"][len(rows):]:
        rows.append({**row, "review_status": "not_attempted_after_failure"})
    return {
        **prepared,
        "status": "SYNTHETIC_FIXTURE_COMPLETE" if synthetic_fixture and calls == 4 else "GENERATED_PENDING_REVIEW" if calls == 4 and all(row["automatic_validation"]["automatic_checks_passed"] for row in rows) else "GENERATION_REJECTED",
        "rounds": rows,
        "execution": {"real_model_inference": not synthetic_fixture, "synthetic_fixture": synthetic_fixture, "calls": calls, "model_loads": 0 if synthetic_fixture else 1, "automatic_retries": 0},
    }


def prepare_continuation_bundle(plan_root: Path, parent_root: Path, e0_review_path: Path | None = None) -> dict[str, Any]:
    prepared=prepare_query_bundle(plan_root);manifest_path=parent_root/"manifest.json";queries_path=parent_root/"queries.json";manifest=json.loads(manifest_path.read_text());parent=json.loads(queries_path.read_text())
    if manifest.get("status")!="committed" or manifest.get("files",{}).get("queries.json")!=sha256_file(queries_path):raise DialogueEnCartographicError("parent manifest o queries divergente")
    if parent.get("status")!="GENERATION_REJECTED" or parent.get("execution")!={"automatic_retries":0,"calls":1,"model_loads":1,"real_model_inference":True,"synthetic_fixture":False}:raise DialogueEnCartographicError("parent histórico incompatible")
    if [row.get("round") for row in parent.get("rounds",[])]!=list(ROUNDS):raise DialogueEnCartographicError("parent E0-E3 incompleto")
    historical=parent["rounds"][0]
    if historical.get("output_sha256")!="3d97a4a1966f36ece2755059f47fc2d946efcbbbbc620420d9b107820627aa11" or sha256_text(historical.get("output_text",""))!=historical.get("output_sha256"):raise DialogueEnCartographicError("E0 histórica divergente")
    if any(row.get("output_text") is not None for row in parent["rounds"][1:]):raise DialogueEnCartographicError("parent contiene outputs duplicados E1-E3")
    e0_spec=FrozenRound(historical["round"],historical["source_text"],historical["source_sha256"],tuple(historical["available_turns"]),tuple(historical["required_claim_ids"]));v2=validate_output(e0_spec,historical["output_text"],language_policy=LANGUAGE_POLICY_V2)
    if not v2["automatic_checks_passed"]:raise DialogueEnCartographicError("E0 histórica no supera validador v2")
    review_reference=None
    if e0_review_path is not None:
        review=json.loads(e0_review_path.read_text())
        if review.get("contract_version")!="dialogue-v3-en-cartographic-human-review-v1" or review.get("round")!="E0" or review.get("status")!="approved" or review.get("decision")!="APPROVED_WITHOUT_CHANGES" or review.get("approved_text")!=historical["output_text"] or review.get("approved_text_sha256")!=historical["output_sha256"] or review.get("text_modified") is not False:raise DialogueEnCartographicError("revisión humana E0 incompatible")
        review_reference={"path":str(e0_review_path),"sha256":sha256_file(e0_review_path),"review_id":review["review_id"],"decision":review["decision"]}
    targets=[]
    for row in prepared["rounds"][1:]:targets.append({**row,"review_status":"not_generated"})
    return {"schema_version":"1.0","contract_version":CONTINUATION_BUNDLE_CONTRACT,"status":"PREPARED_CONTINUATION_NO_INFERENCE","session_id":prepared["session_id"],"prompt_version":prepared["prompt_version"],"prompt_sha256":prepared["prompt_sha256"],"model":prepared["model"],"generation":{"max_new_tokens":256,"seed":0,"do_sample":False,"temperature":0.0,"enable_thinking":False,"target_rounds":["E1","E2","E3"],"maximum_calls":3,"automatic_retries":0},"parent":{"root":str(parent_root),"manifest_sha256":sha256_file(manifest_path),"queries_sha256":sha256_file(queries_path),"authorization_sha256":"16ee2c5d09b4d7dab7635a55a94170b33dd017a011add271fe978d6d6069584f","historical_E0_output_sha256":historical["output_sha256"],"historical_validator_version":"dialogue-en-cartographic-semantic-validator-v1","revalidation":v2,"human_review":review_reference,"regenerate_historical_rounds":False},"rounds":targets,"provenance":prepared["provenance"]}


def materialize_continuation(prepared: Mapping[str,Any],transformer:Any,*,synthetic_fixture:bool)->dict[str,Any]:
    if prepared.get("contract_version")!=CONTINUATION_BUNDLE_CONTRACT or prepared.get("status")!="PREPARED_CONTINUATION_NO_INFERENCE" or [row.get("round") for row in prepared.get("rounds",[])]!=["E1","E2","E3"]:raise DialogueEnCartographicError("continuación preparada incompatible")
    rows=[];calls=0
    for row in prepared["rounds"]:
        calls+=1;result=transformer.generate_prompt(row["prompt"],_generation_config());spec=FrozenRound(row["round"],row["source_text"],row["source_sha256"],tuple(row["available_turns"]),tuple(row["required_claim_ids"]));validation=validate_output(spec,result.text,language_policy=LANGUAGE_POLICY_V2);rows.append({**row,"output_text":result.text,"output_sha256":sha256_text(result.text),"raw_output_sha256":sha256_text(result.raw_output),"duration_ms":result.duration_ms,"automatic_validation":validation,"review_status":"fixture_only" if synthetic_fixture else ("pending" if validation["eligible_for_human_review"] else "rejected")})
        if not validation["automatic_checks_passed"]:break
    for row in prepared["rounds"][len(rows):]:rows.append({**row,"review_status":"not_attempted_after_failure"})
    complete=calls==3 and all(row.get("automatic_validation",{}).get("automatic_checks_passed") for row in rows)
    return {**prepared,"status":"SYNTHETIC_CONTINUATION_COMPLETE" if synthetic_fixture and complete else "GENERATED_CONTINUATION_PENDING_REVIEW" if complete else "CONTINUATION_REJECTED","rounds":rows,"execution":{"real_model_inference":not synthetic_fixture,"synthetic_fixture":synthetic_fixture,"calls":calls,"model_loads":0 if synthetic_fixture else 1,"automatic_retries":0}}


def compose_query_bundle(parent_root:Path,continuation_root:Path,e0_review_path:Path | None=None)->dict[str,Any]:
    parent_manifest=json.loads((parent_root/"manifest.json").read_text());parent=json.loads((parent_root/"queries.json").read_text());continuation_manifest=json.loads((continuation_root/"manifest.json").read_text());continuation=json.loads((continuation_root/"queries.json").read_text())
    if parent_manifest.get("files",{}).get("queries.json")!=sha256_file(parent_root/"queries.json") or continuation_manifest.get("files",{}).get("queries.json")!=sha256_file(continuation_root/"queries.json"):raise DialogueEnCartographicError("lineage de composición divergente")
    if continuation.get("contract_version")!=CONTINUATION_BUNDLE_CONTRACT or continuation.get("status") not in {"GENERATED_CONTINUATION_PENDING_REVIEW","SYNTHETIC_CONTINUATION_COMPLETE"} or [row.get("round") for row in continuation.get("rounds",[])]!=["E1","E2","E3"]:raise DialogueEnCartographicError("continuación incompleta")
    e0=parent["rounds"][0];e0_spec=FrozenRound(e0["round"],e0["source_text"],e0["source_sha256"],tuple(e0["available_turns"]),tuple(e0["required_claim_ids"]));e0_v2=validate_output(e0_spec,e0["output_text"],language_policy=LANGUAGE_POLICY_V2)
    review_reference=None;review_status="pending"
    if e0_review_path is not None:
        review=json.loads(e0_review_path.read_text())
        if review.get("status")!="approved" or review.get("decision")!="APPROVED_WITHOUT_CHANGES" or review.get("approved_text_sha256")!=e0["output_sha256"] or review.get("approved_text")!=e0["output_text"]:raise DialogueEnCartographicError("aprobación E0 incompatible con composición")
        review_reference={"path":str(e0_review_path),"sha256":sha256_file(e0_review_path),"review_id":review["review_id"],"decision":review["decision"]};review_status="reviewed"
    rows=[{**e0,"historical_validation_v1":e0["automatic_validation"],"automatic_validation":e0_v2,"review_status":review_status,"human_review":review_reference,"lineage_segment":"historical-v1"},*[{**row,"lineage_segment":"continuation-v2"} for row in continuation["rounds"]]]
    if [row["round"] for row in rows]!=list(ROUNDS) or len({row["round"] for row in rows})!=4:raise DialogueEnCartographicError("composición E0-E3 inválida")
    return {"schema_version":"1.0","contract_version":COMPOSED_BUNDLE_CONTRACT,"status":"GENERATED_PENDING_HUMAN_REVIEW","session_id":parent["session_id"],"prompt_version":parent["prompt_version"],"prompt_sha256":parent["prompt_sha256"],"model":parent["model"],"rounds":rows,"execution_summary":{"segments":[{"segment":"historical-v1","rounds":["E0"],"model_loads":1,"calls":1},{"segment":"continuation-v2","rounds":["E1","E2","E3"],"model_loads":continuation["execution"]["model_loads"],"calls":continuation["execution"]["calls"]}],"campaign_totals":{"model_loads":1+continuation["execution"]["model_loads"],"calls":1+continuation["execution"]["calls"],"automatic_retries":0,"generations_per_round":1},"single_load_for_all_rounds":False},"lineage":{"parent_manifest_sha256":sha256_file(parent_root/"manifest.json"),"parent_queries_sha256":sha256_file(parent_root/"queries.json"),"continuation_manifest_sha256":sha256_file(continuation_root/"manifest.json"),"continuation_queries_sha256":sha256_file(continuation_root/"queries.json"),"e0_human_review":review_reference},"provenance":parent["provenance"]}


def _generation_config():
    # Import ligero; Qwen solo se carga al construir explícitamente su adaptador.
    from .f5_text_transform import GenerationConfig
    return GenerationConfig(max_new_tokens=256, seed=0, do_sample=False, temperature=0.0, enable_thinking=False)


def audit_clip_tokenization(bundle: Mapping[str, Any], tokenizer: Callable[..., Any]) -> dict[str, Any]:
    validate_query_bundle(bundle, require_reviewed=True, require_real=True)
    rows = []
    for query in bundle["rounds"]:
        text = query["output_text"]
        try:
            full = tokenizer([text], context_length=300, truncate=False)
        except Exception as error:
            raise DialogueEnCartographicError(f"consulta {query['round']} excede contexto CLIP") from error
        truncated = tokenizer([text], context_length=300, truncate=True)
        full_values = _tensor_values(full)
        truncated_values = _tensor_values(truncated)
        if full_values != truncated_values:
            raise DialogueEnCartographicError(f"truncamiento interno detectado: {query['round']}")
        values = full_values[0]
        non_padding = sum(value != 0 for value in values)
        eot = [index for index, value in enumerate(values) if value == 49407]
        if len(eot) != 1:
            raise DialogueEnCartographicError("EOT CLIP ausente o duplicado")
        rows.append({"round": query["round"], "text_sha256": query["output_sha256"], "context_length": 300, "non_padding_tokens_including_sot_eot": non_padding, "eot_position": eot[0], "truncate_false_succeeded": True, "truncate_true_identical": True, "would_truncate": False})
    return {"schema_version": "1.0", "contract_version": "dialogue-v3-en-cartographic-clip-audit-v1", "status": "PASS_NO_TRUNCATION", "context_length": 300, "truncation_side": "right", "model_loaded": False, "rows": rows}


def _tensor_values(value: Any) -> list[list[int]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list) or not value or not all(isinstance(row, list) for row in value):
        raise DialogueEnCartographicError("salida del tokenizer incompatible")
    return [[int(item) for item in row] for row in value]


def validate_exhaustive_ranking(ranking: Mapping[str, Any], *, expected_ids: set[str] | None = None) -> set[str]:
    results = ranking.get("results", [])
    ids = [row.get("candidate_id") for row in results]
    if ranking.get("gallery_id") != "madrid-50m" or len(ids) != 253 or len(set(ids)) != 253:
        raise DialogueEnCartographicError("ranking no exhaustivo o galería incompatible")
    if [row.get("rank") for row in results] != list(range(1, 254)):
        raise DialogueEnCartographicError("orden de ranks inválido")
    scores = [row.get("cosine_similarity") for row in results]
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in scores) or any(scores[index] < scores[index + 1] for index in range(252)):
        raise DialogueEnCartographicError("scores no finitos o desordenados")
    current = set(ids)
    if expected_ids is not None and current != expected_ids:
        raise DialogueEnCartographicError("universo de candidatos divergente")
    return current


def retrieve_query_bundle(bundle: Mapping[str, Any], retriever: Any, clip_audit: Mapping[str, Any], *, real_model_inference: bool) -> dict[str, Any]:
    validate_query_bundle(bundle, require_reviewed=True, require_real=real_model_inference)
    if clip_audit.get("status") != "PASS_NO_TRUNCATION" or [row.get("round") for row in clip_audit.get("rows", [])] != list(ROUNDS):
        raise DialogueEnCartographicError("auditoría CLIP ausente o incompatible")
    if retriever.gallery_id != "madrid-50m" or retriever.gallery_count != 253:
        raise DialogueEnCartographicError("retriever incompatible")
    rankings = []
    universe = None
    for row in bundle["rounds"]:
        ranking = retriever.retrieve_full(query_id=f"{bundle['session_id']}-{row['round']}-en-cartographic", text=row["output_text"], language="en")
        universe = validate_exhaustive_ranking(ranking, expected_ids=universe)
        checkpoint_payload={"round":row["round"],"query_text_sha256":row["output_sha256"],"ranking":ranking}
        rankings.append({"checkpoint_id":"dialogue-en-cartographic-ranking-sha256-"+hashlib.sha256(canonical_bytes(checkpoint_payload)).hexdigest(),**checkpoint_payload})
    return {"schema_version": "1.0", "contract_version": RETRIEVAL_BUNDLE_CONTRACT, "status": "COMMITTED" if real_model_inference else "SYNTHETIC_FIXTURE_ONLY", "session_id": bundle["session_id"], "gallery_id": "madrid-50m", "candidate_count": 253, "real_model_inference": real_model_inference, "scientific_result": real_model_inference, "rankings": rankings, "provenance": {"ground_truth_used": False, "mapillary_used": False, "literal_metrics_used": False, "scores_fused": False, "coordinates_fused": False, "automatic_retries": 0}}


def compare_rankings(left: Mapping[str, Any], right: Mapping[str, Any], *, k: int = 10) -> dict[str, Any]:
    left_results, right_results = left["results"], right["results"]
    left_ids, right_ids = [row["candidate_id"] for row in left_results], [row["candidate_id"] for row in right_results]
    if set(left_ids) != set(right_ids):
        raise DialogueEnCartographicError("comparación con universos distintos")
    left_top, right_top = set(left_ids[:k]), set(right_ids[:k])
    left_rank, right_rank = {value: i + 1 for i, value in enumerate(left_ids)}, {value: i + 1 for i, value in enumerate(right_ids)}
    return {"top_k": k, "intersection": len(left_top & right_top), "jaccard": len(left_top & right_top) / len(left_top | right_top), "changed_candidate_count": sum(left_rank[value] != right_rank[value] for value in left_rank), "spearman_footrule": sum(abs(left_rank[value] - right_rank[value]) for value in left_rank)}


def camera_metrics(ranking: Mapping[str, Any], latitude: float, longitude: float, reference_candidate_id: str) -> dict[str, Any]:
    results = ranking["results"]
    distances = [haversine_m(latitude, longitude, row["latitude"], row["longitude"]) for row in results]
    rank = next(row["rank"] for row in results if row["candidate_id"] == reference_candidate_id)
    minimums = {str(k): min(distances[:k]) for k in (1, 5, 10)}
    return {"top1_error_m": distances[0], "minimum_error_at_k_m": minimums, "geo_recall_at_k": {str(k): {str(t): int(minimums[str(k)] <= t) for t in (25, 50, 100, 500)} for k in (1, 5, 10)}, "reference_candidate_rank": rank, "point_assignment_hit_at_k": {str(k): int(rank <= k) for k in (1, 5, 10)}, "exploratory_point_assignment_only": True, "official_f54_recall": False}


def evaluate_e_vs_r(e_bundle: Mapping[str, Any], r_rankings: Sequence[Mapping[str, Any]], reference: Mapping[str, Any]) -> dict[str, Any]:
    if e_bundle.get("status") != "COMMITTED" or e_bundle.get("real_model_inference") is not True or len(e_bundle.get("rankings", [])) != 4:
        raise DialogueEnCartographicError("rankings E0-E3 no congelados")
    if len(r_rankings) != 4:
        raise DialogueEnCartographicError("rankings R0-R3 incompletos")
    original = reference["coordinates"]["geometry_original_declared"]
    computed = reference["coordinates"]["computed_geometry_mapillary"]
    candidate = reference["spatial_compatibility"]["original_geometry_assignment"]["candidate_id"]
    rows, pairs = [], []
    e_rankings = [row["ranking"] for row in e_bundle["rankings"]]
    universe = None
    for ranking in [*e_rankings, *r_rankings]:
        universe = validate_exhaustive_ranking(ranking, expected_ids=universe)
    for index, (e_ranking, r_ranking) in enumerate(zip(e_rankings, r_rankings)):
        round_id = f"E{index}"
        rows.append({"round": round_id, "geometry": camera_metrics(e_ranking, original["latitude"], original["longitude"], candidate), "computed_geometry": camera_metrics(e_ranking, computed["latitude"], computed["longitude"], candidate)})
        pairs.append({"comparison": f"R{index}_vs_{round_id}", **compare_rankings(r_ranking, e_ranking)})
    transitions = []
    for start, end in ((0, 1), (1, 2), (2, 3), (0, 3)):
        transitions.append({"comparison": f"E{start}_to_E{end}", "delta_top1_error_m": rows[end]["geometry"]["top1_error_m"] - rows[start]["geometry"]["top1_error_m"], **compare_rankings(e_rankings[start], e_rankings[end])})
    return {"schema_version": "1.0", "contract_version": "dialogue-v3-en-cartographic-mapillary-evaluation-v1", "status": "EXPLORATORY_MAPILLARY_CAMERA_REFERENCE", "official_f54_ground_truth": False, "human_observer_ground_truth": False, "single_query_descriptive_only": True, "rows": rows, "paired_literal_comparisons": pairs, "transitions": transitions}
