"""Demo bot: keeps undercutting the current L1 on an active auction so you can
watch ranks flip and the close time extend live in the UI.

    python -m scripts.simulate_bidding                 # first active British auction
    python -m scripts.simulate_bidding --rfq 4 --every 8
"""
import argparse
import random
import time
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

import httpx


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://localhost:8000/api")
    p.add_argument("--rfq", type=int, help="RFQ id (default: first ACTIVE British auction)")
    p.add_argument("--every", type=float, default=10.0, help="seconds between bids")
    args = p.parse_args()

    api = httpx.Client(base_url=args.api, timeout=10)
    rfq_id = args.rfq or next(
        (r["id"] for r in api.get("/rfqs", params={"status": "ACTIVE"}).json() if r["is_british_auction"]), None
    )
    if rfq_id is None:
        raise SystemExit("No active British auction found. Create one (or run scripts.seed) first.")
    suppliers = api.get("/suppliers").json()

    while True:
        rfq = api.get(f"/rfqs/{rfq_id}").json()
        if rfq["status"] != "ACTIVE":
            print(f"RFQ {rfq['reference_id']} is {rfq['status']}. Done.")
            return
        ranking = rfq["ranking"]
        leader = ranking[0]["supplier_id"] if ranking else None
        bidder = random.choice([s for s in suppliers if s["id"] != leader])
        mine = next((q for q in ranking if q["supplier_id"] == bidder["id"]), None)
        target = Decimal(ranking[0]["total_amount"]) if ranking else Decimal(random.randint(40_000, 90_000))
        if mine:
            target = min(target, Decimal(mine["total_amount"]))
        total = (target * Decimal(1 - random.uniform(0.005, 0.02))).quantize(Decimal("1"), ROUND_DOWN)
        origin, dest = (total * Decimal("0.05")).quantize(Decimal("1")), (total * Decimal("0.04")).quantize(Decimal("1"))

        res = api.post(f"/rfqs/{rfq_id}/bids", json={
            "supplier_id": bidder["id"], "carrier_name": f"{bidder['name'].split()[0]} Line-haul",
            "freight_charges": str(total - origin - dest), "origin_charges": str(origin),
            "destination_charges": str(dest), "transit_time_days": random.randint(2, 6),
            "quote_validity_date": (date.today() + timedelta(days=30)).isoformat(),
        })
        body = res.json()
        if res.status_code == 201:
            ext = f"  EXTENDED -> {body['new_close_at']}" if body["extended"] else ""
            print(f"{bidder['name']:<22} {total:>12,} -> {body['rank_label']}{ext}")
        else:
            print(f"{bidder['name']:<22} rejected: {body.get('detail')}")
        time.sleep(args.every)


if __name__ == "__main__":
    main()
