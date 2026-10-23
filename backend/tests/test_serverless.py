"""Serverless mode (Vercel): no reliable background loops, so work happens on incoming requests."""
from app import main
from app.config import get_settings
from app.db import SessionLocal
from app.models import Supplier
from app.services import availability
from tests.conftest import at, bid, make_rfq


def _events(client, rfq_id, kind):
    return [e for e in client.get(f"/api/rfqs/{rfq_id}/activity").json() if e["event_type"] == kind]


def test_due_auctions_close_on_the_next_api_request(client, suppliers, frozen, monkeypatch):
    monkeypatch.setattr(get_settings(), "close_on_request", True)
    monkeypatch.setattr(main, "_last_close_check", 0.0)
    rfq = make_rfq(client, close=60)
    bid(client, rfq["id"], suppliers["Alpha"], 1000)

    frozen.set(at(61))
    monkeypatch.setattr(main, "_last_close_check", 0.0)       # throttle window has passed
    client.get("/api/rfqs")                                    # any API request triggers the closer

    closed = _events(client, rfq["id"], "AUCTION_CLOSED")
    assert len(closed) == 1 and closed[0]["occurred_at"].startswith("2030-01-15T13:00")


def test_opportunistic_close_is_throttled(client, frozen, monkeypatch):
    monkeypatch.setattr(get_settings(), "close_on_request", True)
    calls = []
    monkeypatch.setattr(main, "close_due_auctions", lambda: calls.append(1) or [])
    monkeypatch.setattr(main, "_last_close_check", 0.0)
    for _ in range(5):
        client.get("/api/health")
    assert len(calls) == 1                                     # once per 5 s, not once per request


def test_close_on_request_is_off_by_default(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "close_due_auctions", lambda: calls.append(1) or [])
    monkeypatch.setattr(main, "_last_close_check", 0.0)
    client.get("/api/health")
    assert calls == []


def test_stale_in_memory_bloom_filter_is_rebuilt_before_answering(client, monkeypatch):
    """Another serverless instance inserted a row this instance's filter never saw."""
    monkeypatch.setattr(get_settings(), "bloom_max_age_seconds", 60)
    with SessionLocal() as db:
        availability.rebuild_all(db)
        db.add(Supplier(name="Written Elsewhere"))
        db.commit()
        # Still fresh: answered (wrongly, but harmlessly; the DB constraint guards inserts) by the filter.
        assert availability.check(db, "company", "Written Elsewhere") == (True, "bloom")
        monkeypatch.setattr(availability, "_built_at", -10_000.0)       # pretend it is old
        assert availability.check(db, "company", "Written Elsewhere") == (False, "database")
