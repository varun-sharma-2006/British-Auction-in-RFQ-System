"""Tiny WebSocket fan-out.

Messages are deliberately thin ("RFQ 12 changed"): clients re-fetch over REST,
so there is exactly one source of truth for what an auction looks like.

This is in-process, i.e. correct for a single API instance. To scale out
horizontally, publish these notifications on Redis pub/sub (or PG LISTEN/NOTIFY)
and have every instance relay them to its own sockets; the interface below
stays the same.
"""
import asyncio
import json

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._sockets.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets.discard(ws)

    async def broadcast(self, message: dict) -> None:
        payload = json.dumps(message, default=str)
        async with self._lock:
            sockets = list(self._sockets)
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:  # client went away mid-send
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


manager = ConnectionManager()


async def notify_rfq_changed(rfq_id: int, reason: str) -> None:
    await manager.broadcast({"type": "rfq_updated", "rfq_id": rfq_id, "reason": reason})
