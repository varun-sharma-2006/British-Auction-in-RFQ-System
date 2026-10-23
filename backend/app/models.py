import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import clock
from app.db import Base, UTCDateTime

Money = Numeric(14, 2)


def _now():
    return clock.utcnow()

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _str_enum(cls: type[enum.Enum], name: str) -> Enum:
    # Stored as VARCHAR + CHECK (not a native PG enum) so adding a value is a cheap migration.
    return Enum(cls, name=name, native_enum=False, create_constraint=True, length=32,
                values_callable=lambda e: [m.value for m in e])


class TriggerType(str, enum.Enum):
    BID_RECEIVED = "BID_RECEIVED"          # any bid inside the trigger window
    ANY_RANK_CHANGE = "ANY_RANK_CHANGE"    # any supplier's position in the ranking changes
    L1_CHANGE = "L1_CHANGE"                # only when the lowest bidder changes


class AuctionStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"        # bid start time not reached yet
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"              # closed at the (possibly extended) bid close time
    FORCE_CLOSED = "FORCE_CLOSED"  # extensions ran into the forced close time and it hard-stopped


class EventType(str, enum.Enum):
    RFQ_CREATED = "RFQ_CREATED"
    AUCTION_STARTED = "AUCTION_STARTED"
    BID_SUBMITTED = "BID_SUBMITTED"
    AUCTION_EXTENDED = "AUCTION_EXTENDED"
    EXTENSION_CAPPED = "EXTENSION_CAPPED"   # trigger fired but forced close time leaves no room
    AUCTION_CLOSED = "AUCTION_CLOSED"
    AUCTION_FORCE_CLOSED = "AUCTION_FORCE_CLOSED"


class UserRole(str, enum.Enum):
    BUYER = "BUYER"
    SUPPLIER = "SUPPLIER"


class User(Base):
    """A person who logs in. Supplier users act on behalf of one supplier company."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role <> 'SUPPLIER' OR supplier_id IS NOT NULL", name="ck_user_supplier_has_company"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(_str_enum(UserRole, "user_role"), nullable=False)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)

    supplier: Mapped["Supplier | None"] = relationship()


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)


class Rfq(Base):
    __tablename__ = "rfqs"
    __table_args__ = (
        CheckConstraint("bid_close_at > bid_start_at", name="ck_rfq_close_after_start"),
        CheckConstraint("forced_close_at >= bid_close_at", name="ck_rfq_forced_not_before_close"),
        CheckConstraint(
            "current_close_at >= bid_close_at AND current_close_at <= forced_close_at",
            name="ck_rfq_current_close_within_bounds",
        ),
        CheckConstraint(
            "NOT is_british_auction OR (forced_close_at > bid_close_at"
            " AND trigger_window_minutes > 0 AND extension_minutes > 0 AND trigger_type IS NOT NULL)",
            name="ck_rfq_british_config_complete",
        ),
        Index("ix_rfqs_status_close", "status", "current_close_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str | None] = mapped_column(String(120))
    destination: Mapped[str | None] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False)

    bid_start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    bid_close_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)       # original, never changes
    current_close_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)   # moves with extensions
    forced_close_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)    # hard ceiling

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))   # the buyer

    is_british_auction: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trigger_window_minutes: Mapped[int | None] = mapped_column(Integer)   # X
    extension_minutes: Mapped[int | None] = mapped_column(Integer)        # Y
    trigger_type: Mapped[TriggerType | None] = mapped_column(_str_enum(TriggerType, "trigger_type"))

    status: Mapped[AuctionStatus] = mapped_column(
        _str_enum(AuctionStatus, "auction_status"), default=AuctionStatus.SCHEDULED, nullable=False
    )
    extension_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now, nullable=False)

    bids: Mapped[list["Bid"]] = relationship(back_populates="rfq", order_by="Bid.created_at")
    events: Mapped[list["AuctionEvent"]] = relationship(back_populates="rfq", order_by="AuctionEvent.id")


class Bid(Base):
    """One quote submission. Suppliers re-bid by inserting a new, lower row —
    history is never overwritten, which is what makes the activity log auditable."""

    __tablename__ = "bids"
    __table_args__ = (
        CheckConstraint(
            "freight_charges >= 0 AND origin_charges >= 0 AND destination_charges >= 0",
            name="ck_bid_charges_non_negative",
        ),
        CheckConstraint("total_amount > 0", name="ck_bid_total_positive"),
        CheckConstraint("transit_time_days > 0", name="ck_bid_transit_positive"),
        Index("ix_bids_rfq_total", "rfq_id", "total_amount"),
        Index("ix_bids_rfq_supplier_created", "rfq_id", "supplier_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)   # 1st, 2nd, ... bid by this supplier

    carrier_name: Mapped[str] = mapped_column(String(120), nullable=False)
    freight_charges: Mapped[Decimal] = mapped_column(Money, nullable=False)
    origin_charges: Mapped[Decimal] = mapped_column(Money, nullable=False)
    destination_charges: Mapped[Decimal] = mapped_column(Money, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    transit_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_validity_date: Mapped[date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)

    rfq: Mapped[Rfq] = relationship(back_populates="bids")
    supplier: Mapped[Supplier] = relationship()


class AuctionEvent(Base):
    """Append-only activity log: bids, extensions (with reason), closures."""

    __tablename__ = "auction_events"
    __table_args__ = (Index("ix_events_rfq_id", "rfq_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(_str_enum(EventType, "event_type"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)                 # why an extension happened
    previous_close_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    new_close_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    details: Mapped[dict | None] = mapped_column(JsonType)

    rfq: Mapped[Rfq] = relationship(back_populates="events")
    supplier: Mapped[Supplier | None] = relationship()
