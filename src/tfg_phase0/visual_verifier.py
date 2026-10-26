"""Interfaz desacoplada para verificadores visuales locales de distinta capacidad."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class VisualVerifierConfig:
    model_id: str
    revision: str
    model_path: Path
    weight_sha256: str
    dtype: str = "bfloat16"
    attention: str = "sdpa"
    decision_prompt_version: str = "visual-verdict-only-v4"
    explanation_prompt_version: str = "visual-explanation-v4"


class VisualVerifier(Protocol):
    @property
    def metadata(self) -> Mapping[str, Any]: ...
    def decide(self, *, claim: Mapping[str, Any], image_path: Path) -> Mapping[str, Any]: ...
    def explain(self, *, claim: Mapping[str, Any], image_path: Path, verdict: str) -> Mapping[str, Any]: ...
    def close(self) -> None: ...


SUPPORTED_LOCAL_MODELS = {
    "qwen3-vl-2b": {
        "model_id": "Qwen/Qwen3-VL-2B-Instruct",
        "revision": "89644892e4d85e24eaac8bacfd4f463576704203",
        "weight_sha256": "7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0",
        "status": "validated_development_verdict_only",
    },
    "qwen3-vl-8b": {
        "model_id": "Qwen/Qwen3-VL-8B-Instruct",
        "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        "weight_sha256": ["d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa", "8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5", "83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192", "0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5"],
        "status": "diagnostic_completed_no_improvement_over_2b",
    },
}
