"""Golden-value tests for fund multiples (DPI / RVPI / TVPI).

Hand-computed: contributions 100 at t=0 and 50 at t=1 (paid-in 150),
distributions 30 at t=2 and 90 at t=3 (total 120), residual NAV 60.
DPI = 120/150 = 0.8, RVPI = 60/150 = 0.4, TVPI = 180/150 = 1.2.
"""

from decimal import Decimal

import pytest

from perf.multiples import (
    distributions_total, dpi, paid_in_total, rvpi, tvpi,
)

FLOWS = [("0", "100"), ("1", "50"), ("2", "-30"), ("3", "-90")]


def test_paid_in_and_distributions():
    assert paid_in_total(FLOWS) == Decimal("150")
    assert distributions_total(FLOWS) == Decimal("120")


def test_golden_multiples():
    assert dpi(FLOWS) == Decimal("0.8")
    assert rvpi(FLOWS, "60") == Decimal("0.4")
    assert tvpi(FLOWS, "60") == Decimal("1.2")


def test_tvpi_is_dpi_plus_rvpi():
    assert tvpi(FLOWS, "60") == dpi(FLOWS) + rvpi(FLOWS, "60")


def test_fully_liquidated_fund_has_zero_rvpi():
    assert rvpi(FLOWS, "0") == Decimal("0")
    assert tvpi(FLOWS, "0") == dpi(FLOWS)


def test_no_contribution_raises():
    with pytest.raises(ValueError):
        dpi([("0", "-10"), ("1", "-5")])


def test_negative_residual_nav_raises():
    with pytest.raises(ValueError):
        tvpi(FLOWS, "-1")


def test_float_amount_rejected():
    with pytest.raises(TypeError):
        dpi([("0", 100.0), ("1", "-110")])
