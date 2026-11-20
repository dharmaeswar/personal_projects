import numpy as np
import pytest

from term_structure_mbs import (
    HullWhiteModel,
    Pool,
    effective_duration_convexity,
    flat_curve,
    mc_price,
    project_cashflows,
    scenario_prices,
    solve_oas,
    static_price,
)


def _pool():
    return Pool(balance=100_000_000, wac=0.060, net_coupon=0.055, wam_months=360, psa=100.0)


def test_cashflows_return_all_principal():
    pool = _pool()
    cf = project_cashflows(pool, np.full(pool.wam_months, 0.06))
    principal = cf["scheduled_principal"].sum() + cf["prepayment"].sum()
    assert principal == pytest.approx(pool.balance, rel=1e-9)
    assert cf["ending_balance"][-1] == pytest.approx(0.0, abs=1e-4)
    assert np.all(cf["total"] > 0)


def _wal_years(cf, balance):
    principal = cf["scheduled_principal"] + cf["prepayment"]
    months = np.arange(1, len(principal) + 1)
    return float(np.sum(months * principal) / balance / 12.0)


def test_faster_prepayment_shortens_cashflows():
    pool = _pool()
    slow = project_cashflows(pool, np.full(pool.wam_months, 0.09))
    fast = project_cashflows(pool, np.full(pool.wam_months, 0.03))
    assert fast["prepayment"].sum() > slow["prepayment"].sum()
    assert _wal_years(fast, pool.balance) < _wal_years(slow, pool.balance)


def test_static_price_premium_and_discount():
    pool = _pool()
    premium = static_price(pool, flat_curve(0.04))
    discount = static_price(pool, flat_curve(0.075))
    assert premium > 100.0 > discount


def test_mc_price_matches_static_when_vol_is_zero():
    pool = _pool()
    curve = flat_curve(0.045)
    model = HullWhiteModel(curve, a=0.10, sigma=0.0)
    p_mc = mc_price(pool, model, n_paths=4, seed=2)
    p_static = static_price(pool, curve)
    assert p_mc == pytest.approx(p_static, abs=0.35)


def test_oas_roundtrip():
    pool = _pool()
    curve = flat_curve(0.045)
    target = static_price(pool, curve, spread=0.005)
    solved = solve_oas(pool, curve, target)
    assert solved == pytest.approx(0.005, abs=2e-4)


def test_oas_rejects_out_of_range_target():
    pool = _pool()
    with pytest.raises(ValueError):
        solve_oas(pool, flat_curve(0.045), 250.0)


def test_duration_and_scenarios():
    pool = _pool()
    curve = flat_curve(0.045)
    duration, convexity = effective_duration_convexity(pool, curve)
    assert 1.0 < duration < 10.0
    prices = scenario_prices(pool, curve, {"up_100bp": 0.01, "down_100bp": -0.01})
    assert prices["down_100bp"] > prices["base"] > prices["up_100bp"]
