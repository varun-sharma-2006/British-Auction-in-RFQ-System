from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import clock
from app.db import get_db
from app.errors import DomainError
from app.models import AuctionStatus, Supplier
from app.realtime import manager, notify_rfq_changed
from app.schemas import (
    BidCreate,
    BidOut,
    BidResult,
    EventOut,
    Metrics,
    RfqCreate,
    RfqDetail,
    RfqSummary,
    SupplierCreate,
    SupplierOut,
)
from app.services import bidding, rfq_service

router = APIRouter(prefix="/api")


@router.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "server_time": clock.utcnow()}


# ---------- suppliers ----------

@router.get("/suppliers", response_model=list[SupplierOut], tags=["suppliers"])
def list_suppliers(db: Session = Depends(get_db)):
    return db.execute(select(Supplier).order_by(Supplier.name)).scalars().all()


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED, tags=["suppliers"])
def create_supplier(body: SupplierCreate, db: Session = Depends(get_db)):
    supplier = Supplier(name=body.name, contact_email=body.contact_email)
    db.add(supplier)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, f"A supplier named '{body.name}' already exists")
    return supplier


# ---------- RFQs / auctions ----------

@router.get("/rfqs", response_model=list[RfqSummary], tags=["rfqs"])
def list_rfqs(status: AuctionStatus | None = Query(default=None), db: Session = Depends(get_db)):
    return rfq_service.list_rfqs(db, status)


@router.post("/rfqs", response_model=RfqDetail, status_code=status.HTTP_201_CREATED, tags=["rfqs"])
async def create_rfq(body: RfqCreate, db: Session = Depends(get_db)):
    rfq = await run_in_threadpool(rfq_service.create_rfq, db, body)
    await notify_rfq_changed(rfq.id, "created")
    return await run_in_threadpool(rfq_service.rfq_detail, db, rfq.id)


@router.get("/rfqs/{rfq_id}", response_model=RfqDetail, tags=["rfqs"])
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    return rfq_service.rfq_detail(db, rfq_id)


@router.get("/rfqs/{rfq_id}/bids", response_model=list[BidOut], tags=["bids"])
def list_bids(rfq_id: int, db: Session = Depends(get_db)):
    """Every submission, newest first (the ranking on the RFQ shows each supplier's best)."""
    return rfq_service.rfq_bids(db, rfq_id)


@router.post("/rfqs/{rfq_id}/bids", response_model=BidResult, status_code=status.HTTP_201_CREATED, tags=["bids"])
async def submit_bid(rfq_id: int, body: BidCreate, db: Session = Depends(get_db)):
    result = await run_in_threadpool(bidding.submit_bid, db, rfq_id, body)
    await notify_rfq_changed(rfq_id, "extended" if result.extended else "bid")
    return result


@router.get("/rfqs/{rfq_id}/activity", response_model=list[EventOut], tags=["rfqs"])
def activity(rfq_id: int, db: Session = Depends(get_db)):
    return rfq_service.rfq_activity(db, rfq_id)


@router.get("/metrics", response_model=Metrics, tags=["meta"])
def get_metrics(db: Session = Depends(get_db)):
    return rfq_service.metrics(db)


# ---------- live updates ----------

ws_router = APIRouter()


@ws_router.websocket("/ws")
async def websocket(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # we only push; reading keeps the connection alive and detects close
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
