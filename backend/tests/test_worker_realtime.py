"""Celery closer task and Redis pub/sub fan-out, against an in-memory Redis (fakeredis)."""
import asyncio
import json

import fakeredis
import pytest

from app import realtime
from app.config import get_settings
from app.worker import celery_app, close_due
from tests.conftest import at, bid, make_rfq


@pytest.fixture
def fake_redis(monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(get_settings(), "redis_url", "redis://fake")
    monkeypatch.setattr(realtime, "sync_redis", lambda: fakeredis.FakeRedis(server=server))
    monkeypatch.setattr(realtime, "async_redis", lambda: fakeredis.FakeAsyncRedis(server=server))
    return server


def _subscribe(server):
    pubsub = fakeredis.FakeRedis(server=server).pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(realtime.CHANNEL)
    return pubsub


def _messages(pubsub) -> list[dict]:
    # get_message() also returns None when it swallows a subscribe confirmation, so poll a few times.
    out = []
    for _ in range(5):
        m = pubsub.get_message(timeout=0.1)
        if m is not None:
            out.append(json.loads(m["data"]))
    return out


def test_celery_task_closes_due_auctions_and_publishes(client, suppliers, frozen, fake_redis):
    rfq = make_rfq(client, close=60)
    bid(client, rfq["id"], suppliers["Alpha"], 1000)
    pubsub = _subscribe(fake_redis)
    _messages(pubsub)  # drain the bid notification

    frozen.set(at(61))
    celery_app.conf.task_always_eager = True
    try:
        assert close_due.delay().get() == [rfq["id"]]
        assert close_due.delay().get() == []        # idempotent: already closed
    finally:
        celery_app.conf.task_always_eager = False

    assert _messages(pubsub) == [{"type": "rfq_updated", "rfq_id": rfq["id"], "reason": "status_changed"}]
    assert client.get(f"/api/rfqs/{rfq['id']}").json()["status"] == "CLOSED"


def test_beat_schedule_runs_the_closer():
    entry = celery_app.conf.beat_schedule["close-due-auctions"]
    assert entry["task"] == "auction.close_due" and entry["schedule"] == get_settings().closer_interval_seconds


def test_api_publishes_bids_to_redis_when_configured(client, suppliers, fake_redis):
    rfq = make_rfq(client)
    pubsub = _subscribe(fake_redis)
    bid(client, rfq["id"], suppliers["Alpha"], 1000)
    assert _messages(pubsub) == [{"type": "rfq_updated", "rfq_id": rfq["id"], "reason": "bid"}]


def test_relay_forwards_redis_messages_to_local_sockets(fake_redis, monkeypatch):
    received = []

    async def record(msg):
        received.append(msg)

    monkeypatch.setattr(realtime.manager, "broadcast", record)

    async def scenario():
        stop = asyncio.Event()
        relay = asyncio.create_task(realtime.relay_from_redis(stop))
        await asyncio.sleep(0.2)                             # let it subscribe
        realtime.publish_from_worker(42, "status_changed")   # e.g. from a Celery worker process
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.05)
        stop.set()
        await relay

    asyncio.run(scenario())
    assert received == [{"type": "rfq_updated", "rfq_id": 42, "reason": "status_changed"}]


def test_without_redis_worker_publish_is_a_noop(monkeypatch):
    monkeypatch.setattr(get_settings(), "redis_url", None)
    monkeypatch.setattr(realtime, "sync_redis", lambda: (_ for _ in ()).throw(AssertionError("must not connect")))
    realtime.publish_from_worker(1, "x")
