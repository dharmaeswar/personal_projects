"""Calculation: tiered rates, accelerators, caps, rounding, edge cases."""
from decimal import Decimal

import pytest

from comp_engine import calculate, apply_adjustments, rate_for
from comp_engine import Tier


def _tiers():
    return (Tier(Decimal("0"), Decimal("0.06")),
            Tier(Decimal("0.50"), Decimal("0.08")),
            Tier(Decimal("1.00"), Decimal("0.10")))


def test_rate_for_picks_highest_reached_tier():
    assert rate_for(Decimal("0.25"), _tiers()) == Decimal("0.06")
    assert rate_for(Decimal("0.50"), _tiers()) == Decimal("0.08")
    assert rate_for(Decimal("1.20"), _tiers()) == Decimal("0.10")


def test_basic_commission_at_tier_rate(plan_v1):
    result = calculate("D1", "R1", Decimal("100000"), Decimal("0.60"), plan_v1)
    assert result.gross_commission == Decimal("8000.00")
    assert result.rate == Decimal("0.08")
    assert result.plan_version == 1
    assert result.capped is False


def test_zero_deal_pays_zero(plan_v1):
    result = calculate("D1", "R1", Decimal("0"), Decimal("0"), plan_v1)
    assert result.gross_commission == Decimal("0.00")


def test_accelerator_applies_above_threshold(plan_v1):
    # 125% attainment: first 100% at 10%, the 25% above at 10% * 1.5 = 15%.
    # 80000 * 0.10 + 20000 * 0.10 * 1.5 = 8000 + 3000 = 11000.
    result = calculate("D1", "R1", Decimal("100000"), Decimal("1.25"), plan_v1)
    assert result.gross_commission == Decimal("11000.00")


def test_no_accelerator_at_exactly_threshold(plan_v1):
    result = calculate("D1", "R1", Decimal("100000"), Decimal("1.00"), plan_v1)
    assert result.gross_commission == Decimal("10000.00")


def test_cap_bounds_commission(plan_v1):
    result = calculate("D1", "R1", Decimal("1000000"), Decimal("1.00"), plan_v1)
    assert result.gross_commission == Decimal("60000")
    assert result.capped is True


def test_cents_round_half_up(plan_v1):
    result = calculate("D1", "R1", Decimal("33333.33"), Decimal("0.60"), plan_v1)
    assert result.gross_commission == Decimal("2666.67")


def test_negative_amount_raises(plan_v1):
    with pytest.raises(ValueError):
        calculate("D1", "R1", Decimal("-100"), Decimal("0.5"), plan_v1)


def test_apply_adjustments_sets_net(plan_v1):
    result = calculate("D1", "R1", Decimal("100000"), Decimal("0.60"), plan_v1)
    apply_adjustments(result, Decimal("-2000"))
    assert result.adjustments == Decimal("-2000.00")
    assert result.net_commission == Decimal("6000.00")
