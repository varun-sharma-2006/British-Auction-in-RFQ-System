from app.db import SessionLocal
from app.models import Rfq
from app.security import hash_password, verify_password
from tests.conftest import SUPPLIER_HEADERS, add_supplier, auth, bid, make_rfq, register


def test_password_hashing():
    h = hash_password("correct horse", iterations=1000)
    assert "correct horse" not in h and h.startswith("pbkdf2_sha256$1000$")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert hash_password("correct horse", iterations=1000) != h   # salted
    assert not verify_password("x", "garbage")


def test_register_login_me(client):
    tok = register(client, "Ops@Carrier.com", role="SUPPLIER", company="Carrier Co")
    assert tok["user"]["role"] == "SUPPLIER" and tok["user"]["supplier_name"] == "Carrier Co"
    assert tok["user"]["email"] == "ops@carrier.com"

    res = client.post("/api/auth/login", json={"email": "OPS@carrier.com", "password": "secret-pass-1"})
    assert res.status_code == 200
    me = client.get("/api/auth/me", headers=auth(res.json())).json()
    assert me["email"] == "ops@carrier.com" and me["supplier_id"] == tok["user"]["supplier_id"]


def test_colleagues_share_one_supplier_company(client):
    a = register(client, "a@carrier.com", role="SUPPLIER", company="Carrier Co")
    b = register(client, "b@carrier.com", role="SUPPLIER", company="carrier co")
    assert a["user"]["supplier_id"] == b["user"]["supplier_id"]


def test_login_failures_do_not_reveal_which_part_was_wrong(client):
    register(client, "x@test.com")
    wrong_pw = client.post("/api/auth/login", json={"email": "x@test.com", "password": "nope-nope"})
    no_user = client.post("/api/auth/login", json={"email": "ghost@test.com", "password": "nope-nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"]


def test_registration_validation(client):
    register(client, "dup@test.com")
    dup = client.post("/api/auth/register", json={"email": "DUP@test.com", "password": "secret-pass-1",
                                                  "full_name": "Dup", "role": "BUYER"})
    assert dup.status_code == 409
    short = client.post("/api/auth/register", json={"email": "s@test.com", "password": "short",
                                                    "full_name": "S", "role": "BUYER"})
    assert short.status_code == 422
    no_company = client.post("/api/auth/register", json={"email": "c@test.com", "password": "secret-pass-1",
                                                         "full_name": "Carrier", "role": "SUPPLIER"})
    assert no_company.status_code == 422 and "company" in no_company.json()["detail"]


def test_endpoints_require_a_valid_token(client, frozen):
    anon = {"Authorization": ""}
    assert client.get("/api/rfqs", headers=anon).status_code == 401
    assert client.get("/api/rfqs", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert client.get("/api/health", headers=anon).status_code == 200   # public

    frozen.advance(hours=13)  # tokens last 12h
    res = client.get("/api/rfqs")
    assert res.status_code == 401 and "expired" in res.json()["detail"]


def test_roles_are_enforced(client):
    sid = add_supplier(client, "Role Freight")
    supplier_headers = auth(client.post("/api/auth/login", json={"email": "role@test.com",
                                                                 "password": "secret-pass-1"}).json())
    # Suppliers can't create RFQs or add suppliers...
    assert client.post("/api/rfqs", json={}, headers=supplier_headers).status_code == 403
    assert client.post("/api/suppliers", json={"name": "Fake Co"}, headers=supplier_headers).status_code == 403
    # ...and buyers can't bid.
    rfq = make_rfq(client)
    res = client.post(f"/api/rfqs/{rfq['id']}/bids", json={
        "carrier_name": "X", "freight_charges": 1, "transit_time_days": 1, "quote_validity_date": "2099-01-01"})
    assert res.status_code == 403
    assert bid(client, rfq["id"], sid, 500).status_code == 201


def test_supplier_cannot_bid_as_someone_else(client, suppliers):
    """Any supplier_id in the body is ignored: the quote is attributed to the token's supplier."""
    rfq = make_rfq(client)
    res = client.post(f"/api/rfqs/{rfq['id']}/bids", headers=SUPPLIER_HEADERS[suppliers["Alpha"]], json={
        "supplier_id": suppliers["Bravo"], "carrier_name": "Sneaky", "freight_charges": 500,
        "transit_time_days": 1, "quote_validity_date": "2099-01-01"})
    assert res.status_code == 201 and res.json()["bid"]["supplier_id"] == suppliers["Alpha"]


def test_rfq_records_its_buyer(client):
    rfq = make_rfq(client)
    me = client.get("/api/auth/me").json()
    with SessionLocal() as db:
        assert db.get(Rfq, rfq["id"]).created_by_id == me["id"]

