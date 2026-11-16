"""Admisión atómica de una única operación de modelo por proceso API."""
from __future__ import annotations

import asyncio


class ModelGate:
    def __init__(self):
        self._owner: asyncio.Task | None = None

    def locked(self) -> bool:
        return self._owner is not None

    def try_acquire(self) -> bool:
        task = asyncio.current_task()
        if self._owner is not None:
            return self._owner is task
        self._owner = task
        return True

    async def acquire(self) -> bool:
        if not self.try_acquire():
            raise RuntimeError("model gate ocupado")
        return True

    def release(self) -> None:
        if self._owner is None:
            raise RuntimeError("model gate no adquirido")
        self._owner = None

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.release()
