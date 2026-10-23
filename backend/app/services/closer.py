"""Background job that moves auctions SCHEDULED -> ACTIVE -> CLOSED / FORCE_CLOSED.

Status is always *computed* from the clock on read, so the UI is correct even
if this job lags. The job's purpose is to persist the transition, write the
"auction closed" entry to the activity log at the exact close time, and push a
WebSocket notification.

FOR UPDATE SKIP LOCKED means several API replicas can run this loop safely:
each RFQ is processed by exactly one of them, and an RFQ that is busy taking a
bid is simply picked up on the next tick. In a larger deployment this is the
piece that becomes a Celery beat task (or per-auction ETA tasks).
"""
import asyncio
import logging

from sqlalchemy import or_, select
from starlette.concurrency import run_in_threadpool

from app import clock
from app.db import SessionLocal
from app.models import AuctionStatus, Rfq
from app.realtime import notify_rfq_changed
from app.services.rfq_service import sync_status

log = logging.getLogger(__name__)


def close_due_auctions() -> list[int]:
    now = clock.utcnow()
    changed: list[int] = []
    with SessionLocal() as db:
        due = db.execute(
            select(Rfq)
            .where(or_(
                (Rfq.status == AuctionStatus.SCHEDULED) & (Rfq.bid_start_at <= now),
                (Rfq.status == AuctionStatus.ACTIVE) & (Rfq.current_close_at <= now),
            ))
            .with_for_update(skip_locked=True)
        ).scalars().all()
        for rfq in due:
            if sync_status(db, rfq, now):
                changed.append(rfq.id)
        db.commit()
    return changed


async def run_closer(interval: float, stop: asyncio.Event) -> None:
    log.info("Auction closer started (every %.1fs)", interval)
    while not stop.is_set():
        try:
            for rfq_id in await run_in_threadpool(close_due_auctions):
                await notify_rfq_changed(rfq_id, "status_changed")
        except Exception:
            log.exception("Auction closer iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
