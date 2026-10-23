"""A deployed demo must never go stale: it tops itself up with live auctions."""
from app import main
from app.config import get_settings
from app.db import SessionLocal
from app.models import Rfq
from app.services import demo
from app.services.rfq_service import list_rfqs
from tests.conftest import T0, at


def _statuses(db, now):
    return sorted(r.status.value for r in list_rfqs(db) if r.is_british_auction)


def test_tops_up_when_fewer_than_two_auctions_are_open(client, frozen):
    with SessionLocal() as db:
        demo.ensure_accounts(db)
        assert demo.ensure_live_demo(db, T0) is True
        assert _statuses(db, T0) == ["ACTIVE", "ACTIVE", "ACTIVE", "SCHEDULED"]
        assert demo.ensure_live_demo(db, T0) is False            # enough open auctions now

        # Hours later everything has closed: the next check starts a fresh round.
        later = at(6 * 60)
        frozen.set(later)
        assert demo.ensure_live_demo(db, later) is True
        assert db.query(Rfq).count() == 8


def test_live_round_is_built_by_the_real_engine(client, frozen):
    with SessionLocal() as db:
        demo.ensure_accounts(db)
        demo.ensure_live_demo(db, T0)
        war = next(r for r in list_rfqs(db) if r.bid_count == 4)
        assert war.lowest_bidder == "VRL Logistics" and float(war.lowest_bid) == 149000   # VRL re-took L1


def test_does_nothing_on_a_non_demo_database(client):
    with SessionLocal() as db:
        assert demo.ensure_live_demo(db, T0) is False
        assert db.query(Rfq).count() == 0


def test_api_requests_trigger_the_refresh_when_demo_mode_is_on(client, monkeypatch):
    with SessionLocal() as db:
        demo.ensure_accounts(db)
    monkeypatch.setattr(main, "_last_demo_check", 0.0)
    client.get("/api/health")
    with SessionLocal() as db:
        assert db.query(Rfq).count() == 0                         # off by default

    monkeypatch.setattr(get_settings(), "seed_demo", True)
    monkeypatch.setattr(main, "_last_demo_check", 0.0)
    client.get("/api/health")
    client.get("/api/health")                                     # throttled: still one round
    with SessionLocal() as db:
        assert db.query(Rfq).count() == 4
