"""Adaptador host CPU para transferencia zero-shot del DQ-Pilot oficial."""
from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

SYSTEM_PROMPT = """You are an expert visual detective. Your entire response MUST strictly follow this XML structure:
1.  First, provide your step-by-step reasoning within a `<think>` tag. This reasoning must be grounded in the visual evidence from the images.
2.  Second, provide the final, single best question within a `<question>` tag.
"""

INSTRUCTIONS = (
    """You are an expert visual detective. Your goal is to ask a strategic question to pinpoint a target location.
Based on the dialogue so far and the current set of candidate images, formulate the single best question to ask next.
Focus on a visual detail that is likely to differentiate the candidates and refine the search.""",
    """As a visual inquiry specialist, continue the dialogue to identify a specific place.
Analyze the visual variations among the current candidate images and ask one clear, concise question that narrows the possibilities.""",
    """You are assisting a visual place-search task. Examine the latest candidate images and conversation.
Ask the next logical question that best distinguishes the remaining candidates.""",
)

TEMPORARY = re.compile(
    r"\b(persona|personas|peatón|peatones|coche|coches|vehículo|vehículos|autobús|moto|bicicleta|sombra|sombras|iluminación|clima|lluvia|obra|andamio|people|person|pedestrian|car|vehicle|bus|motorcycle|bicycle|shadow|lighting|weather|rain|scaffold)\b",
    re.I,
)
INTERNAL = re.compile(
    r"\b(imagen|imágenes|foto|fotografía|cámara|candidato|ranking|rank|score|alias|mapillary|candidate place|image|photo|picture|camera)\b",
    re.I,
)


class DQPilotHostError(ValueError):
    def __init__(self, reasons: Sequence[str]):
        self.reasons = tuple(sorted(set(reasons)))
        super().__init__("dq_pilot_host:" + ",".join(self.reasons))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_instruction(seed: int = 42) -> tuple[int, str]:
    generator = random.Random(seed)
    index = generator.randrange(len(INSTRUCTIONS))
    return index, INSTRUCTIONS[index]


def build_native_messages(*, image_refs: Sequence[str], dialogue_history: str, seed: int = 42) -> dict[str, Any]:
    if list(image_refs) != ["I1", "I2", "I3", "I4"]:
        raise DQPilotHostError(["request:image_order_invalid"])
    if not dialogue_history.strip():
        raise DQPilotHostError(["request:history_empty"])
    instruction_index, instruction = select_instruction(seed)
    content: list[dict[str, str]] = [{"type": "text", "text": instruction}]
    for position, image_ref in enumerate(image_refs, 1):
        content.append({"type": "text", "text": f"Candidate Place {position}:\n"})
        content.append({"type": "image", "image_ref": image_ref})
    content.append({"type": "text", "text": f"\nDialogue History:\n{dialogue_history.strip()}"})
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
    return {
        "messages": messages,
        "instruction_index": instruction_index,
        "instruction_sha256": sha256_text(instruction),
        "system_prompt_sha256": sha256_text(SYSTEM_PROMPT),
        "seed": seed,
    }


def parse_native_output(raw: str) -> dict[str, str]:
    full = re.fullmatch(r"\s*<think>(.*?)</think>\s*<question>(.*?)</question>\s*", raw, re.DOTALL)
    if not full:
        raise DQPilotHostError(["native_output:format_invalid"])
    reasoning = full.group(1).strip()
    question = " ".join(full.group(2).split())
    if not reasoning:
        raise DQPilotHostError(["native_output:reasoning_empty"])
    if not question:
        raise DQPilotHostError(["native_output:question_empty"])
    return {"reasoning_internal": reasoning, "question": question}


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(char for char in normalized if not unicodedata.combining(char)).split())


def validate_native_question(
    raw: str,
    *,
    history_questions: Sequence[str],
    outcome_schema: Mapping[str, Any],
) -> dict[str, Any]:
    parsed = parse_native_output(raw)
    question = parsed["question"]
    reasons = []
    if not question.endswith("?") or question.count("?") != 1:
        reasons.append("question:not_single_complete")
    if TEMPORARY.search(question):
        reasons.append("question:temporary")
    if INTERNAL.search(question):
        reasons.append("question:internal_reference")
    if any(_fold(question) == _fold(previous) for previous in history_questions):
        reasons.append("question:redundant")
    if reasons:
        raise DQPilotHostError(reasons)
    outcome = {
        "schema_version": "1.0",
        "contract_version": "dq-pilot-host-outcome-v1",
        "action": "ASK",
        "reason": "NONE",
        "decision_source": "dq_pilot_native_question",
        "native_stop_supported": False,
        "native_output_sha256": sha256_text(raw),
        "candidate_refs": ["C1", "C2", "C3", "C4"],
        "image_refs": ["I1", "I2", "I3", "I4"],
        "native_question": question,
        "public_question": question,
        "semantic_review_required": True,
        "perceptual_review_required": True,
        "automatic_approval": False,
    }
    errors = list(Draft202012Validator(outcome_schema).iter_errors(outcome))
    if errors:
        raise DQPilotHostError(["outcome_schema:" + errors[0].message])
    return {**outcome, "reasoning_internal": parsed["reasoning_internal"], "reasoning_public": False}


def host_terminal(*, action: str, reason: str, native_raw: str | None, outcome_schema: Mapping[str, Any]) -> dict[str, Any]:
    if action not in {"STOP", "ABSTAIN"}:
        raise DQPilotHostError(["terminal:action_invalid"])
    outcome = {
        "schema_version": "1.0",
        "contract_version": "dq-pilot-host-outcome-v1",
        "action": action,
        "reason": reason,
        "decision_source": "atlas_pre_inference_gate" if action == "STOP" else "atlas_post_inference_gate",
        "native_stop_supported": False,
        "native_output_sha256": sha256_text(native_raw) if native_raw is not None else None,
        "candidate_refs": [],
        "image_refs": [],
        "native_question": "",
        "public_question": "",
        "semantic_review_required": False,
        "perceptual_review_required": False,
        "automatic_approval": False,
    }
    errors = list(Draft202012Validator(outcome_schema).iter_errors(outcome))
    if errors:
        raise DQPilotHostError(["outcome_schema:" + errors[0].message])
    return outcome


def canonical_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
