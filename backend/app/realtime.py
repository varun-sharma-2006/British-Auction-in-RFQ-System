"""Live-update fan-out to browsers over WebSocket.

Messages are deliberately thin ("RFQ 12 changed"): clients re-fetch over REST,
so there is exactly one source of truth for what an auction looks like.

Two modes:
* no REDIS_URL  - in-process: correct for a single API instance.
* REDIS_URL set - every publisher (any API replica, the Celery worker) PUBLISHes
  to a Redis channel; every API replica runs `relay_from_redis`, which forwards
  each message to the sockets connected to *that* replica.
"""
import asyncio
import json
import logging

import redis
import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import get_settings

log = logging.getLogger(__name__)
CHANNEL = "rfq_updates"


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


# Factories are module-level so tests can swap in fakeredis.
def async_redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().redis_url)


def sync_redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


def _message(rfq_id: int, reason: str) -> dict:
    return {"type": "rfq_updated", "rfq_id": rfq_id, "reason": reason}


async def notify_rfq_changed(rfq_id: int, reason: str) -> None:
    """Called from the API process."""
    msg = _message(rfq_id, reason)
    if get_settings().redis_url:
        client = async_redis()
        try:
            await client.publish(CHANNEL, json.dumps(msg))
        finally:
            await client.aclose()
    else:
        await manager.broadcast(msg)


def publish_from_worker(rfq_id: int, reason: str) -> None:
    """Called from Celery workers (sync, separate process): only Redis can reach the API's sockets."""
    if not get_settings().redis_url:
        return
    client = sync_redis()
    try:
        client.publish(CHANNEL, json.dumps(_message(rfq_id, reason)))
    finally:
        client.close()


async def relay_from_redis(stop: asyncio.Event) -> None:
    """Forward every message on the Redis channel to this replica's WebSocket clients."""
    while not stop.is_set():
        client = async_redis()
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(CHANNEL)
            log.info("Relaying live updates from Redis channel %r", CHANNEL)
            while not stop.is_set():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    await manager.broadcast(json.loads(msg["data"]))
        except Exception:
            log.exception("Redis relay failed; retrying in 2s")
            await asyncio.sleep(2)
        finally:
            await pubsub.aclose()
            await client.aclose()
