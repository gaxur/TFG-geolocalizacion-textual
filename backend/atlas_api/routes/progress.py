"""SSE por query_id para observar transiciones reales del pipeline HTTP."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/api/v1")


@router.get("/progress/{query_id}")
async def progress_stream(query_id: str, request: Request) -> StreamingResponse:
    hub = request.app.state.progress_hub
    queue = await hub.subscribe(query_id)

    async def events():
        try:
            hello = {"schema_version": "1.0", "event_type": "connected", "query_id": query_id, "sequence": 0}
            yield f"data: {json.dumps(hello, separators=(',', ':'))}\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"
                if event.get("event_type") == "pipeline" and event.get("state") in {"completed", "failed"}:
                    break
        finally:
            await hub.unsubscribe(query_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
