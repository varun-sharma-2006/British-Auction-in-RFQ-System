from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import AuctionStatus, TriggerType
from app.services.auction_engine import (
    Standing,
    apply_bid,
    compute_status,
    evaluate_extension,
    in_trigger_window,
    l1_changed,
    rank,
    rank_changed,
)

CLOSE = datetime(2030, 1, 1, 18, 0, tzinfo=timezone.utc)   # 6:00 PM, as in the assignment examples
FORCED = CLOSE + timedelta(minutes=30)


def t(h, m, s=0):
    return datetime(2030, 1, 1, h, m, s, tzinfo=timezone.utc)


def decide(trigger, before, after, bid_time=t(17, 55), close=CLOSE, forced=FORCED, x=10, y=5):
    return evaluate_extension(
        trigger_type=trigger, window_minutes=x, extension_minutes=y, current_close_at=close,
        forced_close_at=forced, bid_time=bid_time, ranking_before=before, ranking_after=after,
    )


class TestRanking:
    def test_lowest_total_is_l1(self):
        s = [Standing(1, Decimal("500"), t(17, 0)), Standing(2, Decimal("450"), t(17, 1)),
             Standing(3, Decimal("700"), t(16, 0))]
        assert rank(s) == [2, 1, 3]

    def test_tie_goes_to_whoever_reached_the_price_first(self):
        s = [Standing(1, Decimal("500"), t(17, 5)), Standing(2, Decimal("500"), t(17, 1))]
        assert rank(s) == [2, 1]

    def test_apply_bid_replaces_suppliers_previous_standing(self):
        s = [Standing(1, Decimal("500"), t(17, 0)), Standing(2, Decimal("450"), t(17, 1))]
        assert rank(apply_bid(s, Standing(1, Decimal("400"), t(17, 2)))) == [1, 2]


class TestWindowAndStatus:
    @pytest.mark.parametrize("when,expected", [
        (t(17, 49, 59), False),   # just before the 5:50 window opens
        (t(17, 50), True),        # window boundary is inclusive
        (t(17, 59, 59), True),
        (t(18, 0), False),        # at close time bidding is over
    ])
    def test_window_is_last_x_minutes_before_close(self, when, expected):
        assert in_trigger_window(when, CLOSE, 10) is expected

    def test_status_progression(self):
        start = t(17, 0)
        assert compute_status(t(16, 0), start, CLOSE, FORCED, True) == AuctionStatus.SCHEDULED
        assert compute_status(t(17, 30), start, CLOSE, FORCED, True) == AuctionStatus.ACTIVE
        assert compute_status(t(18, 0), start, CLOSE, FORCED, True) == AuctionStatus.CLOSED
        # Close time pushed all the way to the forced close => force closed.
        assert compute_status(FORCED, start, FORCED, FORCED, True) == AuctionStatus.FORCE_CLOSED


class TestRankChangeRules:
    def test_new_supplier_entering_last_is_not_a_rank_change(self):
        assert not rank_changed([1, 2], [1, 2, 3])

    def test_new_supplier_entering_above_others_is_a_rank_change(self):
        assert rank_changed([1, 2], [1, 3, 2])

    def test_lowering_price_without_overtaking_is_not_a_rank_change(self):
        assert not rank_changed([1, 2, 3], [1, 2, 3])

    def test_l1_change(self):
        assert l1_changed([1, 2], [2, 1])
        assert not l1_changed([1, 2, 3], [1, 3, 2])
        assert l1_changed([], [1])   # first bid establishes the L1


class TestExtensionDecision:
    def test_bid_received_in_window_extends_by_y_from_current_close(self):
        d = decide(TriggerType.BID_RECEIVED, [1], [1])
        assert d.extended and d.new_close_at == t(18, 5) and not d.capped
        assert "Bid received" in d.reason

    def test_bid_outside_window_never_extends(self):
        d = decide(TriggerType.BID_RECEIVED, [1], [2, 1], bid_time=t(17, 40))
        assert not d.triggered and d.new_close_at == CLOSE

    def test_any_rank_change(self):
        assert decide(TriggerType.ANY_RANK_CHANGE, [1, 2, 3], [1, 3, 2]).extended
        assert not decide(TriggerType.ANY_RANK_CHANGE, [1, 2], [1, 2]).triggered

    def test_l1_change_only(self):
        assert not decide(TriggerType.L1_CHANGE, [1, 2, 3], [1, 3, 2]).triggered
        d = decide(TriggerType.L1_CHANGE, [1, 2, 3], [3, 1, 2])
        assert d.extended and "L1" in d.reason

    def test_extension_is_capped_at_forced_close(self):
        d = decide(TriggerType.BID_RECEIVED, [1], [1], forced=t(18, 3))
        assert d.extended and d.capped and d.new_close_at == t(18, 3)

    def test_no_extension_once_at_forced_close(self):
        d = decide(TriggerType.BID_RECEIVED, [1], [1], close=FORCED, bid_time=FORCED - timedelta(minutes=1))
        assert d.triggered and not d.extended and d.capped and d.new_close_at == FORCED

    def test_repeated_extensions_never_pass_forced_close(self):
        close = CLOSE
        for _ in range(20):
            d = decide(TriggerType.BID_RECEIVED, [1], [1], close=close, bid_time=close - timedelta(seconds=30))
            assert d.new_close_at <= FORCED
            close = d.new_close_at
        assert close == FORCED
