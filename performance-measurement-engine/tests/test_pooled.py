"""Golden-value tests for pooled and neutrally weighted IRR.

Fund A: -100 at t=0, +110 at t=1 (10% on paid-in 100).
Fund B: -400 at t=0, +484 at t=1 (21% on paid-in 400).

Pooled: -500 at t=0, +594 at t=1 -> 594/500 - 1 = 0.188 exactly.
Neutral weights: (1/100) : (1/400) = 0.8 : 0.2, so the weighted
stream is -160 at t=0, +184.8 at t=1 -> 184.8/160 - 1 = 0.155,
the simple average of 10% and 21%: each fund counts equally.
"""

from decimal import Decimal

import pytest

from perf.pooled import neutral_weights, neutrally_weighted_irr, pooled_irr

FUND_A = [("0", "-100"), ("1", "110")]
FUND_B = [("0", "-400"), ("1", "484")]


def test_pooled_irr_golden():
    rate, diag = pooled_irr([FUND_A, FUND_B])
    assert rate == Decimal("0.188")
    assert diag["ill_conditioned"] is False


def test_neutral_weights_sum_to_one_and_favour_small_fund():
    weights = neutral_weights([FUND_A, FUND_B])
    assert weights == [Decimal("0.8"), Decimal("0.2")]
    assert sum(weights) == Decimal(1)


def test_neutrally_weighted_irr_golden():
    rate, _ = neutrally_weighted_irr([FUND_A, FUND_B])
    assert rate == Decimal("0.155")


def test_single_fund_matches_plain_irr():
    pooled, _ = pooled_irr([FUND_A])
    neutral, _ = neutrally_weighted_irr([FUND_A])
    assert pooled == Decimal("0.1")
    assert neutral == Decimal("0.1")


def test_equal_size_funds_pooled_equals_neutral():
    fund_c = [("0", "-100"), ("1", "121")]
    pooled, _ = pooled_irr([FUND_A, fund_c])
    neutral, _ = neutrally_weighted_irr([FUND_A, fund_c])
    assert pooled == neutral == Decimal("0.155")


def test_no_funds_raises():
    with pytest.raises(ValueError):
        pooled_irr([])


def test_fund_without_paid_in_raises_for_neutral():
    with pytest.raises(ValueError):
        neutral_weights([[("0", "50"), ("1", "60")]])
