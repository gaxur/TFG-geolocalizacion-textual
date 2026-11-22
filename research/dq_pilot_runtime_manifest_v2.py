"""Normalización estricta y dependency-free de manifests runtime DQ-Pilot."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

SOURCE_V9 = "dq-pilot9-arm64-runtime-v1"
SOURCE_V14 = "dq-pilot14-gb10-runtime-v1"
NORMALIZED_CONTRACT = "dq-pilot-runtime-manifest-v2"
SHA256 = re.compile(r"[0-9a-f]{64}")


class RuntimeManifestContractError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeVersions:
    python: str
    torch: str
    torchvision: str
    cuda_build: str
    transformers: str
    tokenizers: str
    safetensors: str
    pillow: str
    numpy: str
    psutil: str
    accelerate: str


@dataclass(frozen=True)
class RuntimeManifestSpec:
    contract_version: str
    source_contract_version: str
    source_sha256: str
    status: str
    architecture: str
    device: str
    compute_capability: tuple[int, int]
    unified_memory: bool
    versions: RuntimeVersions
    model_id: str
    revision: str
    checkpoint_root: str
    checkpoint_manifest_sha256: str
    model_architecture: str
    parameter_count: int
    dtype: str
    attention: str
    device_map: Mapping[str, str]
    quantization: bool
    lora: bool
    flash_attention_added: bool
    generation: Mapping[str, Any]
    launch_requires_authorization: bool

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "contract_version": self.contract_version,
            "source_contract_version": self.source_contract_version,
            "source_sha256": self.source_sha256,
            "status": self.status,
            "platform": {"architecture": self.architecture, "device": self.device, "compute_capability": list(self.compute_capability), "unified_memory": self.unified_memory},
            "versions": {
                "python": self.versions.python, "torch": self.versions.torch,
                "torchvision": self.versions.torchvision, "cuda_build": self.versions.cuda_build,
                "transformers": self.versions.transformers, "tokenizers": self.versions.tokenizers,
                "safetensors": self.versions.safetensors, "Pillow": self.versions.pillow,
                "numpy": self.versions.numpy, "psutil": self.versions.psutil,
                "accelerate": self.versions.accelerate,
            },
            "model": {
                "model_id": self.model_id, "revision": self.revision,
                "checkpoint_root": self.checkpoint_root,
                "checkpoint_manifest_sha256": self.checkpoint_manifest_sha256,
                "architecture": self.model_architecture, "parameter_count": self.parameter_count,
                "dtype": self.dtype, "attention": self.attention,
                "device_map": dict(self.device_map), "quantization": self.quantization,
                "lora": self.lora, "flash_attention_added": self.flash_attention_added,
            },
            "generation": dict(self.generation),
            "permissions": {"launch_requires_separate_authorization": self.launch_requires_authorization},
        }


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _exact_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeManifestContractError(f"{label} debe ser objeto")
    if set(value) != expected:
        raise RuntimeManifestContractError(f"campos {label} incompatibles: {sorted(set(value) ^ expected)}")
    return value


def _string(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise RuntimeManifestContractError(f"{label} debe ser string no vacío")
    return value


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise RuntimeManifestContractError(f"{label} debe ser boolean")
    return value


def _integer(value: Any, label: str) -> int:
    if type(value) is not int:
        raise RuntimeManifestContractError(f"{label} debe ser integer")
    return value


def _sha(value: Any, label: str) -> str:
    text = _string(value, label)
    if not SHA256.fullmatch(text):
        raise RuntimeManifestContractError(f"{label} no es SHA-256")
    return text


def normalize_runtime_versions(document: Mapping[str, Any]) -> RuntimeVersions:
    contract = document.get("contract_version")
    if contract == SOURCE_V9:
        if "software" in document:
            raise RuntimeManifestContractError("manifest v9 ambiguo: software prohibido")
        raw = _exact_keys(document.get("versions"), {"torch", "torchvision", "cuda_build", "transformers", "tokenizers", "safetensors", "Pillow", "numpy", "psutil", "accelerate"}, "versions")
        python = _string(document.get("python", {}).get("version") if isinstance(document.get("python"), Mapping) else None, "python.version")
        return RuntimeVersions(python, *(_string(raw[key], f"versions.{key}") for key in ("torch", "torchvision", "cuda_build", "transformers", "tokenizers", "safetensors", "Pillow", "numpy", "psutil", "accelerate")))
    if contract == SOURCE_V14:
        if "versions" in document:
            raise RuntimeManifestContractError("manifest v14 ambiguo: versions prohibido")
        raw = _exact_keys(document.get("software"), {"python", "torch", "cuda_build", "transformers_effective", "transformers_checkpoint_declared", "transformers_official_release", "scientific_equivalence_claimed"}, "software")
        if _boolean(raw["scientific_equivalence_claimed"], "software.scientific_equivalence_claimed") is not False:
            raise RuntimeManifestContractError("equivalencia Transformers no puede afirmarse")
        # DQ-PILOT.14 omite versiones auxiliares; se heredan únicamente del perfil histórico v9 fijado.
        return RuntimeVersions(
            _string(raw["python"], "software.python"), _string(raw["torch"], "software.torch"),
            "0.26.0+cu130", _string(raw["cuda_build"], "software.cuda_build"),
            _string(raw["transformers_effective"], "software.transformers_effective"),
            "0.22.2", "0.7.0", "12.2.0", "2.3.5", "7.0.0", "1.13.0",
        )
    raise RuntimeManifestContractError(f"contract_version no soportado: {contract!r}")


def normalize_runtime_manifest(document: Mapping[str, Any], *, source_bytes: bytes | None = None) -> RuntimeManifestSpec:
    if document.get("contract_version") != SOURCE_V14:
        raise RuntimeManifestContractError("solo dq-pilot14-gb10-runtime-v1 es ejecutable")
    top = _exact_keys(document, {"schema_version", "contract_version", "status", "platform", "software", "model", "generation", "resource_policy", "resident_policy", "constraints"}, "runtime")
    if top.get("schema_version") != "1.0" or top.get("contract_version") != SOURCE_V14:
        raise RuntimeManifestContractError("solo dq-pilot14-gb10-runtime-v1 es ejecutable")
    if top.get("status") != "CPU_STATIC_PREPARED_GPU_VALIDATION_PENDING":
        raise RuntimeManifestContractError("status runtime no preparado")
    platform_value = _exact_keys(top["platform"], {"architecture", "device", "compute_capability_observed", "unified_memory"}, "platform")
    capability = platform_value["compute_capability_observed"]
    if not isinstance(capability, list) or len(capability) != 2 or any(type(item) is not int for item in capability):
        raise RuntimeManifestContractError("compute_capability inválida")
    model = _exact_keys(top["model"], {"model_id", "revision", "checkpoint_root", "checkpoint_manifest_sha256", "architecture", "parameter_count", "dtype", "attention", "device_map", "quantization", "lora", "flash_attention_added"}, "model")
    generation = _exact_keys(top["generation"], {"do_sample", "num_beams", "max_new_tokens", "repetition_penalty", "eos_token_ids", "pad_token_id", "use_cache", "automatic_retries", "fallbacks"}, "generation")
    expected_generation = {"do_sample": False, "num_beams": 1, "max_new_tokens": 1024, "repetition_penalty": 1.05, "eos_token_ids": [151645, 151643], "pad_token_id": 151643, "use_cache": True, "automatic_retries": 0, "fallbacks": 0}
    if generation != expected_generation or any(type(generation[key]) is not int for key in ("num_beams", "max_new_tokens", "pad_token_id", "automatic_retries", "fallbacks")):
        raise RuntimeManifestContractError("generation incompatible o con tipos ambiguos")
    constraints = _exact_keys(top["constraints"], {"gpu_permitted", "generation_permitted", "h33_permitted", "network_permitted", "downloads_permitted", "training_permitted"}, "constraints")
    if any(_boolean(value, f"constraints.{key}") for key, value in constraints.items()):
        raise RuntimeManifestContractError("runtime base debe permanecer no autorizado")
    device_map = _exact_keys(model["device_map"], {""}, "model.device_map")
    if device_map != {"": "cuda:0"}:
        raise RuntimeManifestContractError("device_map incompatible")
    versions = normalize_runtime_versions(top)
    raw = source_bytes if source_bytes is not None else _canonical(document)
    spec = RuntimeManifestSpec(
        NORMALIZED_CONTRACT, SOURCE_V14, hashlib.sha256(raw).hexdigest(), _string(top["status"], "status"),
        _string(platform_value["architecture"], "platform.architecture"), _string(platform_value["device"], "platform.device"),
        (capability[0], capability[1]), _boolean(platform_value["unified_memory"], "platform.unified_memory"), versions,
        _string(model["model_id"], "model.model_id"), _string(model["revision"], "model.revision"),
        _string(model["checkpoint_root"], "model.checkpoint_root"), _sha(model["checkpoint_manifest_sha256"], "model.checkpoint_manifest_sha256"),
        _string(model["architecture"], "model.architecture"), _integer(model["parameter_count"], "model.parameter_count"),
        _string(model["dtype"], "model.dtype"), _string(model["attention"], "model.attention"), MappingProxyType(dict(device_map)),
        _boolean(model["quantization"], "model.quantization"), _boolean(model["lora"], "model.lora"),
        _boolean(model["flash_attention_added"], "model.flash_attention_added"), MappingProxyType(dict(generation)), True,
    )
    if (spec.architecture, spec.device, spec.compute_capability, spec.model_id, spec.revision, spec.model_architecture, spec.parameter_count, spec.dtype, spec.attention, spec.quantization, spec.lora, spec.flash_attention_added) != ("aarch64", "NVIDIA GB10", (12, 1), "graysonggg/dlgpr", "cf5c7b8a79ce055a83706fcbe0b94edf31b1cb40", "Qwen2_5_VLForConditionalGeneration", 8292166656, "bfloat16", "sdpa", False, False, False):
        raise RuntimeManifestContractError("identidad GB10/modelo incompatible")
    return spec


def load_runtime_manifest(path: Path) -> RuntimeManifestSpec:
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeManifestContractError("runtime JSON inválido") from error
    return normalize_runtime_manifest(document, source_bytes=raw)
