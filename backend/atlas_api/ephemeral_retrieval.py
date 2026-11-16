"""Lazy CT2L and Qwen providers backed by one-shot child processes."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Sequence
import urllib.request

from src.tfg_phase0.crosstext2loc_runtime import GalleryNotLoadedError, RetrievalInputError
from src.tfg_phase0.f5_text_transform import (
    GenerationConfig,
    TextTransformationError,
    TransformResult,
    TransformerMetadata,
)

from .settings import ROOT, Settings


WORKER = ROOT / "scripts/run_mvp_ephemeral_retrieval_worker.py"
QWEN_MODEL_ID = "Qwen/Qwen3-8B"
QWEN_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


class EphemeralProviderError(RuntimeError):
    """A child failed without exposing its command, paths, or diagnostics."""


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _host_sample() -> dict[str, Any]:
    memory = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        memory[key] = int(raw.strip().split()[0]) * 1024
    wanted = {"pswpin", "pswpout", "pgmajfault", "pgscan_direct", "pgsteal_direct", "oom_kill"}
    vmstat = {
        key: int(value)
        for key, value in (line.split() for line in Path("/proc/vmstat").read_text(encoding="utf-8").splitlines())
        if key in wanted
    }
    psi = {}
    for line in Path("/proc/pressure/memory").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        psi[parts[0]] = float(dict(item.split("=", 1) for item in parts[1:])["avg10"])
    gpu = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False)
    processes = [line.strip() for line in gpu.stdout.splitlines() if line.strip()] if gpu.returncode == 0 else ["NOT_VERIFIED"]
    return {"available": memory["MemAvailable"], "vmstat": vmstat, "psi": psi, "gpu": processes}


def _default_resource_probe(ollama_ps_url: str | None) -> dict[str, Any]:
    samples = []
    for index in range(5):
        samples.append(_host_sample())
        if index < 4:
            time.sleep(2)
    first, last = samples[0], samples[-1]
    deltas = {key: last["vmstat"][key] - first["vmstat"][key] for key in first["vmstat"]}
    blocking_deltas = {key: value for key, value in deltas.items() if key != "pgmajfault" and value}
    if not ollama_ps_url:
        ollama: list[dict[str, Any]] = [{"status": "NOT_VERIFIED"}]
    else:
        try:
            with urllib.request.urlopen(ollama_ps_url, timeout=3) as response:
                ollama = json.loads(response.read()).get("models", [])
        except Exception as error:
            ollama = [{"status": "NOT_VERIFIED", "error": type(error).__name__}]
    available = [sample["available"] for sample in samples]
    pressure = max(max(sample["psi"].values()) for sample in samples)
    return {
        "available": min(available),
        "available_spread": max(available) - min(available),
        "gpu": [process for sample in samples for process in sample["gpu"]],
        "ollama": ollama,
        "samples": samples,
        "deltas": deltas,
        "blocking_deltas": blocking_deltas,
        "max_memory_psi_avg10": pressure,
    }


class StableSwapV2Gate:
    """One shared, process-safe admission gate for mutually exclusive model loads."""

    def __init__(
        self,
        *,
        ollama_ps_url: str | None = None,
        probe: Callable[[], Mapping[str, Any]] | None = None,
        lock_path: Path = Path(tempfile.gettempdir()) / "atlas-ephemeral-model.lock",
    ):
        self._ollama_ps_url = ollama_ps_url
        self._probe = probe or (lambda: _default_resource_probe(self._ollama_ps_url))
        self._lock_path = lock_path
        self._thread_lock = threading.Lock()

    @contextmanager
    def acquire(self, workspace: Path, label: str):
        with self._thread_lock, self._lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            sample = dict(self._probe())
            passed = (
                int(sample.get("available", 0)) >= 40 * 1024**3
                and int(sample.get("available_spread", 0)) <= 1024**3
                and not sample.get("gpu")
                and not sample.get("ollama")
                and not sample.get("blocking_deltas")
                and float(sample.get("max_memory_psi_avg10", 0.0)) < 0.10
            )
            _atomic_json(
                workspace / "resource-gate.json",
                {
                    "schema_version": "1.0",
                    "contract_version": "atlas-dialogue-stable-swap-v2",
                    "label": label,
                    "sample": sample,
                    "passed": passed,
                },
            )
            if not passed:
                raise EphemeralProviderError("stable-swap-v2 blocked ephemeral inference")
            yield


def _run_child(command: Sequence[str], timeout: int) -> subprocess.CompletedProcess[str]:
    def parent_death_signal() -> None:
        libc = ctypes.CDLL(None)
        if libc.prctl(1, 9) != 0 or os.getppid() == 1:
            os._exit(128 + 9)
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False, preexec_fn=parent_death_signal)


class _ChildProvider:
    def __init__(self, *, gate: StableSwapV2Gate, runner: Callable[[Sequence[str], int], Any] = _run_child):
        self._gate = gate
        self._runner = runner
        self._closed = False

    def _execute(self, operation: str, request: Mapping[str, Any], arguments: Sequence[str], timeout: int) -> dict[str, Any]:
        if self._closed:
            raise EphemeralProviderError("ephemeral provider is closed")
        with tempfile.TemporaryDirectory(prefix=f"atlas-{operation}-") as raw_workspace:
            workspace = Path(raw_workspace)
            request_path = workspace / "request.json"
            output_path = workspace / "output.json"
            _atomic_json(request_path, request)
            command = [sys.executable, str(WORKER), operation, "--request", str(request_path), "--output", str(output_path), *arguments]
            try:
                with self._gate.acquire(workspace, operation):
                    completed = self._runner(command, timeout)
            except EphemeralProviderError:
                raise
            except Exception as error:
                raise EphemeralProviderError(f"ephemeral {operation} failed") from error
            if completed.returncode != 0 or not output_path.is_file():
                raise EphemeralProviderError(f"ephemeral {operation} failed")
            try:
                document = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise EphemeralProviderError(f"ephemeral {operation} returned an invalid response") from error
            if not isinstance(document, dict):
                raise EphemeralProviderError(f"ephemeral {operation} returned an invalid response")
            return document

    def close(self) -> None:
        self._closed = True


class EphemeralCrossText2LocRetriever(_ChildProvider):
    """CT2L-compatible proxy; construction only reads small JSON configuration."""

    ephemeral = True

    def __init__(self, settings: Settings, *, gate: StableSwapV2Gate, runner: Callable[[Sequence[str], int], Any] = _run_child):
        super().__init__(gate=gate, runner=runner)
        self._settings = settings
        try:
            raw = json.loads(settings.runtime_config.read_text(encoding="utf-8"))
            galleries = raw["galleries"]
            self._counts = {
                gallery_id: int(json.loads((ROOT / config["selection"]).read_text(encoding="utf-8"))["candidate_count"])
                for gallery_id, config in galleries.items()
            }
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise EphemeralProviderError("ephemeral retrieval configuration is invalid") from error
        if set(self._counts) != {"madrid-25m", "madrid-50m"}:
            raise EphemeralProviderError("ephemeral retrieval galleries are incompatible")

    @property
    def gallery_ids(self) -> tuple[str, ...]:
        return tuple(self._counts)

    def gallery_count(self, gallery_id: str) -> int:
        if self._closed:
            raise EphemeralProviderError("ephemeral provider is closed")
        try:
            return self._counts[gallery_id]
        except KeyError as error:
            raise GalleryNotLoadedError(f"galería no cargada: {gallery_id}") from error

    def retrieve(self, *, gallery_id: str, query_id: str, text: str, language: str, k: int) -> dict[str, Any]:
        return self.retrieve_many(gallery_ids=(gallery_id,), query_id=query_id, text=text, language=language, k=k)["retrievals"][0]

    def retrieve_many(
        self,
        *,
        gallery_ids: Sequence[str],
        query_id: str,
        text: str,
        language: str,
        k: int,
        progress_callback: Callable[[str, str, float | None, str | None], None] | None = None,
    ) -> dict[str, Any]:
        ids = tuple(gallery_ids)
        if not ids or len(set(ids)) != len(ids) or any(gallery_id not in self._counts for gallery_id in ids):
            raise GalleryNotLoadedError("galería no cargada")
        if not query_id or not text or not language or k < 1 or any(k > self._counts[gallery_id] for gallery_id in ids):
            raise RetrievalInputError("solicitud de recuperación inválida")

        def notify(phase: str, state: str, elapsed: float | None = None, gallery: str | None = None) -> None:
            if progress_callback:
                try:
                    progress_callback(phase, state, elapsed, gallery)
                except Exception:
                    pass

        notify("text_encoding", "running")
        request = {"gallery_ids": list(ids), "query_id": query_id, "text": text, "language": language, "k": k}
        arguments = [
            "--runtime-config", str(self._settings.runtime_config),
            "--region-config", str(self._settings.region_config),
            "--clip", str(self._settings.clip_weights_path),
            "--cvg-utils-sha256", self._settings.cvg_utils_sha256,
        ]
        try:
            result = self._execute("retrieve", request, arguments, 300)
        except Exception:
            notify("text_encoding", "failed")
            raise
        timings = result.get("timings_ms", {})
        notify("text_encoding", "completed", timings.get("text_encoding"))
        for gallery_id in ids:
            notify("ranking", "running", gallery=gallery_id)
            notify("ranking", "completed", timings.get("ranking_by_gallery", {}).get(gallery_id), gallery_id)
        return result


class EphemeralQwenTransformer(_ChildProvider):
    """Qwen TextTransformer proxy with no imports or model residency in the API."""

    def __init__(self, model_path: Path, *, gate: StableSwapV2Gate, model_id: str = QWEN_MODEL_ID, revision: str = QWEN_REVISION, runner: Callable[[Sequence[str], int], Any] = _run_child):
        if not model_path.is_dir():
            raise TextTransformationError("snapshot Qwen local ausente")
        super().__init__(gate=gate, runner=runner)
        self._model_path = model_path
        self._metadata = TransformerMetadata("transformers-qwen3-ephemeral-v1", model_id, revision, model_id, revision, "0" * 64, True)
        self._resource_usage: dict[str, Any] = {"ephemeral": True, "model_resident": False}

    @property
    def metadata(self) -> TransformerMetadata:
        return self._metadata

    @property
    def resource_usage(self) -> Mapping[str, Any]:
        return self._resource_usage

    def transform(self, original_text: str, task: str, protected_toponyms: Sequence[str], config: GenerationConfig) -> TransformResult:
        request = {"original_text": original_text, "task": task, "protected_toponyms": list(protected_toponyms), "generation": asdict(config)}
        try:
            document = self._execute("transform", request, ["--model", str(self._model_path), "--model-id", self._metadata.model_id, "--revision", self._metadata.revision], 360)
            metadata = document["metadata"]
            self._metadata = TransformerMetadata(**metadata)
            self._resource_usage = {**document.get("resource_usage", {}), "ephemeral": True, "model_resident": False}
            return TransformResult(**document["result"])
        except EphemeralProviderError as error:
            raise TextTransformationError("ephemeral Qwen transformation failed") from error
        except (KeyError, TypeError, ValueError) as error:
            raise TextTransformationError("ephemeral Qwen returned an invalid response") from error


_SHARED_GATE = StableSwapV2Gate(ollama_ps_url=os.environ.get("ATLAS_OLLAMA_PS_URL"))


def ephemeral_retriever_factory(settings: Settings) -> EphemeralCrossText2LocRetriever:
    """Factory suitable for ``build_lifespan`` in operational mode."""
    return EphemeralCrossText2LocRetriever(settings, gate=_SHARED_GATE)


def ephemeral_transformer_factory(settings: Settings) -> EphemeralQwenTransformer | None:
    """Factory suitable for ``build_lifespan`` and sharing CT2L admission."""
    if settings.qwen_model_path is None:
        return None
    return EphemeralQwenTransformer(settings.qwen_model_path, gate=_SHARED_GATE, model_id=settings.qwen_model_id, revision=settings.qwen_model_revision)
