"""Caché temporal Mapillary con escritura atómica y limpieza conservadora."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Iterator


class MapillaryCacheError(ValueError):
    pass


class MapillaryCache:
    def __init__(self, root: Path, *, max_gb: float = 2, ttl_hours: float = 48):
        if max_gb <= 0 or ttl_hours <= 0:
            raise MapillaryCacheError("límites de caché inválidos")
        self.root = root
        self.images = root / "images"
        self.metadata = root / "metadata"
        self.active = root / ".active"
        self.pins = root / ".pins"
        self.max_bytes = int(max_gb * 1024**3)
        self.ttl_seconds = ttl_hours * 3600

    def prepare(self) -> None:
        for path in (self.images, self.metadata, self.active, self.pins):
            path.mkdir(parents=True, exist_ok=True)

    def image_path(self, image_id: str, suffix: str = ".jpg") -> Path:
        if not image_id.isdigit() or suffix not in {".jpg", ".png"}:
            raise MapillaryCacheError("image_id o extensión inválidos")
        return self.images / f"{image_id}{suffix}"

    def store(self, image_id: str, raw: bytes, metadata: dict, *, suffix: str = ".jpg") -> dict:
        self.prepare()
        destination = self.image_path(image_id, suffix)
        digest = hashlib.sha256(raw).hexdigest()
        existing = next(iter(self.images.glob(f"{image_id}.*")), None)
        if existing:
            if hashlib.sha256(existing.read_bytes()).hexdigest() != digest:
                raise MapillaryCacheError("image_id ya existe con contenido diferente")
            os.utime(existing, None)
            return json.loads((self.metadata / f"{image_id}.json").read_text(encoding="utf-8"))
        temporary = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
        temporary.write_bytes(raw)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
            temporary.unlink(missing_ok=True)
            raise MapillaryCacheError("falló la verificación de integridad temporal")
        temporary.replace(destination)
        record = {
            **metadata,
            "image_id": image_id,
            "logical_path": f"images/{destination.name}",
            "sha256": digest,
            "size_bytes": len(raw),
            "cached_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        metadata_path = self.metadata / f"{image_id}.json"
        metadata_tmp = metadata_path.with_suffix(f".{os.getpid()}.tmp")
        metadata_tmp.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        metadata_tmp.replace(metadata_path)
        return record

    @contextmanager
    def in_use(self, image_ids: list[str]) -> Iterator[None]:
        self.prepare()
        markers = []
        try:
            for image_id in image_ids:
                marker = self.active / f"{image_id}.{os.getpid()}"
                marker.write_text(str(time.time()), encoding="ascii")
                markers.append(marker)
            yield
        finally:
            for marker in markers:
                marker.unlink(missing_ok=True)

    def pin(self, image_id: str, experiment_id: str) -> None:
        self.prepare()
        if not image_id.isdigit() or not experiment_id:
            raise MapillaryCacheError("pin inválido")
        (self.pins / f"{image_id}.json").write_text(json.dumps({"image_id": image_id, "experiment_id": experiment_id}, sort_keys=True) + "\n", encoding="utf-8")

    def cleanup(self, *, now: float | None = None) -> dict:
        self.prepare()
        now = time.time() if now is None else now
        active_ids = {path.name.split(".", 1)[0] for path in self.active.iterdir() if path.is_file()}
        pinned_ids = {path.stem for path in self.pins.glob("*.json")}
        files = sorted((path for path in self.images.iterdir() if path.is_file() and not path.name.endswith(".tmp")), key=lambda path: path.stat().st_mtime)
        total = sum(path.stat().st_size for path in files)
        removed = []
        for path in files:
            image_id = path.stem
            expired = now - path.stat().st_mtime > self.ttl_seconds
            over_limit = total > self.max_bytes
            if image_id in active_ids or image_id in pinned_ids or not (expired or over_limit):
                continue
            size = path.stat().st_size
            path.unlink()
            (self.metadata / f"{image_id}.json").unlink(missing_ok=True)
            total -= size
            removed.append(image_id)
        return {"removed_image_ids": removed, "remaining_bytes": total, "active_skipped": sorted(active_ids), "pinned_skipped": sorted(pinned_ids)}


def cache_from_env(project_root: Path) -> MapillaryCache:
    root = Path(os.environ.get("MAPILLARY_CACHE_DIR", project_root / "data/cache/mapillary"))
    return MapillaryCache(root, max_gb=float(os.environ.get("MAPILLARY_CACHE_MAX_GB", "2")), ttl_hours=float(os.environ.get("MAPILLARY_CACHE_TTL_HOURS", "48")))
