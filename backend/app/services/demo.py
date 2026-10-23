"""Demo data that stays alive.

Auctions end, so a demo seeded once is all "Closed" a few hours later. When SEED_DEMO is on, the API
checks (at most once a minute) whether fewer than two British auctions are still open, and if so starts a
fresh set: live ones at different stages, one about to enter its trigger window, and one scheduled. Each
gets realistic bids from the demo suppliers. Everything goes through the real services, with explicit
timestamps, so ranks, events and extensions are exactly what the engine would produce.
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import count

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Rfq, Supplier, TriggerType, User, UserRole
from app.schemas import BidCreate, RfqCreate
from app.security import hash_password
from app.services.bidding import submit_bid
from app.services.rfq_service import create_rfq

log = logging.getLogger(__name__)

DEMO_PASSWORD = "demo1234"
BUYER_EMAIL = "buyer@demo.com"
SUPPLIERS = [
    ("BlueDart Logistics", "bids@bluedart.example"),
    ("Delhivery Freight", "rfq@delhivery.example"),
    ("Gati Express", "sales@gati.example"),
    ("TCI Freight", "quotes@tci.example"),
    ("Rivigo Transport", "rfq@rivigo.example"),
    ("VRL Logistics", "bids@vrl.example"),
]

# Lanes for refreshed rounds: (name, origin, destination, description)
LANES = [
    ("Ahmedabad → Kolkata | 2 x 40ft HC", "Ahmedabad (Sanand)", "Kolkata (Dankuni)",
     "Auto components, 2 x 40ft HC, loading on pickup date morning."),
    ("Pune → Hyderabad | 14ft LCV, express", "Chakan, Pune", "Hyderabad (Shamshabad)",
     "Electronics, time-critical. Bid now to watch it extend."),
    ("Nagpur → Surat | 32ft MXL", "Nagpur (MIHAN)", "Surat (Sachin GIDC)", "Synthetic yarn, 14 tonnes, palletised."),
    ("Ludhiana → Mundra | Export FCL 40ft", "Ludhiana ICD", "Mundra Port",
     "Export textiles, vessel cut-off 3 days after pickup."),
    ("Bengaluru → Chennai | Reefer 20ft", "Bengaluru (Hoskote)", "Chennai Port",
     "Temperature-controlled (2-8 C) vaccines."),
    ("Indore → Delhi | Part load 6T", "Indore (Pithampur)", "Delhi (Okhla)", "FMCG cartons, tail-lift required."),
]


def short(name: str) -> str:
    return name.split()[0]


def ensure_accounts(db: Session) -> tuple[User, dict[str, int]]:
    """Demo buyer + supplier companies and logins (idempotent)."""
    sup = {}
    for name, email in SUPPLIERS:
        s = db.execute(select(Supplier).where(Supplier.name == name)).scalar_one_or_none()
        if s is None:
            s = Supplier(name=name, contact_email=email)
            db.add(s)
            db.flush()
        sup[short(name)] = s.id
        _ensure_user(db, f"{short(name).lower()}@demo.com", f"{short(name)} Bid Desk", UserRole.SUPPLIER, s.id)
    buyer = _ensure_user(db, BUYER_EMAIL, "Priya Buyer", UserRole.BUYER, None)
    db.commit()
    return buyer, sup


def _ensure_user(db: Session, email: str, full_name: str, role: UserRole, supplier_id: int | None) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=full_name, role=role, supplier_id=supplier_id,
                    password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
    return user


class Builder:
    """Creates auctions and bids at chosen moments through the real services."""

    def __init__(self, db: Session, buyer: User, suppliers: dict[str, int]):
        self.db, self.buyer, self.sup = db, buyer, suppliers

    def auction(self, created: datetime, *, name, origin, destination, start, close, forced=None,
                trigger=TriggerType.BID_RECEIVED, x=10, y=5, desc=None, british=True) -> Rfq:
        return create_rfq(self.db, RfqCreate(
            name=name, description=desc, origin=origin, destination=destination,
            pickup_date=(close + timedelta(days=4)).date(), bid_start_at=start, bid_close_at=close,
            forced_close_at=forced if british else None, is_british_auction=british,
            trigger_window_minutes=x if british else None, extension_minutes=y if british else None,
            trigger_type=trigger if british else None,
        ), created_by_id=self.buyer.id, now=created)

    def bid(self, rfq: Rfq, at: datetime, who: str, freight, origin, dest, carrier: str, transit: int) -> None:
        submit_bid(self.db, rfq.id, self.sup[who], BidCreate(
            carrier_name=carrier, freight_charges=Decimal(freight), origin_charges=Decimal(origin),
            destination_charges=Decimal(dest), transit_time_days=transit,
            quote_validity_date=date.today() + timedelta(days=30),
        ), now=at)


def add_live_auctions(db: Session, now: datetime, round_no: int = 0) -> int:
    """Start a fresh set of open auctions around `now`. Returns how many were created."""
    buyer, sup = ensure_accounts(db)
    b = Builder(db, buyer, sup)
    lanes = (LANES[(round_no * 4 + i) % len(LANES)] for i in count())
    m = lambda base, minutes: base + timedelta(minutes=minutes)  # noqa: E731

    # 1) Live, closes in ~45 min, any-rank-change trigger, a real bidding war so far.
    name, o, d, desc = next(lanes)
    r = b.auction(m(now, -70), name=name, origin=o, destination=d, desc=desc, start=m(now, -60), close=m(now, 45),
                  forced=m(now, 75), trigger=TriggerType.ANY_RANK_CHANGE)
    b.bid(r, m(now, -55), "VRL", 142000, 6000, 5500, "VRL Long Haul", 5)
    b.bid(r, m(now, -40), "Gati", 139000, 6500, 5000, "Gati Surface Express", 6)
    b.bid(r, m(now, -25), "TCI", 145000, 5000, 5000, "TCI Freight", 5)
    b.bid(r, m(now, -10), "VRL", 137500, 6000, 5500, "VRL Long Haul", 5)

    # 2) Enters its 10-minute trigger window in ~2 minutes: any bid will visibly extend it.
    name, o, d, desc = next(lanes)
    r = b.auction(m(now, -50), name=name, origin=o, destination=d, desc=desc, start=m(now, -40), close=m(now, 12),
                  forced=m(now, 40), trigger=TriggerType.BID_RECEIVED, x=10, y=3)
    b.bid(r, m(now, -35), "Rivigo", 31000, 1500, 1200, "Rivigo Express", 2)
    b.bid(r, m(now, -15), "BlueDart", 30500, 1800, 1200, "BlueDart Apex", 1)

    # 3) Long-running L1-change auction, closes in ~4 h.
    name, o, d, desc = next(lanes)
    r = b.auction(m(now, -30), name=name, origin=o, destination=d, desc=desc, start=m(now, -20), close=m(now, 240),
                  forced=m(now, 300), trigger=TriggerType.L1_CHANGE, x=15, y=10)
    b.bid(r, m(now, -18), "Delhivery", 64000, 2500, 2000, "Delhivery Part-Truck", 3)
    b.bid(r, m(now, -6), "BlueDart", 62500, 2800, 2200, "BlueDart Surface", 3)

    # 4) Scheduled: opens in 30 min.
    name, o, d, desc = next(lanes)
    b.auction(now, name=name, origin=o, destination=d, desc=desc, start=m(now, 30), close=m(now, 210),
              forced=m(now, 270), trigger=TriggerType.L1_CHANGE, x=15, y=10)
    return 4


def ensure_live_demo(db: Session, now: datetime) -> bool:
    """Top up the demo when fewer than two British auctions are still open. Returns True if it added some."""
    engine = db.get_bind()
    if engine.dialect.name != "postgresql":
        return _top_up(db, now)
    # Serverless instances or replicas may all notice at once: a session-level advisory lock, held on its own
    # connection for the whole refresh (creating auctions commits several times), lets exactly one do it.
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("SELECT pg_try_advisory_lock(424242)")).scalar():
            return False
        try:
            return _top_up(db, now)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(424242)"))
            lock_conn.commit()


def _top_up(db: Session, now: datetime) -> bool:
    if db.execute(select(User.id).where(User.email == BUYER_EMAIL)).first() is None:
        return False   # demo accounts were never seeded: this isn't a demo database
    open_auctions = db.execute(
        select(func.count()).select_from(Rfq).where(Rfq.is_british_auction, Rfq.current_close_at > now)
    ).scalar_one()
    if open_auctions >= 2:
        return False
    rounds = db.execute(select(func.count()).select_from(Rfq)).scalar_one() // 4
    add_live_auctions(db, now, round_no=rounds)
    log.info("Demo refreshed with new live auctions")
    return True
