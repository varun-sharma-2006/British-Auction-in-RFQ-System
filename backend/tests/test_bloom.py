"""Bloom filter correctness and the availability checks built on it."""
import fakeredis
import pytest

from app.config import get_settings
from app.services import availability
from app.services.bloom import BloomFilter, MemoryBits, RedisBits, optimal_size
from tests.conftest import auth, make_rfq, register


def test_sizing_matches_the_standard_formulas():
    m, k = optimal_size(100_000, 0.01)
    assert 958_000 < m < 959_000 and k == 7        # ~117 KB for 100k items at 1%


@pytest.mark.parametrize("store", ["memory", "redis"])
def test_no_false_negatives_and_low_false_positive_rate(store):
    server = fakeredis.FakeServer()
    factory = MemoryBits if store == "memory" else (
        lambda bits: RedisBits(lambda: fakeredis.FakeRedis(server=server), "bloom:test"))
    bf = BloomFilter(factory, capacity=2_000, error_rate=0.01)
    members = [f"user{i}@example.com" for i in range(2_000)]
    for m in members:
        bf.add(m)
    assert all(bf.might_contain(m) for m in members)            # never a false negative
    outsiders = [f"other{i}@example.org" for i in range(5_000)]
    fp_rate = sum(bf.might_contain(o) for o in outsiders) / len(outsiders)
    assert fp_rate < 0.03                                        # target 1%, generous bound for a small sample


def test_rebuild_replaces_contents_and_memory_layout_matches_redis():
    server = fakeredis.FakeServer()
    mem = BloomFilter(MemoryBits, capacity=1_000, error_rate=0.01)
    red = BloomFilter(lambda b: RedisBits(lambda: fakeredis.FakeRedis(server=server), "bloom:x"),
                      capacity=1_000, error_rate=0.01)
    for bf in (mem, red):
        bf.add("deleted-later")
        assert bf.rebuild(["a", "b", "c"]) == 3
        assert bf.might_contain("a") and not bf.might_contain("deleted-later")
    red.add("d")                                   # SETBIT on top of the uploaded bytes
    mem.add("d")
    assert fakeredis.FakeRedis(server=server).get("bloom:x") == bytes(mem.store._buf)


def test_email_check_answers_from_the_filter_then_confirms_with_the_database(client):
    availability.stats.clear()
    free = client.get("/api/availability/email", params={"value": "new.person@carrier.com"}).json()
    assert free == {"value": "new.person@carrier.com", "available": True, "checked_by": "bloom"}

    register(client, "Taken@Carrier.com")
    taken = client.get("/api/availability/email", params={"value": " taken@carrier.COM "}).json()
    assert taken["available"] is False and taken["checked_by"] == "database"
    assert availability.stats["answered_by_bloom"] == 1 and availability.stats["confirmed_taken"] == 1


def test_company_check_means_you_will_join_it(client):
    register(client, "ops@gati.com", role="SUPPLIER", company="Gati Express")
    res = client.get("/api/availability/company", params={"value": "gati express"}).json()
    assert res["available"] is False
    assert client.get("/api/availability/company", params={"value": "Brand New Freight"}).json()["available"]


def test_reference_id_check_is_for_buyers_and_sees_auto_generated_ids(client):
    rfq = make_rfq(client, reference_id="LANE-42")
    auto = make_rfq(client)
    for ref in ("LANE-42", auto["reference_id"]):
        assert client.get("/api/availability/reference-id", params={"value": ref}).json()["available"] is False
    assert client.get("/api/availability/reference-id", params={"value": "LANE-43"}).json()["checked_by"] == "bloom"
    supplier = auth(register(client, "s@x.com", role="SUPPLIER", company="X Co"))
    assert client.get("/api/availability/reference-id", params={"value": "LANE-42"},
                      headers=supplier).status_code == 403
    assert rfq["reference_id"] == "LANE-42"


def test_false_positives_are_caught_by_the_database(client, monkeypatch):
    monkeypatch.setattr(availability.get_filter("email"), "might_contain", lambda v: True)  # filter says "maybe"
    res = client.get("/api/availability/email", params={"value": "nobody@x.com"}).json()
    assert res == {"value": "nobody@x.com", "available": True, "checked_by": "database"}
    assert availability.stats["false_positive"] == 1


def test_rows_written_outside_the_api_are_picked_up_by_rebuild(client):
    from app.db import SessionLocal
    from app.models import Supplier
    with SessionLocal() as db:
        db.add(Supplier(name="Seeded Carrier"))
        db.commit()
        assert availability.check(db, "company", "Seeded Carrier") == (True, "bloom")   # stale: not added yet
        availability.rebuild_all(db)
        assert availability.check(db, "company", "Seeded Carrier") == (False, "database")


def test_unreachable_redis_falls_back_to_the_database(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "redis_url", "redis://unreachable:1")
    availability.reset_filters()

    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(availability, "_redis_client", boom)
    register(client, "still@works.com")            # writes don't fail when the filter is unreachable
    res = client.get("/api/availability/email", params={"value": "still@works.com"}).json()
    assert res["available"] is False and res["checked_by"] == "database"
    availability.reset_filters()
