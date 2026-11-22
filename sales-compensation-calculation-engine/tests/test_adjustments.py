"""Adjustments: clawbacks inside/outside the window, manual approval, SPIFFs."""
from datetime import date
from decimal import Decimal

import pytest

from comp_engine.adjustments import (
    clawback_for, manual_adjustment, spiff, total_for_deal, AdjustmentError,
)
from conftest import deal


def test_clawback_inside_window(plan_v1):
    d = deal(close=date(2026, 9, 20), status="refunded")
    claw = clawback_for(d, Decimal("7200"), plan_v1, date(2026, 11, 10))
    assert claw is not None
    assert claw.amount == Decimal("-7200")
    assert claw.kind == "clawback"


def test_clawback_outside_window_is_none(plan_v1):
    d = deal(close=date(2026, 6, 1), status="refunded")
    assert clawback_for(d, Decimal("7200"), plan_v1, date(2026, 11, 10)) is None


def test_clawback_at_window_edge_still_fires(plan_v1):
    d = deal(close=date(2026, 8, 12), status="churned")
    claw = clawback_for(d, Decimal("1000"), plan_v1, date(2026, 11, 10))
    assert claw is not None  # exactly 90 days after close


def test_no_clawback_for_closed_won(plan_v1):
    assert clawback_for(deal(), Decimal("1000"), plan_v1, date(2026, 11, 10)) is None


def test_event_before_close_raises(plan_v1):
    d = deal(close=date(2026, 11, 20), status="refunded")
    with pytest.raises(AdjustmentError):
        clawback_for(d, Decimal("1000"), plan_v1, date(2026, 11, 10))


def test_manual_adjustment_needs_approver():
    with pytest.raises(AdjustmentError):
        manual_adjustment("A1", "D1", "R1", Decimal("500"), "goodwill", None)


def test_manual_adjustment_with_approver():
    adj = manual_adjustment("A1", "D1", "R1", Decimal("-500"), "pricing error",
                            "finance-lead", date(2026, 11, 15))
    assert adj.approved_by == "finance-lead"
    assert adj.amount == Decimal("-500")


def test_zero_manual_adjustment_rejected():
    with pytest.raises(AdjustmentError):
        manual_adjustment("A1", "D1", "R1", Decimal("0"), "noop", "lead")


def test_spiff_must_be_positive():
    with pytest.raises(AdjustmentError):
        spiff("S1", "D1", "R1", Decimal("-100"), "bad spiff")
    assert spiff("S1", "D1", "R1", Decimal("1500"), "new logo").amount == Decimal("1500")


def test_total_for_deal_sums_signed_amounts():
    adjs = [
        manual_adjustment("A1", "D1", "R1", Decimal("500"), "fix", "lead"),
        spiff("S1", "D1", "R1", Decimal("1500"), "bonus"),
        manual_adjustment("A2", "D2", "R1", Decimal("999"), "other", "lead"),
    ]
    assert total_for_deal(adjs, "D1") == Decimal("2000")
    assert total_for_deal(adjs, "D2") == Decimal("999")
    assert total_for_deal(adjs, "D9") == Decimal("0")
