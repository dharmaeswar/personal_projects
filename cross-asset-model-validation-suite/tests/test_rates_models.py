"""Unit tests for the interest-rate models."""

import math

import pytest

from model_validation_suite.models.rates import (
    DiscountCurve,
    bootstrap_discount_factors,
    par_bond_price,
    vasicek_bond_price,
)

MATURITIES = [0.5, 1, 2, 3, 5, 7, 10]
ZERO_RATES = [0.021, 0.023, 0.026, 0.028, 0.031, 0.033, 0.035]


@pytest.fixture
def curve():
    return DiscountCurve(MATURITIES, ZERO_RATES)


def test_discount_factor_at_zero_is_one(curve):
    assert curve.discount(0.0) == 1.0


def test_discount_factor_matches_closed_form_at_nodes(curve):
    for t, r in zip(MATURITIES, ZERO_RATES):
        assert curve.discount(t) == pytest.approx(math.exp(-r * t), rel=1e-12)


def test_discount_factors_in_unit_interval_and_decreasing(curve):
    grid = [0.1, 0.5, 1, 2, 4, 5, 7, 10, 15, 20]
    dfs = [curve.discount(t) for t in grid]
    assert all(0.0 < df <= 1.0 for df in dfs)
    assert all(b < a for a, b in zip(dfs, dfs[1:]))


def test_zero_coupon_bond_price(curve):
    assert curve.zero_coupon_bond_price(5, face=100.0) == pytest.approx(
        100.0 * math.exp(-0.031 * 5), rel=1e-12)


def test_curve_rejects_mismatched_inputs():
    with pytest.raises(ValueError):
        DiscountCurve([1, 2], [0.02])


def test_bootstrap_first_discount_factor():
    dfs = bootstrap_discount_factors([0.02, 0.022, 0.025], [1, 2, 3])
    assert dfs[0] == pytest.approx(1.0 / 1.02, rel=1e-12)


def test_bootstrap_reprices_par_bonds_to_par():
    yields = [0.020, 0.022, 0.025, 0.027, 0.030]
    dfs = bootstrap_discount_factors(yields, [1, 2, 3, 4, 5])
    for n, y in enumerate(yields):
        assert par_bond_price(y, dfs[: n + 1]) == pytest.approx(1.0, abs=1e-12)


def test_vasicek_short_end_tends_to_face():
    price = vasicek_bond_price(0.025, 1e-5, a=0.3, theta=0.03, sigma=0.01, face=100.0)
    assert price == pytest.approx(100.0, abs=1e-3)


def test_vasicek_price_decreases_in_short_rate():
    args = dict(a=0.3, theta=0.03, sigma=0.01)
    p_low = vasicek_bond_price(0.02, 5.0, **args)
    p_high = vasicek_bond_price(0.04, 5.0, **args)
    assert 0.0 < p_high < p_low < 100.0
