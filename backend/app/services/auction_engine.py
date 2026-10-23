"""Pure British-auction rules — no database, no I/O.

Everything that decides *whether* an auction extends and *by how much* lives
here so it can be unit-tested exhaustively. The bidding service feeds it the
ranking before/after a bid and persists whatever it decides.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.models import AuctionStatus, TriggerType


@dataclass(frozen=True)
class Standing:
    """A supplier's current best quote in one auction."""

    supplier_id: int
    total: Decimal
    achieved_at: datetime


def rank(standings: list[Standing]) -> list[int]:
    """Supplier ids ordered L1, L2, L3, ...

    Lower total wins; on a tie, whoever reached that price first keeps the
    better rank (so copying the leader's price does not steal L1).
    """
    ordered = sorted(standings, key=lambda s: (s.total, s.achieved_at, s.supplier_id))
    return [s.supplier_id for s in ordered]


def apply_bid(standings: list[Standing], new: Standing) -> list[Standing]:
    """Standings after `new` replaces that supplier's previous best (if any)."""
    return [s for s in standings if s.supplier_id != new.supplier_id] + [new]


def compute_status(
    now: datetime,
    bid_start_at: datetime,
    current_close_at: datetime,
    forced_close_at: datetime,
    is_british_auction: bool,
) -> AuctionStatus:
    if now < bid_start_at:
        return AuctionStatus.SCHEDULED
    if now < current_close_at:
        return AuctionStatus.ACTIVE
    if is_british_auction and current_close_at >= forced_close_at:
        return AuctionStatus.FORCE_CLOSED
    return AuctionStatus.CLOSED


def in_trigger_window(bid_time: datetime, current_close_at: datetime, window_minutes: int) -> bool:
    """True if the bid lands in the last X minutes before the *current* close time."""
    return current_close_at - timedelta(minutes=window_minutes) <= bid_time < current_close_at


def rank_changed(before: list[int], after: list[int]) -> bool:
    """Did any supplier that was already ranked move to a different position?

    A brand-new supplier entering at the bottom does not move anyone, so it is
    not a rank change. Entering anywhere above the bottom pushes others down,
    which is.
    """
    positions_after = {sid: i for i, sid in enumerate(after)}
    return any(positions_after.get(sid) != i for i, sid in enumerate(before))


def l1_changed(before: list[int], after: list[int]) -> bool:
    return (before[0] if before else None) != (after[0] if after else None)


@dataclass(frozen=True)
class ExtensionDecision:
    triggered: bool                 # did the configured trigger condition fire?
    new_close_at: datetime          # close time after applying the decision
    extended: bool                  # did the close time actually move?
    capped: bool                    # was the extension shortened/blocked by the forced close?
    reason: str | None              # human-readable explanation for the activity log


def evaluate_extension(
    *,
    trigger_type: TriggerType,
    window_minutes: int,
    extension_minutes: int,
    current_close_at: datetime,
    forced_close_at: datetime,
    bid_time: datetime,
    ranking_before: list[int],
    ranking_after: list[int],
    supplier_names: dict[int, str] | None = None,
) -> ExtensionDecision:
    names = supplier_names or {}

    def name(sid: int | None) -> str:
        return names.get(sid, f"Supplier #{sid}") if sid is not None else "nobody"

    no_change = ExtensionDecision(False, current_close_at, False, False, None)

    if not in_trigger_window(bid_time, current_close_at, window_minutes):
        return no_change

    window = f"within the last {window_minutes} min before close"
    if trigger_type is TriggerType.BID_RECEIVED:
        reason = f"Bid received {window}"
    elif trigger_type is TriggerType.ANY_RANK_CHANGE:
        if not rank_changed(ranking_before, ranking_after):
            return no_change
        reason = f"Supplier ranking changed {window}"
    elif trigger_type is TriggerType.L1_CHANGE:
        if not l1_changed(ranking_before, ranking_after):
            return no_change
        old_l1 = ranking_before[0] if ranking_before else None
        reason = f"Lowest bidder (L1) changed from {name(old_l1)} to {name(ranking_after[0])} {window}"
    else:  # pragma: no cover - exhaustive over the enum
        raise ValueError(f"Unknown trigger type {trigger_type}")

    if current_close_at >= forced_close_at:
        return ExtensionDecision(
            True, current_close_at, False, True,
            f"{reason}, but the auction is already at its forced close time, so no extension is possible",
        )

    proposed = current_close_at + timedelta(minutes=extension_minutes)
    if proposed > forced_close_at:
        return ExtensionDecision(
            True, forced_close_at, True, True,
            f"{reason}; extension of {extension_minutes} min capped at the forced close time",
        )
    return ExtensionDecision(True, proposed, True, False, f"{reason}; extended by {extension_minutes} min")
