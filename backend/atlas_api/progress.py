"""Canal SSE efímero de observabilidad por consulta; no guarda datos del texto."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from typing import Any


class ProgressHub:
    """Fan-out en memoria para el único worker Uvicorn del MVP."""

    def __init__(self, *, max_queue_size: int = 128):
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size

    async def subscribe(self, query_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue_size)
        async with self._lock:
            self._queues.setdefault(query_id, set()).add(queue)
        return queue

    async def unsubscribe(self, query_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subscribers = self._queues.get(query_id)
            if subscribers is None:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._queues.pop(query_id, None)

    async def has_subscribers(self, query_id: str) -> bool:
        async with self._lock:
            return bool(self._queues.get(query_id))

    def subscriber_count(self, query_id: str) -> int:
        """Contador de lectura para pruebas; los cambios siguen bajo asyncio.Lock."""
        return len(self._queues.get(query_id, ()))

    async def publish(self, event: dict[str, Any]) -> None:
        query_id = event["query_id"]
        async with self._lock:
            subscribers = tuple(self._queues.get(query_id, ()))
        for queue in subscribers:
            try:
                queue.put_nowait(dict(event))
            except asyncio.QueueFull:
                # El procesamiento nunca espera al navegador. El cliente detecta
                # el salto de sequence y degrada el progreso a desconocido.
                continue


class QueryProgress:
    """Emite transiciones observables sin incluir texto, scores ni coordenadas."""

    def __init__(self, hub: ProgressHub, query_id: str):
        self.hub = hub
        self.query_id = query_id
        self.sequence = 0
        self.started_at = time.perf_counter()
        self._stage_started: dict[str, float] = {}
        self.active_stage: str | None = None
        self.terminal = False

    async def publish(
        self,
        *,
        event_type: str,
        stage_id: str,
        state: str,
        message: str,
        subphase: dict[str, Any] | None = None,
        outcome: str | None = None,
        elapsed_ms: float | None = None,
    ) -> None:
        if self.terminal:
            return
        now = time.perf_counter()
        if event_type == "stage" and subphase is None:
            if state == "running":
                self._stage_started.setdefault(stage_id, now)
            elif state in {"completed", "failed"} and elapsed_ms is None:
                started = self._stage_started.pop(stage_id, None)
                if started is not None:
                    elapsed_ms = round((now - started) * 1000, 3)
        self.sequence += 1
        event: dict[str, Any] = {
            "schema_version": "1.0",
            "event_type": event_type,
            "query_id": self.query_id,
            "sequence": self.sequence,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "stage_id": stage_id,
            "state": state,
            "message": message,
            "elapsed_ms": elapsed_ms,
        }
        if subphase is not None:
            event["subphase"] = subphase
        if outcome is not None:
            event["outcome"] = outcome
        await self.hub.publish(event)

    async def stage(
        self,
        stage_id: str,
        state: str,
        message: str,
        *,
        subphase: dict[str, Any] | None = None,
        outcome: str | None = None,
        elapsed_ms: float | None = None,
    ) -> None:
        await self.publish(
            event_type="stage", stage_id=stage_id, state=state, message=message,
            subphase=subphase, outcome=outcome, elapsed_ms=elapsed_ms,
        )
        if subphase is None:
            if state == "running":
                self.active_stage = stage_id
            elif self.active_stage == stage_id and state in {"completed", "failed", "skipped", "unavailable"}:
                self.active_stage = None

    async def subphase(
        self,
        subphase_id: str,
        subphase_state: str,
        message: str,
        *,
        elapsed_ms: float | None = None,
        gallery_id: str | None = None,
    ) -> None:
        subphase = {"id": subphase_id, "state": subphase_state}
        if elapsed_ms is not None:
            subphase["elapsed_ms"] = round(float(elapsed_ms), 3)
        if gallery_id is not None:
            subphase["gallery_id"] = gallery_id
        await self.publish(
            event_type="stage", stage_id="crosstext2loc", state="running",
            message=message, subphase=subphase,
        )

    async def pipeline(self, state: str, message: str, *, error_code: str | None = None) -> None:
        await self.publish(
            event_type="pipeline", stage_id="pipeline", state=state, message=message,
            elapsed_ms=round((time.perf_counter() - self.started_at) * 1000, 3),
            outcome=error_code,
        )
        if state in {"completed", "failed"}:
            self.terminal = True
