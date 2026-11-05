"""Verificación fail-closed sobre LMFE usando la decodificación final real."""

from __future__ import annotations

import time
import re
from typing import Any, Callable, Iterable


class FailClosedGuidanceError(RuntimeError):
    pass


def json_string_field_state(text: str, field: str):
    match=re.search(r'"'+re.escape(field)+r'"\s*:\s*"',text)
    if not match:return None
    count=0;escape=False;unicode_remaining=0
    for character in text[match.end():]:
        if unicode_remaining:
            if character not in "0123456789abcdefABCDEF":raise FailClosedGuidanceError("escape Unicode JSON inválido")
            unicode_remaining-=1
            if not unicode_remaining:count+=1
        elif escape:
            if character=='u':unicode_remaining=4
            elif character in '"\\/bfnrt':count+=1
            else:raise FailClosedGuidanceError("escape JSON inválido")
            escape=False
        elif character=='\\':escape=True
        elif character=='"':return {"count":count,"closed":True,"escape":False,"unicode_remaining":0}
        else:count+=1
    return {"count":count,"closed":False,"escape":escape,"unicode_remaining":unicode_remaining}


def advance_json_string_field_state(state: dict, suffix: str, maximum: int):
    current=dict(state)
    for character in suffix:
        if current["closed"]:break
        if current["unicode_remaining"]:
            if character not in "0123456789abcdefABCDEF":raise FailClosedGuidanceError("escape Unicode JSON inválido")
            current["unicode_remaining"]-=1
            if not current["unicode_remaining"]:current["count"]+=1
        elif current["escape"]:
            if character=='u':current["unicode_remaining"]=4
            elif character in '"\\/bfnrt':current["count"]+=1
            else:raise FailClosedGuidanceError("escape JSON inválido")
            current["escape"]=False
        elif character=='\\':current["escape"]=True
        elif character=='"':current["closed"]=True
        else:current["count"]+=1
        if current["count"]>maximum:raise FailClosedGuidanceError("cadena JSON supera maxLength")
    return current


def json_string_token_within_limit(state: dict, token_text: str, maximum: int):
    if not state["escape"] and not state["unicode_remaining"] and '"' not in token_text and '\\' not in token_text:
        return state["count"]+len(token_text)<=maximum
    try:advance_json_string_field_state(state,token_text,maximum);return True
    except FailClosedGuidanceError:return False


def enforce_json_string_field_limit(text: str, field: str, maximum: int):
    state=json_string_field_state(text,field)
    if state and state["count"]>maximum:raise FailClosedGuidanceError(f"{field} supera maxLength={maximum}")
    return state


def replay_decoded_prefix(parser_factory: Callable[[], Any], text: str):
    parser = parser_factory()
    for index, character in enumerate(text):
        if character not in parser.get_allowed_characters():
            raise FailClosedGuidanceError(f"carácter decodificado no permitido en {index}: {character!r}")
        parser = parser.add_character(character)
    return parser


class FailClosedPrefixAllowedTokens:
    """Filtra candidatos LMFE contra el texto que Transformers decodificará."""

    def __init__(
        self,
        *,
        tokenizer,
        parser_factory: Callable[[], Any],
        lmfe_prefix,
        eos_token_ids: Iterable[int],
        verified_token_ids: Iterable[int] = (),
        token_texts: dict[int,str] | None = None,
        string_field_limits: dict[str,int] | None = None,
    ):
        self.tokenizer = tokenizer
        self.parser_factory = parser_factory
        self.lmfe_prefix = lmfe_prefix
        self.eos_token_ids = frozenset(int(token_id) for token_id in eos_token_ids)
        self.verified_token_ids = frozenset(int(token_id) for token_id in verified_token_ids)
        self.token_texts=token_texts or {};self.string_field_limits=string_field_limits or {}
        self.prompt_lengths: dict[int, int] = {}
        self.states: dict[int, tuple[tuple[int, ...], str, Any]] = {}
        self.metrics = {"calls":0,"total_seconds":0.0,"maximum_seconds":0.0,"candidates_examined":0,"verified_candidates":0,"decode_calls":0,"parser_characters":0}

    def _decode(self, token_ids: list[int]) -> str:
        self.metrics["decode_calls"]+=1
        return self.tokenizer.decode(token_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)

    def _advance(self, parser, text: str):
        for character in text:
            if character not in parser.get_allowed_characters():raise FailClosedGuidanceError(f"carácter decodificado no permitido: {character!r}")
            parser=parser.add_character(character);self.metrics["parser_characters"]+=1
        return parser

    def _state(self,batch_id:int,generated:list[int]):
        token_key=tuple(generated);decoded=self._decode(generated);previous=self.states.get(batch_id)
        if previous and token_key[:len(previous[0])]==previous[0] and decoded.startswith(previous[1]):parser=self._advance(previous[2],decoded[len(previous[1]):])
        else:parser=self._advance(self.parser_factory(),decoded)
        self.states[batch_id]=(token_key,decoded,parser);return decoded,parser

    def __call__(self, batch_id: int, sent) -> list[int]:
        started=time.perf_counter()
        try:
            sequence = sent.tolist()
            if batch_id not in self.prompt_lengths:
                self.prompt_lengths[batch_id] = len(sequence)
            generated = sequence[self.prompt_lengths[batch_id]:]
            decoded,parser = self._state(batch_id,generated)
            field_states={field:enforce_json_string_field_limit(decoded,field,maximum) for field,maximum in self.string_field_limits.items()}
            allowed = []
            candidates=self.lmfe_prefix(batch_id, sent);self.metrics["candidates_examined"]+=len(candidates)
            for token_id in candidates:
                token_id = int(token_id)
                if token_id in self.eos_token_ids:
                    if parser.can_end():allowed.append(token_id)
                    continue
                if token_id in self.verified_token_ids:
                    self.metrics["verified_candidates"]+=1
                    try:
                        candidate_decoded=self._decode([*generated,token_id])
                        if not candidate_decoded.startswith(decoded):raise FailClosedGuidanceError("token altera el prefijo decodificado")
                        self._advance(parser,candidate_decoded[len(decoded):])
                        for field,maximum in self.string_field_limits.items():
                            if field_states[field] and not field_states[field]["closed"] and not json_string_token_within_limit(field_states[field],candidate_decoded[len(decoded):],maximum):raise FailClosedGuidanceError("token supera maxLength")
                    except FailClosedGuidanceError:continue
                elif any(state and not state["closed"] for state in field_states.values()):
                    try:
                        for field,maximum in self.string_field_limits.items():
                            if field_states[field] and not field_states[field]["closed"] and not json_string_token_within_limit(field_states[field],self.token_texts.get(token_id,""),maximum):raise FailClosedGuidanceError("token supera maxLength")
                    except FailClosedGuidanceError:continue
                allowed.append(token_id)
            if not allowed:raise FailClosedGuidanceError("ningún token mantiene válida la decodificación final")
            return allowed
        finally:
            elapsed=time.perf_counter()-started;self.metrics["calls"]+=1;self.metrics["total_seconds"]+=elapsed;self.metrics["maximum_seconds"]=max(self.metrics["maximum_seconds"],elapsed)

    def metrics_snapshot(self):
        calls=self.metrics["calls"];return {**self.metrics,"total_ms":self.metrics["total_seconds"]*1000,"maximum_ms":self.metrics["maximum_seconds"]*1000,"mean_ms":self.metrics["total_seconds"]*1000/calls if calls else 0.0}


def build_fail_closed_transformers_prefix(*, tokenizer, schema: dict, eos_token_ids: Iterable[int]):
    """Construye LMFE con alfabeto coherente y añade controles fail-closed."""
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig
    from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data, build_transformers_prefix_allowed_tokens_fn

    tokenizer_data = build_token_enforcer_tokenizer_data(tokenizer)
    config = CharacterLevelParserConfig(alphabet=tokenizer_data.tokenizer_alphabet)
    parser_factory = lambda: JsonSchemaParser(schema, config=CharacterLevelParserConfig(alphabet=tokenizer_data.tokenizer_alphabet))
    lmfe_prefix = build_transformers_prefix_allowed_tokens_fn(tokenizer_data, JsonSchemaParser(schema, config=config))
    verified = {
        token_id
        for token_id, token_text, _ in tokenizer_data.regular_tokens
        if any(character in token_text for character in "\n\r\t")
        or tokenizer.decode([token_id], skip_special_tokens=True, clean_up_tokenization_spaces=False) != token_text
    }
    token_texts={int(token_id):token_text for token_id,token_text,_ in tokenizer_data.regular_tokens}
    string_limits={name:int(definition["maxLength"]) for name,definition in schema.get("properties",{}).items() if "maxLength" in definition and (definition.get("type")=="string" or "string" in definition.get("type",[]))}
    return FailClosedPrefixAllowedTokens(
        tokenizer=tokenizer,
        parser_factory=parser_factory,
        lmfe_prefix=lmfe_prefix,
        eos_token_ids=eos_token_ids,
        verified_token_ids=verified,
        token_texts=token_texts,
        string_field_limits=string_limits,
    )
