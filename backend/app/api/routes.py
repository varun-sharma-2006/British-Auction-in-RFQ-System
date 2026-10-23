from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import clock
from app.api.deps import current_user, require_buyer, require_supplier
from app.db import get_db
from app.errors import DomainError
from app.models import AuctionStatus, Supplier, User
from app.realtime import manager, notify_rfq_changed
from app.schemas import (
    BidCreate,
    BidOut,
    BidResult,
    BuyerDashboard,
    EventOut,
    Metrics,
    RfqCreate,
    RfqDetail,
    RfqSummary,
    SupplierCreate,
    SupplierDashboard,
    SupplierOut,
)
from app.services import availability, bidding, dashboard, rfq_service

router = APIRouter(prefix="/api")
# Everything except /health needs a signed-in user; writes are additionally role-checked.
authed = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


@router.get("/health", tags=["meta"])
def health():
    from app.main import INSTANCE  # which replica answered: useful behind the load balancer
    return {"status": "ok", "server_time": clock.utcnow(), "instance": INSTANCE}


# ---------- suppliers ----------

@authed.get("/suppliers", response_model=list[SupplierOut], tags=["suppliers"])
def list_suppliers(db: Session = Depends(get_db)):
    return db.execute(select(Supplier).order_by(Supplier.name)).scalars().all()


@authed.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED, tags=["suppliers"])
def create_supplier(body: SupplierCreate, db: Session = Depends(get_db), _: User = Depends(require_buyer)):
    supplier = Supplier(name=body.name, contact_email=body.contact_email)
    db.add(supplier)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, f"A supplier named '{body.name}' already exists") from None
    availability.note_added("company", supplier.name)
    return supplier


# ---------- RFQs / auctions ----------

@authed.get("/rfqs", response_model=list[RfqSummary], tags=["rfqs"])
def list_rfqs(status: AuctionStatus | None = Query(default=None), db: Session = Depends(get_db)):
    return rfq_service.list_rfqs(db, status)


@authed.post("/rfqs", response_model=RfqDetail, status_code=status.HTTP_201_CREATED, tags=["rfqs"])
async def create_rfq(body: RfqCreate, db: Session = Depends(get_db), buyer: User = Depends(require_buyer)):
    rfq = await run_in_threadpool(rfq_service.create_rfq, db, body, buyer.id)
    await notify_rfq_changed(rfq.id, "created")
    return await run_in_threadpool(rfq_service.rfq_detail, db, rfq.id)


@authed.get("/rfqs/{rfq_id}", response_model=RfqDetail, tags=["rfqs"])
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    return rfq_service.rfq_detail(db, rfq_id)


@authed.get("/rfqs/{rfq_id}/bids", response_model=list[BidOut], tags=["bids"])
def list_bids(rfq_id: int, db: Session = Depends(get_db)):
    """Every submission, newest first (the ranking on the RFQ shows each supplier's best)."""
    return rfq_service.rfq_bids(db, rfq_id)


@authed.post("/rfqs/{rfq_id}/bids", response_model=BidResult, status_code=status.HTTP_201_CREATED, tags=["bids"])
async def submit_bid(rfq_id: int, body: BidCreate, db: Session = Depends(get_db),
                     supplier: User = Depends(require_supplier)):
    result = await run_in_threadpool(bidding.submit_bid, db, rfq_id, supplier.supplier_id, body)
    await notify_rfq_changed(rfq_id, "extended" if result.extended else "bid")
    return result


@authed.get("/rfqs/{rfq_id}/activity", response_model=list[EventOut], tags=["rfqs"])
def activity(rfq_id: int, db: Session = Depends(get_db)):
    return rfq_service.rfq_activity(db, rfq_id)


@authed.get("/dashboard/buyer", response_model=BuyerDashboard, tags=["dashboard"])
def buyer_dashboard(db: Session = Depends(get_db), buyer: User = Depends(require_buyer)):
    return dashboard.buyer_dashboard(db, buyer.id)


@authed.get("/dashboard/supplier", response_model=SupplierDashboard, tags=["dashboard"])
def supplier_dashboard(db: Session = Depends(get_db), supplier: User = Depends(require_supplier)):
    return dashboard.supplier_dashboard(db, supplier.supplier_id)


@authed.get("/metrics", response_model=Metrics, tags=["meta"])
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
