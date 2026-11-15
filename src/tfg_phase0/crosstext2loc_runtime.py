"""Runtime residente de CrossText2Loc para una o varias galerías F4."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from .config import load_region_config
from .f4_preflight import load_verified_selection
from .f4_retrieval import build_retrieval_result, exhaustive_rank, normalize_l2
from .f4_validation import (
    load_verified_f1_catalog,
    validate_embedding_bundle,
    validate_retrieval_result,
    validate_visual_manifest,
    verify_visual_image_files,
)


EXPECTED_CVG_TEXT_COMMIT = "6910d2747a94fbe985309bde60cd4732bcbbf50f"
EXPECTED_CLIP_COMMIT = "dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1"
EXPECTED_CHECKPOINT_NAME = "long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth"
EXPECTED_CHECKPOINT_SIZE = 1_712_649_548
EXPECTED_CHECKPOINT_SHA256 = "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d"
EXPECTED_CLIP_WEIGHTS_NAME = "ViT-L-14-336px.pt"
EXPECTED_CLIP_WEIGHTS_SIZE = 934_088_680
EXPECTED_CLIP_WEIGHTS_SHA256 = "3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02"
MODEL_NAME = "CLIP-L/14@336"
CLIP_ARCHITECTURE = "ViT-L/14@336px"
CONTEXT_LENGTH = 300


class CrossText2LocRuntimeError(RuntimeError):
    pass


class ResourceConfigurationError(CrossText2LocRuntimeError):
    pass


class ResourceIntegrityError(CrossText2LocRuntimeError):
    pass


class ModelCompatibilityError(CrossText2LocRuntimeError):
    pass


class GalleryNotLoadedError(CrossText2LocRuntimeError):
    pass


class RuntimeClosedError(CrossText2LocRuntimeError):
    pass


class InferenceError(CrossText2LocRuntimeError):
    pass


class RetrievalInputError(ValueError):
    pass


class TextEncoder(Protocol):
    checkpoint_sha256: str
    model_name: str

    def encode_text(self, text: str) -> Any: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class ModelConfig:
    checkpoint: Path
    clip_weights: Path
    cvg_text_root: Path
    cvg_utils_sha256: str
    device: str = "cuda"


@dataclass(frozen=True)
class GalleryConfig:
    gallery_id: str
    catalog_manifest: Path
    selection: Path
    visual_bundle: Path
    embedding_bundle: Path


def load_runtime_config(
    path: Path,
    *,
    project_root: Path,
    cvg_utils_sha256: str,
    clip_weights_path: Path,
) -> tuple[ModelConfig, list[GalleryConfig]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise ResourceConfigurationError("no se pudo leer la configuración runtime") from error
    if set(raw) != {"schema_version", "contract_version", "model", "galleries"} or raw["schema_version"] != "1.0" or raw["contract_version"] != "crosstext2loc-runtime-config-v1":
        raise ResourceConfigurationError("configuración runtime incompatible")
    model = raw["model"]
    if not isinstance(model, Mapping) or set(model) != {"checkpoint", "clip_weights", "cvg_text_root", "device"} or model["clip_weights"] != "${CLIP_WEIGHTS_PATH}":
        raise ResourceConfigurationError("configuración de modelo incompatible")
    galleries_raw = raw["galleries"]
    expected_fields = {"catalog_manifest", "selection", "visual_bundle", "embedding_bundle"}
    if not isinstance(galleries_raw, Mapping) or not galleries_raw or any(not isinstance(value, Mapping) or set(value) != expected_fields for value in galleries_raw.values()):
        raise ResourceConfigurationError("configuración de galerías incompatible")
    model_config = ModelConfig(project_root / model["checkpoint"], clip_weights_path, project_root / model["cvg_text_root"], cvg_utils_sha256, model["device"])
    galleries = [GalleryConfig(gallery_id, project_root / value["catalog_manifest"], project_root / value["selection"], project_root / value["visual_bundle"], project_root / value["embedding_bundle"]) for gallery_id, value in galleries_raw.items()]
    return model_config, galleries


@dataclass(frozen=True)
class ResidentGallery:
    gallery_id: str
    catalog: Any
    visual_manifest: Mapping[str, Any]
    embedding_manifest: Mapping[str, Any]
    matrix: Any
    candidate_ids: tuple[str, ...]

    @classmethod
    def load(
        cls,
        config: GalleryConfig,
        *,
        region_config: Path,
        deep_validate_visual_assets: bool = False,
    ) -> "ResidentGallery":
        try:
            catalog = load_verified_f1_catalog(config.catalog_manifest, load_region_config(region_config))
            selection, selection_hash = load_verified_selection(config.selection, catalog)
            visual_raw = (config.visual_bundle / "manifest.json").read_bytes()
            visual = json.loads(visual_raw.decode("utf-8"))
            validate_visual_manifest(visual, catalog, selection=selection, selection_sha256=selection_hash)
            if deep_validate_visual_assets:
                verify_visual_image_files(visual, config.visual_bundle)
            embedding = json.loads((config.embedding_bundle / "manifest.json").read_text(encoding="utf-8"))
            matrix, candidate_ids = validate_embedding_bundle(
                embedding, config.embedding_bundle, visual, visual_raw, catalog
            )
        except Exception as error:
            raise ResourceIntegrityError(f"no se pudo cargar la galería {config.gallery_id}") from error
        return cls(config.gallery_id, catalog, visual, embedding, matrix, candidate_ids)


class OpenAIClipTextEncoder:
    model_name = MODEL_NAME
    checkpoint_sha256 = EXPECTED_CHECKPOINT_SHA256

    def __init__(self, model: Any, clip_module: Any, device: str, cvg_utils_sha256: str):
        self._model = model
        self._clip = clip_module
        self._device = device
        self._lock = threading.Lock()
        self.cvg_utils_sha256 = cvg_utils_sha256
        self.encode_count = 0

    @classmethod
    def load(cls, config: ModelConfig) -> "OpenAIClipTextEncoder":
        model, _, clip = load_model_components(config)
        return cls(model, clip, config.device, config.cvg_utils_sha256)

    def encode_text(self, text: str) -> Any:
        try:
            import torch
            with self._lock:
                tokens = self._clip.tokenize(text, context_length=CONTEXT_LENGTH, truncate=True).to(self._device)
                with torch.inference_mode():
                    feature = self._model.encode_text(tokens).float().cpu().numpy()[0]
                self.encode_count += 1
            return normalize_l2(feature, label="embedding textual")
        except Exception as error:
            raise InferenceError("falló la codificación textual") from error

    def cuda_memory(self) -> dict[str, int | None]:
        try:
            import torch
            if not self._device.startswith("cuda"):
                return {"allocated_bytes": None, "reserved_bytes": None, "max_allocated_bytes": None, "max_reserved_bytes": None}
            return {
                "allocated_bytes": int(torch.cuda.memory_allocated()),
                "reserved_bytes": int(torch.cuda.memory_reserved()),
                "max_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                "max_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            }
        except Exception as error:
            raise InferenceError("no se pudo leer telemetría CUDA") from error

    def close(self) -> None:
        self._model = None
        try:
            import torch
            if self._device.startswith("cuda"):
                torch.cuda.empty_cache()
        except Exception:
            pass


def load_model_components(config: ModelConfig) -> tuple[Any, Any, Any]:
    """Carga explícitamente modelo, preprocess y CLIP; importar no inicializa CUDA."""
    _verify_model_resources(config)
    try:
        import clip
        import torch
        utils_path = config.cvg_text_root / "utils.py"
        spec = importlib.util.spec_from_file_location(f"cvg_text_utils_{config.cvg_utils_sha256}", utils_path)
        if spec is None or spec.loader is None:
            raise ResourceIntegrityError("no se pudo cargar utils.py verificado")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        interpolate_pos_embedding = module.interpolate_pos_embedding

        model, preprocess = clip.load(str(config.clip_weights), device="cpu")
        model = model.float()
        model.positional_embedding = torch.nn.Parameter(
            interpolate_pos_embedding(model.positional_embedding, CONTEXT_LENGTH)
        )
        mask = torch.empty(CONTEXT_LENGTH, CONTEXT_LENGTH)
        mask.fill_(float("-inf"))
        mask.triu_(1)
        for block in model.transformer.resblocks:
            block.attn_mask = mask
        state = torch.load(config.checkpoint, map_location="cpu", weights_only=True)
        incompatible = model.load_state_dict(state, strict=False)
        if incompatible.missing_keys or incompatible.unexpected_keys:
            raise ModelCompatibilityError(f"checkpoint incompatible: {incompatible}")
        model.eval().to(config.device)
        return model, preprocess, clip
    except CrossText2LocRuntimeError:
        raise
    except Exception as error:
        raise ModelCompatibilityError("no se pudo cargar CrossText2Loc") from error


def load_visual_inputs(config: GalleryConfig, *, region_config: Path, deep_validate_visual_assets: bool = True) -> tuple[Any, Mapping[str, Any], bytes]:
    """Carga inputs visuales para generación offline sin crear un runtime residente."""
    try:
        catalog = load_verified_f1_catalog(config.catalog_manifest, load_region_config(region_config))
        selection, selection_hash = load_verified_selection(config.selection, catalog)
        visual_raw = (config.visual_bundle / "manifest.json").read_bytes()
        visual = json.loads(visual_raw.decode("utf-8"))
        validate_visual_manifest(visual, catalog, selection=selection, selection_sha256=selection_hash)
        if deep_validate_visual_assets:
            verify_visual_image_files(visual, config.visual_bundle)
        return catalog, visual, visual_raw
    except Exception as error:
        raise ResourceIntegrityError(f"no se pudieron cargar inputs visuales de {config.gallery_id}") from error


class CrossText2LocRetriever:
    def __init__(self, encoder: TextEncoder, galleries: Sequence[ResidentGallery]):
        if not galleries:
            raise ResourceConfigurationError("se requiere al menos una galería")
        gallery_map = {gallery.gallery_id: gallery for gallery in galleries}
        if len(gallery_map) != len(galleries):
            raise ResourceConfigurationError("gallery_id duplicado")
        for gallery in galleries:
            if gallery.embedding_manifest["checkpoint"]["sha256"] != encoder.checkpoint_sha256:
                raise ModelCompatibilityError("galería y encoder usan checkpoints distintos")
            model = gallery.embedding_manifest["model"]
            if model["name"] != MODEL_NAME or model["architecture"] != CLIP_ARCHITECTURE or model["text_context_length"] != CONTEXT_LENGTH:
                raise ModelCompatibilityError("galería incompatible con el encoder textual")
            encoder_utils = getattr(encoder, "cvg_utils_sha256", None)
            if encoder_utils is not None and model["cvg_utils_sha256"] != encoder_utils:
                raise ModelCompatibilityError("galería y encoder usan utils.py distintos")
        self._encoder = encoder
        self._galleries = gallery_map
        self._closed = False
        self._lifecycle = threading.RLock()

    @classmethod
    def load(
        cls,
        *,
        model_config: ModelConfig,
        gallery_configs: Sequence[GalleryConfig],
        region_config: Path,
        deep_validate_visual_assets: bool = False,
    ) -> "CrossText2LocRetriever":
        encoder = OpenAIClipTextEncoder.load(model_config)
        try:
            galleries = [
                ResidentGallery.load(config, region_config=region_config, deep_validate_visual_assets=deep_validate_visual_assets)
                for config in gallery_configs
            ]
            return cls(encoder, galleries)
        except Exception:
            encoder.close()
            raise

    @property
    def gallery_ids(self) -> tuple[str, ...]:
        return tuple(self._galleries)

    def gallery_count(self, gallery_id: str) -> int:
        self._ensure_open()
        try:
            return len(self._galleries[gallery_id].candidate_ids)
        except KeyError as error:
            raise GalleryNotLoadedError(f"galería no cargada: {gallery_id}") from error

    def retrieve(self, *, gallery_id: str, query_id: str, text: str, language: str, k: int) -> dict[str, Any]:
        return self.retrieve_many(gallery_ids=[gallery_id], query_id=query_id, text=text, language=language, k=k)["retrievals"][0]

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
        with self._lifecycle:
            self._ensure_open()
            ids = _validate_request_values(gallery_ids, query_id, text, language, k)
            galleries = []
            for gallery_id in ids:
                try:
                    gallery = self._galleries[gallery_id]
                except KeyError as error:
                    raise GalleryNotLoadedError(f"galería no cargada: {gallery_id}") from error
                if k > len(gallery.candidate_ids):
                    raise RetrievalInputError(f"top_k excede la galería {gallery_id}")
                galleries.append(gallery)
            started = time.perf_counter()
            encoded_started = time.perf_counter()

            def notify(phase: str, state: str, elapsed_ms: float | None = None, gallery_id: str | None = None) -> None:
                if progress_callback is None:
                    return
                try:
                    progress_callback(phase, state, elapsed_ms, gallery_id)
                except Exception:
                    # Observability must never change retrieval/scoring semantics.
                    return

            notify("text_encoding", "running")
            try:
                text_embedding = self._encoder.encode_text(text)
            except Exception:
                notify("text_encoding", "failed", (time.perf_counter() - encoded_started) * 1000)
                raise
            encoded_at = time.perf_counter()
            notify("text_encoding", "completed", (encoded_at - encoded_started) * 1000)
            response_rows = []
            ranking_times = {}
            for gallery in galleries:
                ranking_started = time.perf_counter()
                notify("ranking", "running", gallery_id=gallery.gallery_id)
                try:
                    ranked = exhaustive_rank(gallery.matrix, gallery.candidate_ids, text_embedding, k)
                except Exception:
                    notify("ranking", "failed", (time.perf_counter() - ranking_started) * 1000, gallery.gallery_id)
                    raise
                ranking_at = time.perf_counter()
                ranking_ms = (ranking_at - ranking_started) * 1000
                notify("ranking", "completed", ranking_ms, gallery.gallery_id)
                ranking_times[gallery.gallery_id] = ranking_ms
                result = build_retrieval_result(
                query_id=query_id,
                text=text,
                language=language,
                embedding_dataset_id=gallery.embedding_manifest["embedding_dataset_id"],
                checkpoint_sha256=self._encoder.checkpoint_sha256,
                ranked=ranked,
                catalog=gallery.catalog,
                gallery_count=len(gallery.candidate_ids),
                requested_k=k,
                timings_ms={"text_encoding": (encoded_at - encoded_started) * 1000, "ranking": ranking_ms, "total": (encoded_at - encoded_started) * 1000 + ranking_ms},
                )
                validate_retrieval_result(result, gallery.catalog, embedding_manifest=gallery.embedding_manifest, candidate_ids=gallery.candidate_ids)
                response_rows.append({
                    "gallery_id": gallery.gallery_id,
                    "visual_dataset_id": gallery.visual_manifest["visual_dataset_id"],
                    "embedding_dataset_id": gallery.embedding_manifest["embedding_dataset_id"],
                    "gallery_count": len(gallery.candidate_ids),
                    "requested_k": k,
                    "effective_k": len(result["results"]),
                    "ranking_method": "exhaustive_cosine",
                    "tie_break": "candidate_id_ascending",
                    "results": [
                        {"rank": row["rank"], "candidate_id": row["candidate_id"], "latitude": row["latitude"], "longitude": row["longitude"], "cosine_similarity": row["score"]}
                        for row in result["results"]
                    ],
                })
            response = {
            "schema_version": "1.0",
            "contract_version": "crosstext2loc-retrieval-response-v1",
            "query": {"query_id": query_id, "text": text, "language": language},
            "model": {"name": self._encoder.model_name, "checkpoint_sha256": self._encoder.checkpoint_sha256},
            "retrievals": response_rows,
            "timings_ms": {"text_encoding": (encoded_at - encoded_started) * 1000, "ranking_by_gallery": ranking_times, "total": (time.perf_counter() - started) * 1000},
            }
            from .validation import validate_document
            validate_document(response, "crosstext2loc_retrieval_response")
            return response

    def cuda_memory(self) -> dict[str, int | None]:
        with self._lifecycle:
            self._ensure_open()
            method = getattr(self._encoder, "cuda_memory", None)
            return method() if method else {"allocated_bytes": None, "reserved_bytes": None, "max_allocated_bytes": None, "max_reserved_bytes": None}

    def close(self) -> None:
        with self._lifecycle:
            if not self._closed:
                self._encoder.close()
                self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeClosedError("runtime cerrado")


def validate_retrieval_request(document: Mapping[str, Any], loaded_gallery_ids: Sequence[str] | None = None) -> None:
    from .validation import SchemaValidationError, validate_document
    try:
        validate_document(document, "crosstext2loc_retrieval_request")
    except SchemaValidationError as error:
        raise RetrievalInputError("petición de retrieval inválida") from error
    query = document["query"]
    ids = _validate_request_values(document["gallery_ids"], query["query_id"], query["text"], query["language"], document["top_k"])
    if loaded_gallery_ids is not None and any(gallery_id not in loaded_gallery_ids for gallery_id in ids):
        raise GalleryNotLoadedError("la petición incluye una galería no cargada")


def _validate_request_values(gallery_ids: Sequence[str], query_id: str, text: str, language: str, k: int) -> tuple[str, ...]:
    if not isinstance(query_id, str) or not query_id.strip():
        raise RetrievalInputError("query_id vacío")
    if not isinstance(text, str) or not text.strip():
        raise RetrievalInputError("texto vacío")
    if not isinstance(language, str) or len(language.strip()) < 2:
        raise RetrievalInputError("idioma inválido")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise RetrievalInputError("top_k debe ser un entero positivo")
    if not isinstance(gallery_ids, Sequence) or isinstance(gallery_ids, (str, bytes)) or not 1 <= len(gallery_ids) <= 2:
        raise RetrievalInputError("se requieren una o dos galerías")
    ids = tuple(gallery_ids)
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise RetrievalInputError("gallery_ids inválidos o duplicados")
    return ids


def _verify_model_resources(config: ModelConfig) -> None:
    _require_file(config.checkpoint, EXPECTED_CHECKPOINT_NAME, EXPECTED_CHECKPOINT_SIZE, EXPECTED_CHECKPOINT_SHA256)
    _require_file(config.clip_weights, EXPECTED_CLIP_WEIGHTS_NAME, EXPECTED_CLIP_WEIGHTS_SIZE, EXPECTED_CLIP_WEIGHTS_SHA256)
    try:
        head = subprocess.run(["git", "-C", str(config.cvg_text_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        if head != EXPECTED_CVG_TEXT_COMMIT:
            raise ResourceIntegrityError("commit CVG-Text inesperado")
        utils = config.cvg_text_root / "utils.py"
        if _sha256(utils) != config.cvg_utils_sha256:
            raise ResourceIntegrityError("utils.py no coincide con el hash declarado")
        from importlib.metadata import distribution
        direct_url = distribution("clip").read_text("direct_url.json")
        commit = json.loads(direct_url).get("vcs_info", {}).get("commit_id") if direct_url else None
        if commit != EXPECTED_CLIP_COMMIT:
            raise ResourceIntegrityError("commit OpenAI CLIP inesperado")
    except CrossText2LocRuntimeError:
        raise
    except Exception as error:
        raise ResourceIntegrityError("no se pudo verificar el entorno del modelo") from error


def _require_file(path: Path, expected_name: str, expected_size: int, expected_sha256: str) -> None:
    if not path.is_file() or path.is_symlink() or path.name != expected_name:
        raise ResourceIntegrityError(f"recurso inexistente o inesperado: {path}")
    if path.stat().st_size != expected_size or _sha256(path) != expected_sha256:
        raise ResourceIntegrityError(f"integridad incorrecta: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
