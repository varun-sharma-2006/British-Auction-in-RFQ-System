"""Concurrency guarantees of the bid path. PostgreSQL only (SQLite has no row locks).

Run with:  TEST_DATABASE_URL=postgresql+psycopg://... pytest tests/test_concurrency.py
"""
import threading
from datetime import timedelta
from decimal import Decimal

import pytest

from app.db import SessionLocal, engine
from app.errors import DomainError
from app.models import AuctionEvent, Bid, EventType, Rfq, Supplier
from app.schemas import BidCreate
from app.services.bidding import submit_bid
from tests.conftest import at, make_rfq

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs PostgreSQL row locking")


def _quote(supplier_id: int, total: int) -> BidCreate:
    return BidCreate(supplier_id=supplier_id, carrier_name="Race Carrier", freight_charges=Decimal(total),
                     transit_time_days=2, quote_validity_date="2099-01-01")


def _fire_simultaneously(jobs):
    """Run callables at the same instant from separate threads/sessions; return (results, errors)."""
    barrier = threading.Barrier(len(jobs))
    results, errors = [], []

    def run(job):
        with SessionLocal() as db:
            barrier.wait()
            try:
                results.append(job(db))
            except DomainError as e:
                errors.append(e)

    threads = [threading.Thread(target=run, args=(j,)) for j in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def test_simultaneous_last_second_bids_extend_exactly_once_each_and_never_pass_forced_close(client, frozen):
    # close at +60, forced at +65, X=10, Y=1: room for exactly 5 one-minute extensions.
    rfq = make_rfq(client, close=60, forced=65, x=10, y=1, trigger="BID_RECEIVED")
    ids = [client.post("/api/suppliers", json={"name": f"Racer {i}"}).json()["id"] for i in range(8)]
    frozen.set(at(59))  # everybody bids one minute before close, at the same instant

    results, errors = _fire_simultaneously([lambda db, s=s, i=i: submit_bid(db, rfq["id"], _quote(s, 1000 - i))
                                            for i, s in enumerate(ids)])

    assert not errors and len(results) == 8
    with SessionLocal() as db:
        r = db.get(Rfq, rfq["id"])
        events = db.query(AuctionEvent).filter_by(rfq_id=r.id).all()
        extended = [e for e in events if e.event_type == EventType.AUCTION_EXTENDED]
        capped = [e for e in events if e.event_type == EventType.EXTENSION_CAPPED]

        # Without the row lock, concurrent bids read the same close time and extensions get lost.
        assert r.extension_count == 5 and len(extended) == 5
        assert len(capped) == 3
        assert r.current_close_at == at(65) == r.forced_close_at
        # Each extension continues exactly where the previous one ended: a gap-free chain.
        chain = sorted((e.previous_close_at, e.new_close_at) for e in extended)
        assert [c[0] for c in chain] == [at(60) + timedelta(minutes=k) for k in range(5)]
        assert all(new - prev == timedelta(minutes=1) for prev, new in chain)


def test_same_supplier_double_submit_is_serialised(client, frozen):
    rfq = make_rfq(client)
    sid = client.post("/api/suppliers", json={"name": "Double Clicker"}).json()["id"]

    results, errors = _fire_simultaneously([lambda db: submit_bid(db, rfq["id"], _quote(sid, 900))] * 2)

    # The second request sees the first one's bid and is rejected: "you can only lower your price".
    assert len(results) == 1 and len(errors) == 1 and errors[0].status_code == 422
    with SessionLocal() as db:
        bids = db.query(Bid).filter_by(rfq_id=rfq["id"]).all()
        assert [b.revision for b in bids] == [1]
        assert db.query(Supplier).count() == 1
