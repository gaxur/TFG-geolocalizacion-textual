"""Integración XGrammar para JSON Schema con Qwen/Transformers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


EXPECTED_QWEN3_VL_TEXT_VOCAB_SIZE = 151936
EXPECTED_QWEN3_VL_EOS_TOKEN_IDS = (151645, 151643)


def resolve_text_vocab_size(config, *, expected: int = EXPECTED_QWEN3_VL_TEXT_VOCAB_SIZE) -> int:
    text_config = getattr(config, "text_config", None)
    if text_config is None:
        raise ValueError("configuración Qwen3-VL sin text_config")
    if not hasattr(text_config, "vocab_size"):
        raise ValueError("text_config sin vocab_size")
    vocab_size = text_config.vocab_size
    if isinstance(vocab_size, bool) or not isinstance(vocab_size, int) or vocab_size <= 0:
        raise ValueError("text_config.vocab_size debe ser un entero positivo")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
        raise ValueError("vocabulario esperado inválido")
    if vocab_size != expected:
        raise ValueError(f"vocabulario textual incompatible: {vocab_size} != {expected}")
    return vocab_size


@dataclass(frozen=True)
class XGrammarProfile:
    tokenizer_info: Any
    compiler: Any
    vocab_size: int
    stop_token_ids: tuple[int, ...]


def build_xgrammar_profile(*, tokenizer, vocab_size: int, stop_token_ids: Iterable[int]) -> XGrammarProfile:
    import xgrammar as xgr
    stops=tuple(sorted({int(token_id) for token_id in stop_token_ids}))
    if not stops:
        raise ValueError("XGrammar requiere al menos un stop token")
    info=xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=vocab_size,stop_token_ids=list(stops))
    return XGrammarProfile(info,xgr.GrammarCompiler(info,max_threads=8,cache_enabled=True),vocab_size,stops)


def compile_json_schema(profile: XGrammarProfile, schema: dict):
    return profile.compiler.compile_json_schema(schema,strict_mode=True)


def build_transformers_logits_processor(compiled_grammar):
    import xgrammar as xgr
    return xgr.contrib.hf.LogitsProcessor(compiled_grammar)
