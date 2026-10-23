"""Bid submission: the only write path that can move an auction's close time.

Concurrency: the RFQ row is locked with SELECT ... FOR UPDATE for the whole
transaction, so two bids on the same auction are applied strictly one after the
other. Ranking-before / ranking-after are therefore exact, and two simultaneous
last-second bids can never both read the same close time and double-extend it.
Bids on *different* auctions don't contend at all.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import DomainError
from app.models import AuctionEvent, AuctionStatus, Bid, EventType, Rfq, Supplier
from app.schemas import BidCreate, BidResult
from app.services.auction_engine import Standing, apply_bid, evaluate_extension, rank
from app.services.rfq_service import _rfq_bids, _standings, bid_out, sync_status


def submit_bid(db: Session, rfq_id: int, data: BidCreate) -> BidResult:
    rfq = db.execute(select(Rfq).where(Rfq.id == rfq_id).with_for_update()).scalar_one_or_none()
    if rfq is None:
        raise DomainError(404, f"RFQ {rfq_id} not found")

    now = clock.utcnow()  # taken *after* acquiring the lock: this is the bid's official timestamp
    if sync_status(db, rfq, now):
        db.commit()  # persist a start/close transition we just detected, whatever happens next
        rfq = db.execute(select(Rfq).where(Rfq.id == rfq_id).with_for_update()).scalar_one()
    if rfq.status == AuctionStatus.SCHEDULED:
        raise DomainError(409, f"Bidding has not started yet (opens at {rfq.bid_start_at.isoformat()})")
    if rfq.status in (AuctionStatus.CLOSED, AuctionStatus.FORCE_CLOSED):
        raise DomainError(409, "This auction is closed; no more bids are accepted")

    supplier = db.get(Supplier, data.supplier_id)
    if supplier is None:
        raise DomainError(404, f"Supplier {data.supplier_id} not found")
    if data.quote_validity_date < date.today():
        raise DomainError(422, "Quote validity date cannot be in the past")

    bids = _rfq_bids(db, rfq.id)
    standings = _standings(bids)
    total = data.total
    mine = standings.get(supplier.id)
    if mine is not None and total >= mine.total:
        raise DomainError(
            422, f"In a British auction you can only lower your price: your current quote is "
                 f"{mine.total:,.2f}, the new total must be below it (got {total:,.2f})",
        )

    revision = sum(1 for b in bids if b.supplier_id == supplier.id) + 1
    bid = Bid(
        rfq_id=rfq.id, supplier_id=supplier.id, revision=revision, carrier_name=data.carrier_name.strip(),
        freight_charges=data.freight_charges, origin_charges=data.origin_charges,
        destination_charges=data.destination_charges, total_amount=total,
        transit_time_days=data.transit_time_days, quote_validity_date=data.quote_validity_date,
        remarks=data.remarks, created_at=now,
    )
    db.add(bid)
    db.flush()

    before = rank(list(standings.values()))
    after = rank(apply_bid(list(standings.values()), Standing(supplier.id, total, now)))
    position = after.index(supplier.id) + 1
    old_position = before.index(supplier.id) + 1 if supplier.id in before else None

    if old_position is None:
        move = f"entered at L{position}"
    elif old_position != position:
        move = f"moved L{old_position} -> L{position}"
    else:
        move = f"stays L{position}"
    db.add(AuctionEvent(
        rfq_id=rfq.id, event_type=EventType.BID_SUBMITTED, occurred_at=now, supplier_id=supplier.id, bid_id=bid.id,
        message=f"{supplier.name} bid {total:,.2f} {rfq.currency} (revision {revision}), {move}",
        details={"total": str(total), "rank": position, "previous_rank": old_position,
                 "ranking_before": before, "ranking_after": after},
    ))

    decision = None
    if rfq.is_british_auction:
        names = {b.supplier_id: b.supplier.name for b in bids} | {supplier.id: supplier.name}
        decision = evaluate_extension(
            trigger_type=rfq.trigger_type, window_minutes=rfq.trigger_window_minutes,
            extension_minutes=rfq.extension_minutes, current_close_at=rfq.current_close_at,
            forced_close_at=rfq.forced_close_at, bid_time=now,
            ranking_before=before, ranking_after=after, supplier_names=names,
        )
        if decision.extended:
            db.add(AuctionEvent(
                rfq_id=rfq.id, event_type=EventType.AUCTION_EXTENDED, occurred_at=now,
                supplier_id=supplier.id, bid_id=bid.id,
                message=f"Bid close time extended by {rfq.extension_minutes} min"
                        + (" (capped at forced close)" if decision.capped else ""),
                reason=decision.reason, previous_close_at=rfq.current_close_at, new_close_at=decision.new_close_at,
                details={"trigger_type": rfq.trigger_type.value, "capped": decision.capped},
            ))
            rfq.current_close_at = decision.new_close_at
            rfq.extension_count += 1
        elif decision.triggered:
            db.add(AuctionEvent(
                rfq_id=rfq.id, event_type=EventType.EXTENSION_CAPPED, occurred_at=now,
                supplier_id=supplier.id, bid_id=bid.id, message="Extension blocked: forced close time reached",
                reason=decision.reason, previous_close_at=rfq.current_close_at, new_close_at=rfq.current_close_at,
                details={"trigger_type": rfq.trigger_type.value, "capped": True},
            ))

    db.commit()
    return BidResult(
        bid=bid_out(bid), rank=position, rank_label=f"L{position}",
        extended=bool(decision and decision.extended), new_close_at=rfq.current_close_at,
        extension_reason=decision.reason if decision and decision.extended else None,
    )
