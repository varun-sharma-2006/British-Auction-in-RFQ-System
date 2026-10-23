from tests.conftest import SUPPLIER_HEADERS, at, auth, bid, make_rfq, register


def test_buyer_dashboard_shows_only_my_rfqs_with_savings(client, suppliers, frozen):
    mine = make_rfq(client, close=60)
    other_buyer = auth(register(client, "other.buyer@test.com"))
    client.post("/api/rfqs", headers=other_buyer, json={
        "name": "Not mine", "pickup_date": "2030-01-20", "bid_start_at": "2030-01-15T11:00:00Z",
        "bid_close_at": "2030-01-15T13:00:00Z", "is_british_auction": False})
    bid(client, mine["id"], suppliers["Alpha"], 1000)      # best opening quote
    bid(client, mine["id"], suppliers["Bravo"], 1100)
    bid(client, mine["id"], suppliers["Bravo"], 900)       # 10% below the best opening

    d = client.get("/api/dashboard/buyer").json()
    assert d["total_rfqs"] == 1 and d["active"] == 1 and d["bids_received"] == 3
    row = d["rfqs"][0]
    assert row["name"] == "Mumbai -> Delhi FTL" and row["lowest_bidder"] == "Bravo Freight"
    assert float(row["best_opening"]) == 1000 and float(row["savings_amount"]) == 100 and row["savings_pct"] == 10.0
    assert float(d["savings_total"]) == 100 and d["avg_savings_pct"] == 10.0
    assert d["activity"][0]["event_type"] == "BID_SUBMITTED" and d["activity"][0]["rfq_name"] == row["name"]


def test_supplier_dashboard_positions_and_open_auctions(client, suppliers, frozen):
    a = make_rfq(client, name="Lane A", close=60)
    b = make_rfq(client, name="Lane B", close=30)
    make_rfq(client, name="Lane C", close=90, forced=120)
    bid(client, a["id"], suppliers["Alpha"], 1000)
    bid(client, a["id"], suppliers["Bravo"], 900)          # Alpha outbid on A
    bid(client, b["id"], suppliers["Alpha"], 500)          # Alpha leads B

    alpha = client.get("/api/dashboard/supplier", headers=_headers(suppliers["Alpha"])).json()
    assert (alpha["participating"], alpha["leading"], alpha["outbid"], alpha["open_to_join"]) == (2, 1, 1, 1)
    rows = {r["name"]: r for r in alpha["my_auctions"]}
    assert rows["Lane A"]["position"] == "OUTBID" and rows["Lane A"]["my_rank_label"] == "L2"
    assert float(rows["Lane A"]["gap_to_l1"]) == 100
    assert rows["Lane B"]["position"] == "LEADING" and float(rows["Lane B"]["gap_to_l1"]) == 0
    assert [r["name"] for r in alpha["my_auctions"]] == ["Lane B", "Lane A"]   # soonest closing first
    assert [r["name"] for r in alpha["open_auctions"]] == ["Lane C"]

    frozen.set(at(61))                                     # A and B have closed
    alpha = client.get("/api/dashboard/supplier", headers=_headers(suppliers["Alpha"])).json()
    assert (alpha["won"], alpha["lost"], alpha["participating"]) == (1, 1, 0)


def test_dashboards_are_role_specific(client, suppliers):
    assert client.get("/api/dashboard/supplier").status_code == 403          # the client is a buyer
    assert client.get("/api/dashboard/buyer", headers=_headers(suppliers["Alpha"])).status_code == 403


def _headers(supplier_id):
    return SUPPLIER_HEADERS[supplier_id]
