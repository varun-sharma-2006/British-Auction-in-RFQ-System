"""Load realistic demo data.

Rather than inserting rows by hand, this *replays* auctions through the real
services with a simulated clock, so every extension, cap and closure in the
demo data was produced by the same engine the API uses.

    python -m scripts.seed            # adds demo data
    python -m scripts.seed --reset    # wipes all tables first

Demo logins (password for all: demo1234):
    buyer@demo.com                      buyer
    bluedart@demo.com, delhivery@demo.com, gati@demo.com,
    tci@demo.com, rivigo@demo.com, vrl@demo.com      suppliers
"""
import argparse
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from app import clock
from app.db import SessionLocal
from app.models import AuctionEvent, Bid, Rfq, Supplier, TriggerType, User, UserRole
from app.schemas import BidCreate, RfqCreate
from app.security import hash_password
from app.services.bidding import submit_bid
from app.services.closer import close_due_auctions
from app.services.rfq_service import create_rfq

DEMO_PASSWORD = "demo1234"

SUPPLIERS = [
    ("BlueDart Logistics", "bids@bluedart.example"),
    ("Delhivery Freight", "rfq@delhivery.example"),
    ("Gati Express", "sales@gati.example"),
    ("TCI Freight", "quotes@tci.example"),
    ("Rivigo Transport", "rfq@rivigo.example"),
    ("VRL Logistics", "bids@vrl.example"),
]


class SimClock:
    def __init__(self, t: datetime):
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def _ensure_user(db, email, full_name, role, supplier_id):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=full_name, role=role, supplier_id=supplier_id,
                    password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
    return user


def run(reset: bool, if_empty: bool = False) -> None:
    real_now = datetime.now(UTC).replace(second=0, microsecond=0)
    sim = SimClock(real_now)
    real_utcnow = clock.utcnow
    clock.utcnow = sim

    try:
        with SessionLocal() as db:
            if if_empty and db.execute(select(Rfq.id).limit(1)).first():
                print("Database already has data; skipping demo seed.")
                return
            if reset:
                for model in (AuctionEvent, Bid, Rfq, User, Supplier):
                    db.execute(delete(model))
                db.commit()

            sup = {}
            for name, email in SUPPLIERS:
                s = db.execute(select(Supplier).where(Supplier.name == name)).scalar_one_or_none()
                if s is None:
                    s = Supplier(name=name, contact_email=email)
                    db.add(s)
                    db.flush()
                sup[name.split()[0]] = s.id
                _ensure_user(db, f"{name.split()[0].lower()}@demo.com", f"{name.split()[0]} Bid Desk",
                             UserRole.SUPPLIER, s.id)
            buyer = _ensure_user(db, "buyer@demo.com", "Priya Buyer", UserRole.BUYER, None)
            db.commit()

            def auction(t_create, *, name, start, close, forced, x=10, y=5, trigger=TriggerType.BID_RECEIVED,
                        origin, destination, british=True, desc=None):
                sim.t = t_create
                return create_rfq(db, created_by_id=buyer.id, data=RfqCreate(
                    name=name, description=desc, origin=origin, destination=destination,
                    pickup_date=(close + timedelta(days=4)).date(),
                    bid_start_at=start, bid_close_at=close, forced_close_at=forced if british else None,
                    is_british_auction=british, trigger_window_minutes=x if british else None,
                    extension_minutes=y if british else None, trigger_type=trigger if british else None,
                ))

            def place(rfq, at, who, freight, origin_c, dest_c, carrier, transit, validity_days=30):
                sim.t = at
                submit_bid(db, rfq.id, sup[who], BidCreate(
                    carrier_name=carrier, freight_charges=Decimal(freight),
                    origin_charges=Decimal(origin_c), destination_charges=Decimal(dest_c),
                    transit_time_days=transit, quote_validity_date=date.today() + timedelta(days=validity_days),
                ))

            m = lambda base, minutes: base + timedelta(minutes=minutes)  # noqa: E731

            # 1) Closed two days ago, extended twice by L1 changes.
            c = real_now - timedelta(days=2)
            r = auction(m(c, -180), name="Mumbai -> Delhi | 20ft container, FTL", origin="Nhava Sheva, Mumbai",
                        destination="ICD Tughlakabad, Delhi", start=m(c, -120), close=c, forced=m(c, 30),
                        trigger=TriggerType.L1_CHANGE, desc="Weekly FTL lane, 18 tonnes, palletised FMCG.")
            place(r, m(c, -110), "BlueDart", 84000, 4500, 3500, "BlueDart Surface", 3)
            place(r, m(c, -95), "Delhivery", 81000, 4000, 3500, "Delhivery Part-Truck", 3)
            place(r, m(c, -60), "Gati", 86000, 3000, 3000, "Gati Surface Express", 4)
            place(r, m(c, -30), "BlueDart", 79500, 4000, 3500, "BlueDart Surface", 3)
            place(r, m(c, -6), "Delhivery", 78000, 4000, 3000, "Delhivery Part-Truck", 3)    # new L1 -> +5
            place(r, m(c, -2), "Gati", 80500, 3000, 2500, "Gati Surface Express", 4)        # L3->L2, L1 same -> no ext
            place(r, m(c, 3), "BlueDart", 76000, 4000, 3500, "BlueDart Surface", 3)         # new L1 -> +5
            place(r, m(c, 8), "Gati", 79000, 3000, 2500, "Gati Surface Express", 4)        # still L2 -> no ext

            # 2) Yesterday: a bidding war that ran into the forced close.
            c = real_now - timedelta(days=1)
            r = auction(m(c, -150), name="Chennai -> Bengaluru | Reefer 32ft", origin="Chennai Port",
                        destination="Bengaluru (Hoskote)", start=m(c, -90), close=c, forced=m(c, 12), x=10, y=5,
                        desc="Temperature-controlled (2-8 C) pharma consignment.")
            place(r, m(c, -80), "TCI", 52000, 2500, 2000, "TCI Reefer", 1)
            place(r, m(c, -50), "Rivigo", 50500, 2500, 2000, "Rivigo Relay Reefer", 1)
            place(r, m(c, -8), "TCI", 49800, 2200, 2000, "TCI Reefer", 1)       # close c -> c+5
            place(r, m(c, 2), "Rivigo", 48900, 2200, 2000, "Rivigo Relay Reefer", 1)  # c+5 -> c+10
            place(r, m(c, 9), "TCI", 48500, 2000, 2000, "TCI Reefer", 1)        # c+10 -> c+12, capped at forced
            place(r, m(c, 11), "VRL", 49000, 2000, 1800, "VRL Reefer", 2)       # at forced close: no room left

            # 3) Live: closes in ~25 minutes, any-rank-change trigger.
            c = m(real_now, 25)
            r = auction(m(real_now, -120), name="Ahmedabad -> Kolkata | 2 x 40ft HC", origin="Ahmedabad (Sanand)",
                        destination="Kolkata (Dankuni)", start=m(real_now, -60), close=c, forced=m(c, 30),
                        trigger=TriggerType.ANY_RANK_CHANGE, x=10, y=5,
                        desc="Auto components, 2 x 40ft HC, loading on pickup date morning.")
            place(r, m(real_now, -55), "VRL", 142000, 6000, 5500, "VRL Long Haul", 5)
            place(r, m(real_now, -40), "Gati", 139000, 6500, 5000, "Gati Surface Express", 6)
            place(r, m(real_now, -25), "TCI", 145000, 5000, 5000, "TCI Freight", 5)
            place(r, m(real_now, -10), "VRL", 137500, 6000, 5500, "VRL Long Haul", 5)

            # 4) Live: inside the trigger window right now, so any bid extends it.
            c = m(real_now, 7)
            r = auction(m(real_now, -90), name="Pune -> Hyderabad | 14ft LCV, express", origin="Chakan, Pune",
                        destination="Hyderabad (Shamshabad)", start=m(real_now, -45), close=c, forced=m(c, 20),
                        trigger=TriggerType.BID_RECEIVED, x=10, y=3,
                        desc="Electronics, time-critical. Try bidding now to watch it extend.")
            place(r, m(real_now, -40), "Rivigo", 31000, 1500, 1200, "Rivigo Express", 2)
            place(r, m(real_now, -20), "BlueDart", 30500, 1800, 1200, "BlueDart Apex", 1)

            # 5) Scheduled: opens in 2 hours.
            s = m(real_now, 120)
            auction(real_now, name="Ludhiana -> Mundra | Export FCL 40ft", origin="Ludhiana ICD",
                    destination="Mundra Port",
                    start=s, close=m(s, 120), forced=m(s, 180), trigger=TriggerType.L1_CHANGE, x=15, y=10,
                    desc="Export textiles, vessel cut-off 3 days after pickup.")

            # 6) A plain RFQ (British Auction disabled) for comparison in the metrics.
            c = m(real_now, 180)
            r = auction(m(real_now, -30), name="Jaipur -> Indore | Part load 3T", origin="Jaipur (Sitapura)",
                        destination="Indore (Pithampur)", start=m(real_now, -20), close=c, forced=c, british=False)
            place(r, m(real_now, -15), "VRL", 21000, 900, 800, "VRL Part Load", 3)
            place(r, m(real_now, -5), "Gati", 22500, 700, 700, "Gati PTL", 2)

        sim.t = datetime.now(UTC)
        close_due_auctions()
    finally:
        clock.utcnow = real_utcnow
    print("Seeded 6 auctions (closed, force-closed, 3 active, 1 scheduled).")
    print(f"Log in as buyer@demo.com or bluedart@demo.com / gati@demo.com / ... with password '{DEMO_PASSWORD}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    parser.add_argument("--if-empty", action="store_true", help="only seed a database that has no RFQs yet")
    args = parser.parse_args()
    run(args.reset, args.if_empty)
