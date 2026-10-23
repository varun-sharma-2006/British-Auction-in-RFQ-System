from app.services.closer import close_due_auctions
from tests.conftest import T0, at, bid, iso, make_rfq


def events(client, rfq_id, kind=None):
    evs = client.get(f"/api/rfqs/{rfq_id}/activity").json()
    return [e for e in evs if kind is None or e["event_type"] == kind]


class TestRfqCreation:
    def test_create_british_auction(self, client):
        rfq = make_rfq(client)
        assert rfq["reference_id"].startswith("RFQ-")
        assert rfq["status"] == "ACTIVE"
        assert rfq["current_close_at"] == rfq["bid_close_at"]
        assert rfq["config"] == {"is_british_auction": True, "trigger_window_minutes": 10,
                                 "extension_minutes": 5, "trigger_type": "BID_RECEIVED"}
        assert events(client, rfq["id"], "RFQ_CREATED")

    def test_forced_close_must_be_after_bid_close(self, client):
        for forced in (60, 30):
            res = client.post("/api/rfqs", json={
                "name": "Bad", "pickup_date": "2030-01-20", "bid_start_at": iso(at(0)),
                "bid_close_at": iso(at(60)), "forced_close_at": iso(at(forced)),
                "trigger_window_minutes": 10, "extension_minutes": 5, "trigger_type": "BID_RECEIVED",
            })
            assert res.status_code == 422
            assert "Forced Bid Close Time must be later than Bid Close Time" in res.json()["detail"]

    def test_british_auction_requires_configuration(self, client):
        res = client.post("/api/rfqs", json={
            "name": "No config", "pickup_date": "2030-01-20", "bid_start_at": iso(at(0)),
            "bid_close_at": iso(at(60)), "forced_close_at": iso(at(90)),
        })
        assert res.status_code == 422 and "Trigger Window" in res.json()["detail"]

    def test_close_must_be_after_start_and_in_future(self, client):
        base = {"name": "Times", "pickup_date": "2030-01-20", "forced_close_at": iso(at(90)),
                "trigger_window_minutes": 10, "extension_minutes": 5, "trigger_type": "BID_RECEIVED"}
        res = client.post("/api/rfqs", json={**base, "bid_start_at": iso(at(30)), "bid_close_at": iso(at(20))})
        assert res.status_code == 422
        res = client.post("/api/rfqs", json={**base, "bid_start_at": iso(at(-60)), "bid_close_at": iso(at(-1))})
        assert res.status_code == 422 and "future" in res.json()["detail"]

    def test_duplicate_reference_id(self, client):
        make_rfq(client, reference_id="LANE-001")
        res = client.post("/api/rfqs", json={
            "name": "Dup", "reference_id": "LANE-001", "pickup_date": "2030-01-20", "bid_start_at": iso(at(0)),
            "bid_close_at": iso(at(60)), "forced_close_at": iso(at(90)),
            "trigger_window_minutes": 10, "extension_minutes": 5, "trigger_type": "BID_RECEIVED",
        })
        assert res.status_code == 409

    def test_plain_rfq_without_british_auction(self, client, suppliers, frozen):
        res = client.post("/api/rfqs", json={
            "name": "Plain", "pickup_date": "2030-01-20", "bid_start_at": iso(at(0)),
            "bid_close_at": iso(at(60)), "is_british_auction": False,
        })
        assert res.status_code == 201
        rfq = res.json()
        assert rfq["forced_close_at"] == rfq["bid_close_at"] and rfq["config"]["trigger_type"] is None
        frozen.set(at(59))
        assert not bid(client, rfq["id"], suppliers["Alpha"], 1000).json()["extended"]


class TestBidding:
    def test_bid_before_start_is_rejected(self, client, suppliers):
        rfq = make_rfq(client, start=10)
        assert rfq["status"] == "SCHEDULED"
        res = bid(client, rfq["id"], suppliers["Alpha"], 1000)
        assert res.status_code == 409 and "not started" in res.json()["detail"]

    def test_total_is_sum_of_charges(self, client, suppliers):
        rfq = make_rfq(client)
        res = bid(client, rfq["id"], suppliers["Alpha"], 1000, origin=150.5, dest=49.5)
        assert res.status_code == 201
        assert float(res.json()["bid"]["total_amount"]) == 1200.0

    def test_supplier_can_only_lower_their_price(self, client, suppliers):
        rfq = make_rfq(client)
        assert bid(client, rfq["id"], suppliers["Alpha"], 1000).status_code == 201
        for same_or_higher in (1000, 1100):
            res = bid(client, rfq["id"], suppliers["Alpha"], same_or_higher)
            assert res.status_code == 422 and "only lower" in res.json()["detail"]
        assert bid(client, rfq["id"], suppliers["Alpha"], 990).status_code == 201

    def test_ranking_sorted_by_price_with_l_labels(self, client, suppliers, frozen):
        rfq = make_rfq(client)
        bid(client, rfq["id"], suppliers["Alpha"], 1000)
        frozen.advance(seconds=1)
        bid(client, rfq["id"], suppliers["Bravo"], 900)
        frozen.advance(seconds=1)
        bid(client, rfq["id"], suppliers["Charlie"], 900)  # ties Bravo but later -> L2
        frozen.advance(seconds=1)
        bid(client, rfq["id"], suppliers["Alpha"], 950)

        detail = client.get(f"/api/rfqs/{rfq['id']}").json()
        ranking = [(q["rank_label"], q["supplier_name"], float(q["total_amount"])) for q in detail["ranking"]]
        assert ranking == [("L1", "Bravo Freight", 900), ("L2", "Charlie Cargo", 900), ("L3", "Alpha Logistics", 950)]
        alpha = detail["ranking"][2]
        assert alpha["bid_count"] == 2 and float(alpha["first_total"]) == 1000
        assert detail["bid_count"] == 4 and float(detail["lowest_bid"]) == 900
        assert len(client.get(f"/api/rfqs/{rfq['id']}/bids").json()) == 4

    def test_validation_errors(self, client, suppliers):
        rfq = make_rfq(client)
        assert bid(client, rfq["id"], suppliers["Alpha"], -5).status_code == 422
        assert bid(client, rfq["id"], suppliers["Alpha"], 0).status_code == 422
        assert bid(client, rfq["id"], suppliers["Alpha"], 100, quote_validity_date="2000-01-01").status_code == 422
        assert bid(client, 9999, suppliers["Alpha"], 100).status_code == 404


class TestExtensions:
    def test_bid_outside_window_does_not_extend(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60, x=10)
        frozen.set(at(45))
        res = bid(client, rfq["id"], suppliers["Alpha"], 1000).json()
        assert not res["extended"]
        assert not events(client, rfq["id"], "AUCTION_EXTENDED")

    def test_bid_received_trigger(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60, forced=90, x=10, y=5, trigger="BID_RECEIVED")
        frozen.set(at(55))  # the "5:55 PM" example
        res = bid(client, rfq["id"], suppliers["Alpha"], 1000).json()
        assert res["extended"] and res["new_close_at"] == iso(at(65))

        ext = events(client, rfq["id"], "AUCTION_EXTENDED")[0]
        assert ext["previous_close_at"] == iso(at(60)) and ext["new_close_at"] == iso(at(65))
        assert "Bid received" in ext["reason"]
        detail = client.get(f"/api/rfqs/{rfq['id']}").json()
        assert detail["current_close_at"] == iso(at(65)) and detail["bid_close_at"] == iso(at(60))
        assert detail["extension_count"] == 1

    def test_window_follows_the_extended_close_time(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60, forced=120, x=10, y=5)
        frozen.set(at(58))
        bid(client, rfq["id"], suppliers["Alpha"], 1000)      # -> close 65
        frozen.set(at(62))                                      # past original close, inside new window
        res = bid(client, rfq["id"], suppliers["Bravo"], 900).json()
        assert res["new_close_at"] == iso(at(70))

    def test_any_rank_change_trigger(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60, trigger="ANY_RANK_CHANGE")
        bid(client, rfq["id"], suppliers["Alpha"], 1000)
        frozen.set(at(52))
        # Bravo enters *last*: nobody moves -> no extension
        assert not bid(client, rfq["id"], suppliers["Bravo"], 1200).json()["extended"]
        # Bravo lowers but still L2 -> no extension
        assert not bid(client, rfq["id"], suppliers["Bravo"], 1100).json()["extended"]
        # Bravo underbids Alpha (the "5:58 PM" example) -> extension
        frozen.set(at(58))
        res = bid(client, rfq["id"], suppliers["Bravo"], 950).json()
        assert res["extended"] and res["rank_label"] == "L1"
        assert "ranking changed" in events(client, rfq["id"], "AUCTION_EXTENDED")[0]["reason"]

    def test_l1_change_trigger(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60, trigger="L1_CHANGE")
        bid(client, rfq["id"], suppliers["Alpha"], 1000)
        bid(client, rfq["id"], suppliers["Bravo"], 1100)
        bid(client, rfq["id"], suppliers["Charlie"], 1200)
        frozen.set(at(55))
        # Charlie overtakes Bravo (L3 -> L2): ranks change but L1 doesn't -> no extension
        assert not bid(client, rfq["id"], suppliers["Charlie"], 1050).json()["extended"]
        # Charlie becomes the new lowest bidder (the "5:59 PM" example) -> extension
        frozen.set(at(59))
        res = bid(client, rfq["id"], suppliers["Charlie"], 990).json()
        assert res["extended"] and res["new_close_at"] == iso(at(65))
        reason = events(client, rfq["id"], "AUCTION_EXTENDED")[0]["reason"]
        assert "Alpha Logistics" in reason and "Charlie Cargo" in reason

    def test_never_extends_beyond_forced_close_and_then_force_closes(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60, forced=68, x=10, y=5)
        frozen.set(at(59))
        assert bid(client, rfq["id"], suppliers["Alpha"], 1000).json()["new_close_at"] == iso(at(65))
        frozen.set(at(63))
        res = bid(client, rfq["id"], suppliers["Bravo"], 990).json()
        assert res["extended"] and res["new_close_at"] == iso(at(68))   # 65+5=70 capped to 68
        frozen.set(at(67))
        res = bid(client, rfq["id"], suppliers["Alpha"], 980).json()
        assert not res["extended"] and res["new_close_at"] == iso(at(68))
        assert events(client, rfq["id"], "EXTENSION_CAPPED")

        frozen.set(at(68))
        res = bid(client, rfq["id"], suppliers["Charlie"], 500)
        assert res.status_code == 409 and "closed" in res.json()["detail"]
        assert client.get(f"/api/rfqs/{rfq['id']}").json()["status"] == "FORCE_CLOSED"
        assert events(client, rfq["id"], "AUCTION_FORCE_CLOSED")

    def test_bid_rejected_after_close(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60)
        frozen.set(at(60))
        assert bid(client, rfq["id"], suppliers["Alpha"], 1000).status_code == 409


class TestListingAndClosing:
    def test_listing_columns_and_live_status(self, client, suppliers, frozen):
        active = make_rfq(client, name="Active lane", close=60)
        make_rfq(client, name="Future lane", start=70, close=90, forced=120)
        bid(client, active["id"], suppliers["Alpha"], 1000)
        bid(client, active["id"], suppliers["Bravo"], 800)

        rows = {r["name"]: r for r in client.get("/api/rfqs").json()}
        a = rows["Active lane"]
        assert a["status"] == "ACTIVE" and float(a["lowest_bid"]) == 800 and a["lowest_bidder"] == "Bravo Freight"
        assert a["current_close_at"] and a["forced_close_at"] and a["bid_count"] == 2 and a["supplier_count"] == 2
        assert rows["Future lane"]["status"] == "SCHEDULED" and rows["Future lane"]["lowest_bid"] is None

        frozen.set(at(61))
        statuses = {r["name"]: r["status"] for r in client.get("/api/rfqs").json()}
        assert statuses == {"Active lane": "CLOSED", "Future lane": "SCHEDULED"}
        assert [r["name"] for r in client.get("/api/rfqs?status=CLOSED").json()] == ["Active lane"]

    def test_closer_persists_status_and_logs_closure(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60)
        bid(client, rfq["id"], suppliers["Alpha"], 1000)
        frozen.set(at(61))
        assert close_due_auctions() == [rfq["id"]]
        assert close_due_auctions() == []      # idempotent
        closed = events(client, rfq["id"], "AUCTION_CLOSED")[0]
        assert closed["occurred_at"] == iso(at(60)) and "Alpha Logistics" in closed["message"]

    def test_metrics(self, client, suppliers, frozen):
        rfq = make_rfq(client, close=60)
        make_rfq(client, close=60)
        bid(client, rfq["id"], suppliers["Alpha"], 1000)  # best opening quote
        bid(client, rfq["id"], suppliers["Bravo"], 1100)
        frozen.set(at(55))
        bid(client, rfq["id"], suppliers["Bravo"], 900)   # in window -> extends; 10% below best opening
        m = client.get("/api/metrics").json()
        assert m["total_auctions"] == 2 and m["total_bids"] == 3 and m["extended_auctions"] == 1
        assert m["avg_bids_per_rfq"] == 1.5 and m["avg_improvement_extended_pct"] == 10.0
        assert m["avg_bids_extended"] == 3 and m["avg_bids_not_extended"] == 0


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["server_time"].startswith(str(T0.date()))


def test_websocket_receives_bid_notification(client, suppliers):
    rfq = make_rfq(client)
    with client.websocket_connect("/ws") as ws:
        bid(client, rfq["id"], suppliers["Alpha"], 1000)
        assert ws.receive_json() == {"type": "rfq_updated", "rfq_id": rfq["id"], "reason": "bid"}



def test_system_endpoint_describes_the_deployment(client, monkeypatch):
    body = client.get("/api/system").json()
    assert body["mode"] == "single" and body["instance"] and body["bloom_filter"] == "in-memory per instance"
    monkeypatch.setenv("VERCEL", "1")
    assert client.get("/api/system").json()["mode"] == "serverless"
