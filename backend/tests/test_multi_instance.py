"""Two real API processes sharing PostgreSQL and Redis, as they run behind the load balancer.

Proves what horizontal scaling relies on:
  * a bid handled by replica A reaches a browser connected to replica B (Redis pub/sub fan-out);
  * the Bloom filter is shared, so replica B knows about an email that just registered on replica A;
  * a JWT issued by one replica is accepted by the other (stateless auth).

Needs real services:  TEST_DATABASE_URL=postgresql+psycopg://...  TEST_REDIS_URL=redis://...
"""
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from websockets.sync.client import connect

from app.db import engine

REDIS_URL = os.environ.get("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql" or not REDIS_URL, reason="needs PostgreSQL and Redis (TEST_REDIS_URL)",
)
BACKEND = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start(name: str, port: int) -> subprocess.Popen:
    env = {**os.environ, "DATABASE_URL": str(engine.url.render_as_string(hide_password=False)),
           "REDIS_URL": REDIS_URL, "RUN_CLOSER": "false", "INSTANCE_NAME": name,
           "PASSWORD_HASH_ITERATIONS": "1000", "BLOOM_REBUILD_SECONDS": "3600"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError(f"{name} did not start")


@pytest.fixture
def replicas():
    import redis
    redis.from_url(REDIS_URL).flushdb()        # fresh shared Bloom filters for this test
    ports = [_free_port(), _free_port()]
    procs = [_start(n, p) for n, p in zip(("replica-a", "replica-b"), ports, strict=True)]
    try:
        yield [f"http://127.0.0.1:{p}" for p in ports]
    finally:
        for p in procs:
            p.terminate()
            p.wait(timeout=10)


def _register(base, email, role="BUYER", company=None) -> dict:
    res = httpx.post(f"{base}/api/auth/register", json={"email": email, "password": "secret-pass-1",
                                                        "full_name": "Test User", "role": role,
                                                        "company_name": company})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_bid_on_one_replica_reaches_websocket_on_the_other(replicas):
    a, b = replicas
    assert httpx.get(f"{a}/api/health").headers["X-Served-By"] == "replica-a"
    assert httpx.get(f"{b}/api/health").headers["X-Served-By"] == "replica-b"

    buyer = _register(a, "buyer@multi-carrier.com")
    supplier = _register(b, "carrier@multi-carrier.com", role="SUPPLIER", company="Multi Carrier")
    now = datetime.now(UTC)
    rfq = httpx.post(f"{b}/api/rfqs", headers=buyer, json={   # token from A accepted by B
        "name": "Cross-replica lane", "pickup_date": (now + timedelta(days=2)).date().isoformat(),
        "bid_start_at": (now - timedelta(minutes=1)).isoformat(),
        "bid_close_at": (now + timedelta(minutes=30)).isoformat(),
        "forced_close_at": (now + timedelta(minutes=60)).isoformat(),
        "trigger_window_minutes": 10, "extension_minutes": 5, "trigger_type": "BID_RECEIVED"})
    assert rfq.status_code == 201, rfq.text
    rfq_id = rfq.json()["id"]

    with connect(b.replace("http", "ws") + "/ws", open_timeout=5) as ws:   # browser connected to replica B
        time.sleep(0.5)                                                    # let B's Redis relay subscribe
        res = httpx.post(f"{a}/api/rfqs/{rfq_id}/bids", headers=supplier, json={   # bid lands on replica A
            "carrier_name": "Multi Carrier", "freight_charges": "1000", "transit_time_days": 2,
            "quote_validity_date": (now + timedelta(days=30)).date().isoformat()})
        assert res.status_code == 201, res.text
        assert res.headers["X-Served-By"] == "replica-a"
        msg = json.loads(ws.recv(timeout=5))
        assert msg == {"type": "rfq_updated", "rfq_id": rfq_id, "reason": "bid"}


def test_bloom_filter_is_shared_between_replicas(replicas):
    a, b = replicas
    probe = {"value": "fresh@multi-carrier.com"}
    assert httpx.get(f"{b}/api/availability/email", params=probe).json()["checked_by"] == "bloom"
    _register(a, "fresh@multi-carrier.com")                       # added to the Redis bits by replica A
    seen_by_b = httpx.get(f"{b}/api/availability/email", params=probe).json()
    assert seen_by_b == {"value": "fresh@multi-carrier.com", "available": False, "checked_by": "database"}
