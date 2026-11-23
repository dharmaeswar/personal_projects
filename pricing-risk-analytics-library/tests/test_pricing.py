"""Tests for the pricing and risk analytics library.

All numbers are checked against closed-form values, put-call parity,
or convergence behaviour — no market data is used.
"""

import math

import pytest

from pricing_lib import (
    DiscountCurve,
    aggregate_greeks,
    asian_mc,
    bs_greeks,
    bs_price,
    crank_nicolson_price,
    european_mc,
    explicit_price,
    historical_es,
    historical_var,
    implied_vol,
    parametric_var,
)

S, K, T, R, SIG = 100.0, 100.0, 1.0, 0.05, 0.20


# ---------------------------------------------------------------- Black-Scholes
def test_bs_call_put_parity():
    call = bs_price(S, K, T, R, SIG, "call")
    put = bs_price(S, K, T, R, SIG, "put")
    assert call - put == pytest.approx(S - K * math.exp(-R * T), abs=1e-9)


def test_bs_price_known_value():
    # S=K=100, T=1, r=5%, sigma=20%: call ~= 10.4506, put ~= 5.5735.
    assert bs_price(S, K, T, R, SIG, "call") == pytest.approx(10.4506, abs=1e-3)
    assert bs_price(S, K, T, R, SIG, "put") == pytest.approx(5.5735, abs=1e-3)


def test_bs_price_bounds_and_expiry():
    assert bs_price(S, K, T, R, SIG, "call") >= max(S - K, 0.0)
    assert bs_price(S, K, T, R, SIG, "put") >= max(K - S, 0.0)
    assert bs_price(110.0, K, 0.0, R, SIG, "call") == pytest.approx(10.0)
    assert bs_price(90.0, K, 0.0, R, SIG, "put") == pytest.approx(10.0)


def test_bs_price_rejects_bad_inputs():
    with pytest.raises(ValueError):
        bs_price(-100.0, K, T, R, SIG)
    with pytest.raises(ValueError):
        bs_price(S, K, T, R, SIG, "straddle")


def test_bs_greeks_signs_and_call_put_gamma():
    call = bs_greeks(S, K, T, R, SIG, "call")
    put = bs_greeks(S, K, T, R, SIG, "put")
    assert 0 < call["delta"] < 1
    assert -1 < put["delta"] < 0
    assert call["delta"] - put["delta"] == pytest.approx(1.0)
    assert call["gamma"] == pytest.approx(put["gamma"])
    assert call["gamma"] > 0
    assert call["vega"] == pytest.approx(put["vega"])
    assert call["vega"] > 0
    assert call["theta"] < 0
    assert call["rho"] > 0 and put["rho"] < 0


def test_implied_vol_round_trips():
    price = bs_price(S, K, T, R, SIG, "call")
    assert implied_vol(price, S, K, T, R, "call") == pytest.approx(SIG, abs=1e-4)
    price_put = bs_price(S, K, T, R, SIG, "put")
    assert implied_vol(price_put, S, K, T, R, "put") == pytest.approx(SIG, abs=1e-4)


def test_implied_vol_rejects_impossible_price():
    with pytest.raises(ValueError):
        implied_vol(1.0, 110.0, K, T, R, "call")  # below intrinsic 10


# ---------------------------------------------------------------- PDE solvers
def test_crank_nicolson_matches_bs():
    cn = crank_nicolson_price(S, K, T, R, SIG, "call", n_space=200, n_time=100)
    assert cn == pytest.approx(bs_price(S, K, T, R, SIG, "call"), abs=0.05)
    cn_put = crank_nicolson_price(S, K, T, R, SIG, "put", n_space=200, n_time=100)
    assert cn_put == pytest.approx(bs_price(S, K, T, R, SIG, "put"), abs=0.05)


def test_crank_nicolson_converges_with_finer_grid():
    bs = bs_price(S, K, T, R, SIG, "call")
    coarse = crank_nicolson_price(S, K, T, R, SIG, "call", n_space=50, n_time=25)
    fine = crank_nicolson_price(S, K, T, R, SIG, "call", n_space=400, n_time=200)
    assert abs(fine - bs) < abs(coarse - bs)


def test_explicit_matches_bs_and_rejects_unstable_step():
    price = explicit_price(S, K, T, R, SIG, "call", n_space=100, n_time=4000)
    assert price == pytest.approx(bs_price(S, K, T, R, SIG, "call"), abs=0.05)
    with pytest.raises(ValueError):
        explicit_price(S, K, T, R, SIG, "call", n_space=100, n_time=10)


def test_pde_put_call_parity():
    call = crank_nicolson_price(S, K, T, R, SIG, "call", n_space=200, n_time=100)
    put = crank_nicolson_price(S, K, T, R, SIG, "put", n_space=200, n_time=100)
    assert call - put == pytest.approx(S - K * math.exp(-R * T), abs=0.1)


# ---------------------------------------------------------------- Monte Carlo
def test_european_mc_within_ci_of_bs():
    result = european_mc(S, K, T, R, SIG, "call", n_paths=40000, seed=7)
    bs = bs_price(S, K, T, R, SIG, "call")
    assert result["ci_low"] <= bs <= result["ci_high"]
    assert result["stderr"] < 0.15


def test_european_mc_put_within_ci_of_bs():
    result = european_mc(S, K, T, R, SIG, "put", n_paths=40000, seed=11)
    bs = bs_price(S, K, T, R, SIG, "put")
    assert result["ci_low"] <= bs <= result["ci_high"]


def test_mc_stderr_shrinks_with_paths():
    small = european_mc(S, K, T, R, SIG, "call", n_paths=1000, seed=7)
    big = european_mc(S, K, T, R, SIG, "call", n_paths=40000, seed=7)
    assert big["stderr"] < small["stderr"]


def test_asian_mc_sane_and_below_european():
    asian = asian_mc(S, K, T, R, SIG, "call", n_paths=20000, seed=7)
    european = bs_price(S, K, T, R, SIG, "call")
    assert 0 < asian["price"] < european
    assert asian["stderr"] < 0.15


def test_mc_rejects_bad_inputs():
    with pytest.raises(ValueError):
        european_mc(S, K, T, R, SIG, "call", n_paths=50)
    with pytest.raises(ValueError):
        asian_mc(S, K, T, R, SIG, "call", n_paths=20000, n_fixings=0)


# ---------------------------------------------------------------- curves
PAR_RATES = [(1, 0.020), (2, 0.025), (3, 0.028), (5, 0.032), (10, 0.035)]


def test_curve_bootstraps_and_reprices_par_swaps():
    curve = DiscountCurve(PAR_RATES)
    assert len(curve.discount_factors) == 5
    dfs = curve.discount_factors
    assert all(dfs[i] > dfs[i + 1] for i in range(len(dfs) - 1))
    for tenor, rate in PAR_RATES:
        assert curve.par_swap_rate(tenor) == pytest.approx(rate, abs=1e-9)


def test_curve_discount_factor_and_forward():
    curve = DiscountCurve(PAR_RATES)
    assert curve.discount_factor(0.0) == 1.0
    assert curve.discount_factor(1.0) == pytest.approx(curve.discount_factors[0])
    assert curve.discount_factor(1.5) < curve.discount_factor(1.0)
    assert curve.discount_factor(1.5) > curve.discount_factor(2.0)
    fwd = curve.forward_rate(1.0, 2.0)
    assert fwd == pytest.approx(
        curve.discount_factor(1.0) / curve.discount_factor(2.0) - 1.0)
    assert curve.zero_rate(5.0) > 0


def test_curve_rejects_bad_inputs():
    with pytest.raises(ValueError):
        DiscountCurve([(2, 0.025), (2, 0.028)])  # tenors must increase
    with pytest.raises(ValueError):
        DiscountCurve([(1, 0.02), (2.5, 0.028)])  # tenors must be whole years
    with pytest.raises(ValueError):
        DiscountCurve([(1, 0.02)]).discount_factor(-1.0)


# ---------------------------------------------------------------- risk
RETURNS = [0.01, -0.02, 0.015, -0.005, -0.03, 0.02, -0.01, 0.005, -0.015, 0.03]


def test_historical_var_known_value():
    # Losses sorted ascending: -0.03, -0.02, -0.015, -0.01, -0.005, 0.005,
    # 0.01, 0.015, 0.02, 0.03. 95% VaR (alpha=0.05, n=10) is the worst
    # loss, 0.03; 80% VaR (alpha=0.20) is the 2nd worst, 0.02.
    assert historical_var(RETURNS, alpha=0.05) == pytest.approx(0.03)
    assert historical_var(RETURNS, alpha=0.20) == pytest.approx(0.02)


def test_historical_es_exceeds_var():
    var = historical_var(RETURNS, alpha=0.20)
    es = historical_es(RETURNS, alpha=0.20)
    assert es >= var
    assert es == pytest.approx((0.03 + 0.02) / 2)


def test_parametric_var_formula():
    result = parametric_var(RETURNS, alpha=0.05)
    mean = sum(RETURNS) / len(RETURNS)
    var = sum((r - mean) ** 2 for r in RETURNS) / (len(RETURNS) - 1)
    expected = -(mean + (-1.6448536269514722) * math.sqrt(var))
    assert result == pytest.approx(expected, abs=1e-6)
    assert result > 0


def test_risk_rejects_bad_inputs():
    with pytest.raises(ValueError):
        historical_var([], alpha=0.05)
    with pytest.raises(ValueError):
        historical_var(RETURNS, alpha=1.5)
    with pytest.raises(ValueError):
        parametric_var(RETURNS, alpha=0.0)


def test_aggregate_greeks_sums_positions():
    g1 = bs_greeks(S, K, T, R, SIG, "call")
    g2 = bs_greeks(S, K, T, R, SIG, "put")
    total = aggregate_greeks([(2, g1), (-1, g2)])
    assert total["delta"] == pytest.approx(2 * g1["delta"] - g2["delta"])
    assert total["gamma"] == pytest.approx(2 * g1["gamma"] - g2["gamma"])
    assert total["vega"] == pytest.approx(2 * g1["vega"] - g2["vega"])


def test_aggregate_greeks_rejects_missing_key():
    with pytest.raises(ValueError):
        aggregate_greeks([(1, {"delta": 0.5})])
