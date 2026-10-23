"""Role-specific home screens: what a buyer and what a supplier needs to see first."""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import clock
from app.models import AuctionEvent, AuctionStatus, Bid, Rfq
from app.schemas import (
    BuyerDashboard,
    BuyerRfqRow,
    DashboardEvent,
    RfqSummary,
    SupplierAuctionRow,
    SupplierDashboard,
)
from app.services.rfq_service import _cols, live_status, ranked_quotes

OPEN = (AuctionStatus.ACTIVE, AuctionStatus.SCHEDULED)
# (auction still open?, am I L1?) -> what the supplier should know at a glance
POSITION = {(True, True): "LEADING", (True, False): "OUTBID", (False, True): "WON", (False, False): "LOST"}


def _bids_by_rfq(db: Session, rfq_ids: list[int]) -> dict[int, list[Bid]]:
    out: dict[int, list[Bid]] = defaultdict(list)
    if rfq_ids:
        rows = db.execute(select(Bid).options(joinedload(Bid.supplier)).where(Bid.rfq_id.in_(rfq_ids))
                          .order_by(Bid.created_at, Bid.id)).scalars()
        for b in rows:
            out[b.rfq_id].append(b)
    return out


def _summary(rfq: Rfq, status: AuctionStatus, bids: list[Bid]) -> dict:
    ranking = ranked_quotes(bids)
    return {
        **_cols(rfq), "status": status,
        "lowest_bid": ranking[0].total_amount if ranking else None,
        "lowest_bidder": ranking[0].supplier_name if ranking else None,
        "bid_count": len(bids), "supplier_count": len(ranking),
    }


def _best_opening(bids: list[Bid]) -> Decimal | None:
    firsts: dict[int, Decimal] = {}
    for b in bids:
        firsts.setdefault(b.supplier_id, b.total_amount)
    return min(firsts.values()) if firsts else None


def _activity(db: Session, rfq_ids: list[int], limit: int = 12) -> list[DashboardEvent]:
    if not rfq_ids:
        return []
    rows = db.execute(
        select(AuctionEvent, Rfq.name, Rfq.reference_id).join(Rfq, Rfq.id == AuctionEvent.rfq_id)
        .where(AuctionEvent.rfq_id.in_(rfq_ids))
        .order_by(AuctionEvent.occurred_at.desc(), AuctionEvent.id.desc()).limit(limit)
    ).all()
    return [DashboardEvent(id=e.id, rfq_id=e.rfq_id, rfq_name=name, reference_id=ref, event_type=e.event_type,
                           occurred_at=e.occurred_at, message=e.message, reason=e.reason)
            for e, name, ref in rows]


def buyer_dashboard(db: Session, buyer_id: int) -> BuyerDashboard:
    now = clock.utcnow()
    rfqs = db.execute(select(Rfq).where(Rfq.created_by_id == buyer_id).order_by(Rfq.created_at.desc())).scalars().all()
    bids = _bids_by_rfq(db, [r.id for r in rfqs])

    rows, savings_pct, savings_total = [], [], Decimal(0)
    for r in rfqs:
        rb = bids.get(r.id, [])
        status = live_status(r, now)
        opening = _best_opening(rb)
        l1 = min((b.total_amount for b in rb), default=None)
        saved = (opening - l1) if opening is not None and l1 is not None else None
        pct = float(saved / opening * 100) if saved is not None and opening else None
        if pct is not None:
            savings_pct.append(pct)
            savings_total += saved
        rows.append(BuyerRfqRow.model_validate({**_summary(r, status, rb), "best_opening": opening,
                                                "savings_amount": saved, "savings_pct": pct}))

    return BuyerDashboard(
        total_rfqs=len(rfqs),
        active=sum(1 for r in rows if r.status == AuctionStatus.ACTIVE),
        scheduled=sum(1 for r in rows if r.status == AuctionStatus.SCHEDULED),
        bids_received=sum(r.bid_count for r in rows),
        extensions=sum(r.extension_count for r in rows),
        savings_total=savings_total,
        avg_savings_pct=round(sum(savings_pct) / len(savings_pct), 2) if savings_pct else None,
        rfqs=rows,
        activity=_activity(db, [r.id for r in rfqs]),
    )


def supplier_dashboard(db: Session, supplier_id: int) -> SupplierDashboard:
    now = clock.utcnow()
    mine_ids = list(db.execute(select(Bid.rfq_id).where(Bid.supplier_id == supplier_id).distinct()).scalars())
    rfqs = db.execute(select(Rfq).order_by(Rfq.current_close_at)).scalars().all()
    bids = _bids_by_rfq(db, [r.id for r in rfqs])

    my_rows, open_rows = [], []
    for r in rfqs:
        status = live_status(r, now)
        rb = bids.get(r.id, [])
        if r.id not in mine_ids:
            if status in OPEN:
                open_rows.append(RfqSummary.model_validate(_summary(r, status, rb)))
            continue
        ranking = ranked_quotes(rb)
        me = next(q for q in ranking if q.supplier_id == supplier_id)
        l1 = ranking[0]
        position = POSITION[(status in OPEN, me.rank == 1)]
        my_rows.append(SupplierAuctionRow.model_validate({
            **_summary(r, status, rb),
            "my_rank": me.rank, "my_rank_label": me.rank_label, "my_best": me.total_amount,
            "my_bid_count": me.bid_count, "l1_total": l1.total_amount,
            "gap_to_l1": me.total_amount - l1.total_amount, "position": position,
        }))

    # Live auctions first (soonest closing first), then finished ones (most recent first).
    my_rows.sort(key=lambda x: (x.status not in OPEN, x.current_close_at if x.status in OPEN
                                else -x.current_close_at.timestamp()))
    count = defaultdict(int)
    for row in my_rows:
        count[row.position] += 1
    return SupplierDashboard(
        participating=sum(1 for x in my_rows if x.status in OPEN),
        leading=count["LEADING"], outbid=count["OUTBID"], won=count["WON"], lost=count["LOST"],
        open_to_join=len(open_rows),
        my_auctions=my_rows,
        open_auctions=open_rows,
        activity=_activity(db, mine_ids),
    )
