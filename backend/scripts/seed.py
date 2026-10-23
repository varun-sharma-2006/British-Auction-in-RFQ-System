"""Load realistic demo data.

Rather than inserting rows by hand, this *replays* auctions through the real services with explicit
timestamps, so every extension, cap and closure in the demo data was produced by the same engine the
API uses.

    python -m scripts.seed              # adds demo data
    python -m scripts.seed --reset      # wipes all tables first
    python -m scripts.seed --if-empty   # only on a database with no RFQs yet (used at deploy time)

Demo logins (password for all: demo1234):
    buyer@demo.com                                        buyer
    bluedart@demo.com, delhivery@demo.com, gati@demo.com,
    tci@demo.com, rivigo@demo.com, vrl@demo.com           suppliers

With SEED_DEMO=true the running API also tops the demo up with fresh live auctions whenever fewer
than two are still open (app/services/demo.py), so a deployed demo never goes stale.
"""
import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import AuctionEvent, Bid, Rfq, Supplier, TriggerType, User
from app.services import availability
from app.services.closer import close_due_auctions
from app.services.demo import DEMO_PASSWORD, SUPPLIERS, Builder, add_live_auctions, ensure_accounts

__all__ = ["DEMO_PASSWORD", "SUPPLIERS", "run"]   # simulate_bidding.py imports these


def run(reset: bool, if_empty: bool = False) -> None:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    m = lambda base, minutes: base + timedelta(minutes=minutes)  # noqa: E731

    with SessionLocal() as db:
        if if_empty and db.execute(select(Rfq.id).limit(1)).first():
            print("Database already has data; skipping demo seed.")
            return
        if reset:
            for model in (AuctionEvent, Bid, Rfq, User, Supplier):
                db.execute(delete(model))
            db.commit()

        buyer, sup = ensure_accounts(db)
        b = Builder(db, buyer, sup)

        # 1) Closed two days ago, extended twice by L1 changes.
        c = now - timedelta(days=2)
        r = b.auction(m(c, -180), name="Mumbai -> Delhi | 20ft container, FTL", origin="Nhava Sheva, Mumbai",
                      destination="ICD Tughlakabad, Delhi", start=m(c, -120), close=c, forced=m(c, 30),
                      trigger=TriggerType.L1_CHANGE, desc="Weekly FTL lane, 18 tonnes, palletised FMCG.")
        b.bid(r, m(c, -110), "BlueDart", 84000, 4500, 3500, "BlueDart Surface", 3)
        b.bid(r, m(c, -95), "Delhivery", 81000, 4000, 3500, "Delhivery Part-Truck", 3)
        b.bid(r, m(c, -60), "Gati", 86000, 3000, 3000, "Gati Surface Express", 4)
        b.bid(r, m(c, -30), "BlueDart", 79500, 4000, 3500, "BlueDart Surface", 3)
        b.bid(r, m(c, -6), "Delhivery", 78000, 4000, 3000, "Delhivery Part-Truck", 3)    # new L1 -> +5
        b.bid(r, m(c, -2), "Gati", 80500, 3000, 2500, "Gati Surface Express", 4)        # L3->L2, L1 same -> no ext
        b.bid(r, m(c, 3), "BlueDart", 76000, 4000, 3500, "BlueDart Surface", 3)         # new L1 -> +5
        b.bid(r, m(c, 8), "Gati", 79000, 3000, 2500, "Gati Surface Express", 4)         # still L2 -> no ext

        # 2) Yesterday: a bidding war that ran into the forced close.
        c = now - timedelta(days=1)
        r = b.auction(m(c, -150), name="Chennai -> Bengaluru | Reefer 32ft", origin="Chennai Port",
                      destination="Bengaluru (Hoskote)", start=m(c, -90), close=c, forced=m(c, 12), x=10, y=5,
                      desc="Temperature-controlled (2-8 C) pharma consignment.")
        b.bid(r, m(c, -80), "TCI", 52000, 2500, 2000, "TCI Reefer", 1)
        b.bid(r, m(c, -50), "Rivigo", 50500, 2500, 2000, "Rivigo Relay Reefer", 1)
        b.bid(r, m(c, -8), "TCI", 49800, 2200, 2000, "TCI Reefer", 1)       # close c -> c+5
        b.bid(r, m(c, 2), "Rivigo", 48900, 2200, 2000, "Rivigo Relay Reefer", 1)  # c+5 -> c+10
        b.bid(r, m(c, 9), "TCI", 48500, 2000, 2000, "TCI Reefer", 1)        # c+10 -> c+12, capped at forced
        b.bid(r, m(c, 11), "VRL", 49000, 2000, 1800, "VRL Reefer", 2)       # at forced close: no room left

        # 3-6) Live auctions at different stages + one scheduled (same set the API uses to refresh the demo).
        add_live_auctions(db, now)

        # 7) A plain RFQ (British Auction disabled) for comparison in the metrics.
        r = b.auction(m(now, -30), name="Jaipur -> Indore | Part load 3T", origin="Jaipur (Sitapura)",
                      destination="Indore (Pithampur)", start=m(now, -20), close=m(now, 180), british=False)
        b.bid(r, m(now, -15), "VRL", 21000, 900, 800, "VRL Part Load", 3)
        b.bid(r, m(now, -5), "Gati", 22500, 700, 700, "Gati PTL", 2)

    close_due_auctions()
    with SessionLocal() as db:
        # Refresh the availability Bloom filters (shared via Redis when configured).
        availability.rebuild_all(db)
    print("Seeded 7 auctions (closed, force-closed, 3 live, 1 scheduled, 1 standard RFQ).")
    print(f"Log in as buyer@demo.com or bluedart@demo.com / gati@demo.com / ... with password '{DEMO_PASSWORD}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    parser.add_argument("--if-empty", action="store_true", help="only seed a database that has no RFQs yet")
    args = parser.parse_args()
    run(args.reset, args.if_empty)
