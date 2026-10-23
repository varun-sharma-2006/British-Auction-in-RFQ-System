from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import AuctionStatus, EventType, TriggerType, UserRole

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    role: UserRole
    company_name: str | None = Field(default=None, min_length=2, max_length=120)

    @model_validator(mode="after")
    def supplier_needs_company(self) -> "RegisterIn":
        if self.role == UserRole.SUPPLIER and not self.company_name:
            raise ValueError("Supplier accounts need a company name")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: UserRole
    supplier_id: int | None
    supplier_name: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Suppliers ----------

class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact_email: str | None = Field(default=None, max_length=254)

    @field_validator("name")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class SupplierOut(ORM):
    id: int
    name: str
    contact_email: str | None


# ---------- RFQs ----------

class RfqCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    reference_id: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9._\-/]+$")
    description: str | None = Field(default=None, max_length=5000)
    origin: str | None = Field(default=None, max_length=120)
    destination: str | None = Field(default=None, max_length=120)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    pickup_date: date

    bid_start_at: AwareDatetime
    bid_close_at: AwareDatetime
    forced_close_at: AwareDatetime | None = None

    is_british_auction: bool = True
    trigger_window_minutes: int | None = Field(default=None, ge=1, le=1440)
    extension_minutes: int | None = Field(default=None, ge=1, le=1440)
    trigger_type: TriggerType | None = None

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def check_times_and_config(self) -> "RfqCreate":
        if self.bid_close_at <= self.bid_start_at:
            raise ValueError("Bid Close Time must be later than Bid Start Time")
        if self.pickup_date < self.bid_start_at.date():
            raise ValueError("Pickup / Service Date cannot be before the Bid Start Date")

        if self.is_british_auction:
            missing = [
                label for label, value in (
                    ("Forced Bid Close Time", self.forced_close_at),
                    ("Trigger Window (X)", self.trigger_window_minutes),
                    ("Extension Duration (Y)", self.extension_minutes),
                    ("Extension Trigger", self.trigger_type),
                ) if value is None
            ]
            if missing:
                raise ValueError(f"British Auction requires: {', '.join(missing)}")
            if self.forced_close_at <= self.bid_close_at:
                raise ValueError("Forced Bid Close Time must be later than Bid Close Time")
        else:
            # A plain RFQ simply closes at the bid close time; extension settings don't apply.
            self.forced_close_at = self.bid_close_at
            self.trigger_window_minutes = self.extension_minutes = self.trigger_type = None
        return self


class AuctionConfig(BaseModel):
    is_british_auction: bool
    trigger_window_minutes: int | None
    extension_minutes: int | None
    trigger_type: TriggerType | None


class RfqSummary(ORM):
    id: int
    reference_id: str
    name: str
    origin: str | None
    destination: str | None
    currency: str
    pickup_date: date
    bid_start_at: datetime
    bid_close_at: datetime
    current_close_at: datetime
    forced_close_at: datetime
    status: AuctionStatus
    is_british_auction: bool
    trigger_type: TriggerType | None
    extension_count: int
    lowest_bid: Decimal | None = None
    lowest_bidder: str | None = None
    bid_count: int = 0
    supplier_count: int = 0


class BidCreate(BaseModel):
    # No supplier_id: the bidding supplier is taken from the access token, so nobody can bid as someone else.
    carrier_name: str = Field(min_length=2, max_length=120)
    freight_charges: Money
    origin_charges: Money = Decimal("0")
    destination_charges: Money = Decimal("0")
    transit_time_days: int = Field(ge=1, le=365)
    quote_validity_date: date
    remarks: str | None = Field(default=None, max_length=2000)

    @property
    def total(self) -> Decimal:
        return self.freight_charges + self.origin_charges + self.destination_charges

    @model_validator(mode="after")
    def positive_total(self) -> "BidCreate":
        if self.total <= 0:
            raise ValueError("Total quote amount must be greater than zero")
        return self


class BidOut(ORM):
    id: int
    rfq_id: int
    supplier_id: int
    supplier_name: str
    revision: int
    carrier_name: str
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    total_amount: Decimal
    transit_time_days: int
    quote_validity_date: date
    remarks: str | None
    created_at: datetime


class RankedQuote(BidOut):
    rank: int                 # 1 = L1
    rank_label: str           # "L1", "L2", ...
    bid_count: int            # how many times this supplier has bid
    first_total: Decimal      # their opening price, to show how far they came down


class EventOut(ORM):
    id: int
    event_type: EventType
    occurred_at: datetime
    supplier_id: int | None
    supplier_name: str | None = None
    bid_id: int | None
    message: str
    reason: str | None
    previous_close_at: datetime | None
    new_close_at: datetime | None
    details: dict | None


class RfqDetail(RfqSummary):
    description: str | None
    config: AuctionConfig
    closed_at: datetime | None
    created_at: datetime
    ranking: list[RankedQuote]
    server_time: datetime     # lets the UI correct its countdown for clock skew


class BidResult(BaseModel):
    bid: BidOut
    rank: int
    rank_label: str
    extended: bool
    new_close_at: datetime
    extension_reason: str | None


class Metrics(BaseModel):
    total_auctions: int
    active_auctions: int
    total_bids: int
    avg_bids_per_rfq: float
    extended_auctions: int
    avg_bids_extended: float | None
    avg_bids_not_extended: float | None
    avg_price_improvement_pct: float | None          # opening L1 -> current L1, all auctions with bids
    avg_improvement_extended_pct: float | None
    avg_improvement_not_extended_pct: float | None


# ---------- Dashboards ----------

class DashboardEvent(BaseModel):
    id: int
    rfq_id: int
    rfq_name: str
    reference_id: str
    event_type: EventType
    occurred_at: datetime
    message: str
    reason: str | None


class BuyerRfqRow(RfqSummary):
    best_opening: Decimal | None      # lowest *first* quote across suppliers
    savings_amount: Decimal | None    # best opening - current L1: what competition has saved so far
    savings_pct: float | None


class BuyerDashboard(BaseModel):
    total_rfqs: int
    active: int
    scheduled: int
    bids_received: int
    extensions: int
    savings_total: Decimal
    avg_savings_pct: float | None
    rfqs: list[BuyerRfqRow]
    activity: list[DashboardEvent]


class SupplierAuctionRow(RfqSummary):
    my_rank: int
    my_rank_label: str
    my_best: Decimal
    my_bid_count: int
    l1_total: Decimal
    gap_to_l1: Decimal                # 0 when I'm L1
    position: str                     # LEADING | OUTBID (live)  ·  WON | LOST (finished)


class SupplierDashboard(BaseModel):
    participating: int
    leading: int
    outbid: int
    won: int
    lost: int
    open_to_join: int
    my_auctions: list[SupplierAuctionRow]
    open_auctions: list[RfqSummary]
    activity: list[DashboardEvent]
