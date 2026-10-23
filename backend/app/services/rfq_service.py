from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import clock
from app.errors import DomainError
from app.models import AuctionEvent, AuctionStatus, Bid, EventType, Rfq, Supplier
from app.schemas import (
    AuctionConfig,
    BidOut,
    EventOut,
    Metrics,
    RankedQuote,
    RfqCreate,
    RfqDetail,
    RfqSummary,
)
from app.services import availability
from app.services.auction_engine import Standing, compute_status, rank

TRIGGER_LABELS = {
    "BID_RECEIVED": "Bid received in last X minutes",
    "ANY_RANK_CHANGE": "Any supplier rank change in last X minutes",
    "L1_CHANGE": "Lowest bidder (L1) change in last X minutes",
}


def live_status(rfq: Rfq, now: datetime | None = None) -> AuctionStatus:
    return compute_status(
        now or clock.utcnow(), rfq.bid_start_at, rfq.current_close_at, rfq.forced_close_at, rfq.is_british_auction
    )


# ---------- create ----------

def create_rfq(db: Session, data: RfqCreate, created_by_id: int | None = None) -> Rfq:
    now = clock.utcnow()
    if data.bid_close_at <= now:
        raise DomainError(422, "Bid Close Time must be in the future")

    rfq = Rfq(
        reference_id=data.reference_id or f"TMP-{now.timestamp()}",
        name=data.name.strip(),
        description=data.description,
        origin=data.origin,
        destination=data.destination,
        currency=data.currency,
        pickup_date=data.pickup_date,
        bid_start_at=data.bid_start_at,
        bid_close_at=data.bid_close_at,
        current_close_at=data.bid_close_at,
        forced_close_at=data.forced_close_at,
        is_british_auction=data.is_british_auction,
        trigger_window_minutes=data.trigger_window_minutes,
        extension_minutes=data.extension_minutes,
        trigger_type=data.trigger_type,
        created_by_id=created_by_id,
    )
    rfq.status = live_status(rfq, now)
    db.add(rfq)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, f"Reference ID '{data.reference_id}' is already in use") from None

    if not data.reference_id:
        rfq.reference_id = f"RFQ-{now.year}-{rfq.id:05d}"

    if rfq.is_british_auction:
        config = (
            f"British Auction · X={rfq.trigger_window_minutes} min, Y={rfq.extension_minutes} min, "
            f"trigger: {TRIGGER_LABELS[rfq.trigger_type.value]}"
        )
    else:
        config = "Standard RFQ (no auto-extension)"
    db.add(AuctionEvent(rfq_id=rfq.id, event_type=EventType.RFQ_CREATED, occurred_at=now,
                        message=f"RFQ {rfq.reference_id} created. {config}"))
    db.commit()
    availability.note_added("reference_id", rfq.reference_id)
    return rfq


# ---------- status transitions (used by the background closer and the bid path) ----------

def sync_status(db: Session, rfq: Rfq, now: datetime) -> bool:
    """Persist the time-derived status and log the transition. Returns True if it changed."""
    new = live_status(rfq, now)
    if new == rfq.status:
        return False

    if new == AuctionStatus.ACTIVE and rfq.status == AuctionStatus.SCHEDULED:
        db.add(AuctionEvent(rfq_id=rfq.id, event_type=EventType.AUCTION_STARTED,
                            occurred_at=rfq.bid_start_at, message="Bidding opened"))
    if new in (AuctionStatus.CLOSED, AuctionStatus.FORCE_CLOSED):
        rfq.closed_at = rfq.current_close_at
        winner = _l1_name(db, rfq.id)
        tail = f" L1: {winner}." if winner else " No bids were received."
        if new == AuctionStatus.FORCE_CLOSED:
            db.add(AuctionEvent(
                rfq_id=rfq.id, event_type=EventType.AUCTION_FORCE_CLOSED, occurred_at=rfq.current_close_at,
                message=f"Auction force-closed at the forced close time after "
                        f"{rfq.extension_count} extension(s).{tail}",
            ))
        else:
            db.add(AuctionEvent(
                rfq_id=rfq.id, event_type=EventType.AUCTION_CLOSED, occurred_at=rfq.current_close_at,
                message=f"Auction closed after {rfq.extension_count} extension(s).{tail}",
            ))
    rfq.status = new
    return True


def _l1_name(db: Session, rfq_id: int) -> str | None:
    bids = db.execute(select(Bid).options(joinedload(Bid.supplier)).where(Bid.rfq_id == rfq_id)).scalars().all()
    standings = _standings(bids)
    if not standings:
        return None
    l1 = rank(list(standings.values()))[0]
    best = standings[l1]
    supplier = next(b.supplier for b in bids if b.supplier_id == l1)
    return f"{supplier.name} @ {best.total:,.2f}"


# ---------- read models ----------

def _standings(bids: list[Bid]) -> dict[int, Standing]:
    best: dict[int, Standing] = {}
    for b in bids:
        cur = best.get(b.supplier_id)
        if cur is None or b.total_amount < cur.total:
            best[b.supplier_id] = Standing(b.supplier_id, b.total_amount, b.created_at)
    return best


def bid_out(b: Bid) -> BidOut:
    return BidOut.model_validate({**_cols(b), "supplier_name": b.supplier.name})


def _cols(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__mapper__.column_attrs}


def ranked_quotes(bids: list[Bid]) -> list[RankedQuote]:
    standings = _standings(bids)
    order = rank(list(standings.values()))
    by_supplier: dict[int, list[Bid]] = defaultdict(list)
    for b in bids:
        by_supplier[b.supplier_id].append(b)

    out = []
    for i, sid in enumerate(order, start=1):
        history = sorted(by_supplier[sid], key=lambda b: b.created_at)
        best = min(history, key=lambda b: (b.total_amount, b.created_at))
        out.append(RankedQuote.model_validate({
            **bid_out(best).model_dump(),
            "rank": i, "rank_label": f"L{i}",
            "bid_count": len(history), "first_total": history[0].total_amount,
        }))
    return out


def list_rfqs(db: Session, status: AuctionStatus | None = None) -> list[RfqSummary]:
    now = clock.utcnow()
    rfqs = db.execute(select(Rfq).order_by(Rfq.created_at.desc())).scalars().all()

    agg = {
        row.rfq_id: row for row in db.execute(
            select(Bid.rfq_id, func.min(Bid.total_amount).label("lowest"), func.count(Bid.id).label("bids"),
                   func.count(func.distinct(Bid.supplier_id)).label("suppliers"))
            .group_by(Bid.rfq_id)
        )
    }
    # L1 per RFQ: lowest total, earliest wins ties (same rule as the engine).
    ranked = (
        select(Bid.rfq_id, Supplier.name,
               func.row_number().over(partition_by=Bid.rfq_id,
                                      order_by=(Bid.total_amount, Bid.created_at, Bid.supplier_id)).label("rn"))
        .join(Supplier, Supplier.id == Bid.supplier_id)
        .subquery()
    )
    leaders = dict(db.execute(select(ranked.c.rfq_id, ranked.c.name).where(ranked.c.rn == 1)).all())

    result = []
    for r in rfqs:
        st = live_status(r, now)
        if status and st != status:
            continue
        a = agg.get(r.id)
        result.append(RfqSummary.model_validate({
            **_cols(r), "status": st,
            "lowest_bid": a.lowest if a else None, "lowest_bidder": leaders.get(r.id),
            "bid_count": a.bids if a else 0, "supplier_count": a.suppliers if a else 0,
        }))
    return result


def get_rfq_or_404(db: Session, rfq_id: int) -> Rfq:
    rfq = db.get(Rfq, rfq_id)
    if rfq is None:
        raise DomainError(404, f"RFQ {rfq_id} not found")
    return rfq


def _rfq_bids(db: Session, rfq_id: int) -> list[Bid]:
    return list(db.execute(
        select(Bid).options(joinedload(Bid.supplier)).where(Bid.rfq_id == rfq_id).order_by(Bid.created_at, Bid.id)
    ).scalars().all())


def rfq_detail(db: Session, rfq_id: int) -> RfqDetail:
    rfq = get_rfq_or_404(db, rfq_id)
    now = clock.utcnow()
    bids = _rfq_bids(db, rfq_id)
    ranking = ranked_quotes(bids)
    return RfqDetail.model_validate({
        **_cols(rfq),
        "status": live_status(rfq, now),
        "lowest_bid": ranking[0].total_amount if ranking else None,
        "lowest_bidder": ranking[0].supplier_name if ranking else None,
        "bid_count": len(bids),
        "supplier_count": len(ranking),
        "config": AuctionConfig(
            is_british_auction=rfq.is_british_auction, trigger_window_minutes=rfq.trigger_window_minutes,
            extension_minutes=rfq.extension_minutes, trigger_type=rfq.trigger_type,
        ),
        "ranking": ranking,
        "server_time": now,
    })


def rfq_bids(db: Session, rfq_id: int) -> list[BidOut]:
    get_rfq_or_404(db, rfq_id)
    return [bid_out(b) for b in reversed(_rfq_bids(db, rfq_id))]


def rfq_activity(db: Session, rfq_id: int) -> list[EventOut]:
    get_rfq_or_404(db, rfq_id)
    events = db.execute(
        select(AuctionEvent).options(joinedload(AuctionEvent.supplier))
        .where(AuctionEvent.rfq_id == rfq_id).order_by(AuctionEvent.occurred_at.desc(), AuctionEvent.id.desc())
    ).scalars().all()
    return [EventOut.model_validate({**_cols(e), "supplier_name": e.supplier.name if e.supplier else None})
            for e in events]


# ---------- metrics (assignment §4: bids per RFQ, price improvement vs. non-extended) ----------

def metrics(db: Session) -> Metrics:
    now = clock.utcnow()
    rfqs = db.execute(select(Rfq)).scalars().all()
    bids = db.execute(select(Bid).order_by(Bid.created_at, Bid.id)).scalars().all()
    by_rfq: dict[int, list[Bid]] = defaultdict(list)
    for b in bids:
        by_rfq[b.rfq_id].append(b)

    def avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    counts_ext, counts_flat, imp_all, imp_ext, imp_flat = [], [], [], [], []
    for r in rfqs:
        rb = by_rfq.get(r.id, [])
        extended = r.extension_count > 0
        (counts_ext if extended else counts_flat).append(len(rb))
        if not rb:
            continue
        # Improvement = how far competition pushed the price below the best *opening* quote.
        firsts: dict[int, Decimal] = {}
        for b in rb:
            firsts.setdefault(b.supplier_id, b.total_amount)
        best_opening = min(firsts.values())
        final_l1 = min(b.total_amount for b in rb)
        pct = float((best_opening - final_l1) / best_opening * 100)
        imp_all.append(pct)
        (imp_ext if extended else imp_flat).append(pct)

    return Metrics(
        total_auctions=len(rfqs),
        active_auctions=sum(1 for r in rfqs if live_status(r, now) == AuctionStatus.ACTIVE),
        total_bids=len(bids),
        avg_bids_per_rfq=round(len(bids) / len(rfqs), 2) if rfqs else 0.0,
        extended_auctions=len(counts_ext),
        avg_bids_extended=avg(counts_ext),
        avg_bids_not_extended=avg(counts_flat),
        avg_price_improvement_pct=avg(imp_all),
        avg_improvement_extended_pct=avg(imp_ext),
        avg_improvement_not_extended_pct=avg(imp_flat),
    )
