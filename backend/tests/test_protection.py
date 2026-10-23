"""Abuse protection for the public demo: rate limits and the nightly reset."""
import fakeredis
import pytest

from app import ratelimit
from app.config import get_settings
from app.db import SessionLocal
from app.models import Rfq, User
from app.services import demo
from tests.conftest import bid, make_rfq


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    ratelimit.reset()
    yield
    ratelimit.reset()


def _register(client, i, ip="203.0.113.7"):
    return client.post("/api/auth/register", headers={"X-Real-IP": ip}, json={
        "email": f"spam{i}@spam-co.com", "password": "secret-pass-1", "full_name": "Spam Bot", "role": "BUYER"})


def test_signups_are_limited_per_ip(client, limits_on):
    assert [_register(client, i).status_code for i in range(5)] == [201] * 5
    res = _register(client, 99)
    assert res.status_code == 429 and "try again" in res.json()["detail"]
    assert _register(client, 100, ip="198.51.100.9").status_code == 201      # other clients unaffected


def test_logins_are_limited(client, limits_on):
    codes = [client.post("/api/auth/login", json={"email": "buyer@test.com", "password": "wrong-pass"}).status_code
             for _ in range(21)]
    assert codes[:20] == [401] * 20 and codes[20] == 429


def test_bids_are_limited_per_session(client, suppliers, limits_on):
    rfq = make_rfq(client)
    codes = [bid(client, rfq["id"], suppliers["Alpha"], 100_000 - i).status_code for i in range(31)]
    assert codes[:30] == [201] * 30 and codes[30] == 429
    assert bid(client, rfq["id"], suppliers["Bravo"], 50_000).status_code == 201   # another supplier is fine


def test_limits_are_shared_through_redis(client, limits_on, monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(get_settings(), "redis_url", "redis://fake")
    import redis
    monkeypatch.setattr(redis, "from_url", lambda url: fakeredis.FakeRedis(server=server))
    assert [_register(client, i).status_code for i in range(6)][-1] == 429
    assert any(k.startswith(b"rl:register:203.0.113.7") for k in fakeredis.FakeRedis(server=server).scan_iter())


def test_limits_are_off_when_disabled(client):
    assert all(_register(client, i).status_code == 201 for i in range(8))


def test_nightly_reset_requires_the_cron_secret_and_wipes_junk(client, monkeypatch):
    assert client.get("/api/cron/reset-demo").status_code == 404                # off unless configured
    monkeypatch.setattr(get_settings(), "seed_demo", True)
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret")
    assert client.get("/api/cron/reset-demo").status_code == 401
    assert client.get("/api/cron/reset-demo", headers={"Authorization": "Bearer wrong"}).status_code == 401

    make_rfq(client, name="Junk created by a visitor")
    res = client.get("/api/cron/reset-demo", headers={"Authorization": "Bearer s3cret"})
    assert res.status_code == 200 and res.json()["status"] == "reset"
    with SessionLocal() as db:
        names = [r.name for r in db.query(Rfq)]
        assert "Junk created by a visitor" not in names and len(names) == 7
        assert db.query(User).filter(User.email == demo.BUYER_EMAIL).count() == 1
        assert db.query(User).filter(User.email == "buyer@test.com").count() == 0   # visitor accounts gone
