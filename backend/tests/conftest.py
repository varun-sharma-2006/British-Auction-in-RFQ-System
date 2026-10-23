import os
import tempfile
from datetime import UTC, datetime, timedelta

# Must be set before the app (and its engine) is imported.
# TEST_DATABASE_URL=postgresql+psycopg://... runs the suite against PostgreSQL (CI does this);
# otherwise a throwaway SQLite file is used so the tests run anywhere.
_SQLITE = "sqlite:///" + os.path.join(tempfile.gettempdir(), "british_auction_test.db")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", _SQLITE)
os.environ["RUN_CLOSER"] = "false"
os.environ["PASSWORD_HASH_ITERATIONS"] = "1000"  # fast hashing in tests
os.environ["RATE_LIMIT_ENABLED"] = "false"       # tests make many requests; test_protection.py turns it on

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import clock  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import availability  # noqa: E402

T0 = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)  # 12:00 UTC; tests advance from here


class FakeClock:
    def __init__(self, now: datetime):
        self.now = now

    def set(self, now: datetime) -> None:
        self.now = now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def frozen(monkeypatch) -> FakeClock:
    fake = FakeClock(T0)
    monkeypatch.setattr(clock, "utcnow", lambda: fake.now)
    return fake


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    availability.reset_filters()   # each test starts with empty Bloom filters, like a fresh deployment
    yield


SUPPLIER_HEADERS: dict[int, dict] = {}   # supplier_id -> Authorization header of a user of that supplier


def register(client, email, role="BUYER", company=None, password="secret-pass-1") -> dict:
    res = client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": email.split("@")[0] + " User",
        "role": role, "company_name": company,
    })
    assert res.status_code == 201, res.text
    return res.json()


def auth(token_response: dict) -> dict:
    return {"Authorization": f"Bearer {token_response['access_token']}"}


@pytest.fixture
def client(frozen) -> TestClient:
    """A client signed in as a buyer. Supplier requests pass their own headers (see `bid`)."""
    SUPPLIER_HEADERS.clear()
    with TestClient(app) as c:
        c.headers.update(auth(register(c, "buyer@test.com")))
        yield c


def add_supplier(client, name: str) -> int:
    tok = register(client, f"{name.split()[0].lower()}@test.com", role="SUPPLIER", company=name)
    sid = tok["user"]["supplier_id"]
    SUPPLIER_HEADERS[sid] = auth(tok)
    return sid


@pytest.fixture
def suppliers(client) -> dict[str, int]:
    names = ("Alpha Logistics", "Bravo Freight", "Charlie Cargo")
    return {name.split()[0]: add_supplier(client, name) for name in names}


def at(minutes: float) -> datetime:
    """T0 + minutes, i.e. a point on the test timeline."""
    return T0 + timedelta(minutes=minutes)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")  # matches the API's serialisation


def make_rfq(client, *, start=-5, close=60, forced=90, x=10, y=5, trigger="BID_RECEIVED", **extra):
    body = {
        "name": "Mumbai -> Delhi FTL",
        "pickup_date": (T0 + timedelta(days=3)).date().isoformat(),
        "bid_start_at": iso(at(start)),
        "bid_close_at": iso(at(close)),
        "forced_close_at": iso(at(forced)),
        "is_british_auction": True,
        "trigger_window_minutes": x,
        "extension_minutes": y,
        "trigger_type": trigger,
        **extra,
    }
    res = client.post("/api/rfqs", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def bid(client, rfq_id, supplier_id, freight, origin=0, dest=0, **extra):
    """Submit a quote as a user of `supplier_id`."""
    body = {
        "carrier_name": "Test Carrier",
        "freight_charges": freight,
        "origin_charges": origin,
        "destination_charges": dest,
        "transit_time_days": 3,
        "quote_validity_date": "2099-12-31",
        **extra,
    }
    return client.post(f"/api/rfqs/{rfq_id}/bids", json=body, headers=SUPPLIER_HEADERS[supplier_id])
