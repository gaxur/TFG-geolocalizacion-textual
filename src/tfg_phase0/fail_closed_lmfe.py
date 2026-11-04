"""Verificación fail-closed sobre LMFE usando la decodificación final real."""

from __future__ import annotations

from typing import Any, Callable, Iterable


class FailClosedGuidanceError(RuntimeError):
    pass


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
    ):
        self.tokenizer = tokenizer
        self.parser_factory = parser_factory
        self.lmfe_prefix = lmfe_prefix
        self.eos_token_ids = frozenset(int(token_id) for token_id in eos_token_ids)
        self.verified_token_ids = frozenset(int(token_id) for token_id in verified_token_ids)
        self.prompt_lengths: dict[int, int] = {}

    def _decode(self, token_ids: list[int]) -> str:
        return self.tokenizer.decode(token_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)

    def _replay(self, token_ids: list[int]):
        return replay_decoded_prefix(self.parser_factory, self._decode(token_ids))

    def __call__(self, batch_id: int, sent) -> list[int]:
        sequence = sent.tolist()
        if batch_id not in self.prompt_lengths:
            self.prompt_lengths[batch_id] = len(sequence)
        generated = sequence[self.prompt_lengths[batch_id]:]
        parser = self._replay(generated)
        allowed = []
        for token_id in self.lmfe_prefix(batch_id, sent):
            token_id = int(token_id)
            if token_id in self.eos_token_ids:
                if parser.can_end():
                    allowed.append(token_id)
                continue
            if token_id in self.verified_token_ids:
                try:
                    self._replay([*generated, token_id])
                except FailClosedGuidanceError:
                    continue
            allowed.append(token_id)
        if not allowed:
            raise FailClosedGuidanceError("ningún token mantiene válida la decodificación final")
        return allowed


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
    return FailClosedPrefixAllowedTokens(
        tokenizer=tokenizer,
        parser_factory=parser_factory,
        lmfe_prefix=lmfe_prefix,
        eos_token_ids=eos_token_ids,
        verified_token_ids=verified,
    )
