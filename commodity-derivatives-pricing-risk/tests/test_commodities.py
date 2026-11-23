"""Tests for the commodity derivatives pricing and risk modules."""

from __future__ import annotations

import math

import numpy as np
import pytest

from commodities.curves import (
    calendar_spreads,
    curve_shape,
    curve_summary,
    implied_convenience_yield,
)
from commodities.data import generate_futures_curve, generate_spot_paths
from commodities.pricing import (
    black76_call,
    black76_greeks,
    black76_put,
    implied_vol,
    monte_carlo_price,
)
from commodities.risk import (
    book_value,
    historical_var,
    monte_carlo_var,
    scenario_shocks,
)
from commodities.validation import (
    check_greeks_finite_difference,
    check_mc_convergence,
    check_put_call_parity,
)

F, K, T, R, SIGMA = 80.0, 80.0, 0.5, 0.045, 0.32


def test_black76_atm_call_put_reasonable():
    call = black76_call(F, K, T, R, SIGMA)
    put = black76_put(F, K, T, R, SIGMA)
    assert call > 0 and put > 0
    # ATM call and put are close (rates small, T short).
    assert abs(call - put) < 1.0


def test_call_price_increases_with_vol_and_time():
    assert black76_call(F, K, T, R, 0.5) > black76_call(F, K, T, R, 0.2)
    assert black76_call(F, K, 1.0, R, SIGMA) > black76_call(F, K, T, R, SIGMA)
    assert black76_call(F, K + 10, T, R, SIGMA) < black76_call(F, K, T, R, SIGMA)


def test_put_call_parity():
    result = check_put_call_parity(F, K, T, R, SIGMA)
    assert result["passed"] is True
    assert result["difference"] < 1e-8


def test_mc_converges_to_black76():
    result = check_mc_convergence(F, K, T, R, SIGMA, n_paths=200_000)
    assert result["passed"] is True
    assert result["z_score"] < 3.0


def test_greeks_match_finite_differences():
    result = check_greeks_finite_difference(F, K, T, R, SIGMA)
    assert result["passed"] is True


def test_greeks_signs():
    greeks = black76_greeks(F, K, T, R, SIGMA, "call")
    assert 0.0 < greeks["delta"] < 1.0
    assert greeks["gamma"] > 0
    assert greeks["vega"] > 0
    assert greeks["theta"] < 0  # long option loses value with time
    put_greeks = black76_greeks(F, K, T, R, SIGMA, "put")
    assert -1.0 < put_greeks["delta"] < 0.0


def test_implied_vol_recovers_input():
    price = black76_call(F, K, T, R, SIGMA)
    assert abs(implied_vol(price, F, K, T, R, "call") - SIGMA) < 1e-6


def test_futures_curve_shape_and_spreads():
    contango = generate_futures_curve(78.0, 0.045, 0.08, 0.02)
    assert curve_shape(contango) == "contango"
    backward = generate_futures_curve(78.0, 0.045, 0.02, 0.12)
    assert curve_shape(backward) == "backwardation"
    spreads = calendar_spreads(contango)
    assert len(spreads) == 11
    assert (spreads["spread"] > 0).all()
    summary = curve_summary(contango)
    assert summary["contracts"] == 12
    assert summary["front_price"] < summary["deferred_price"]


def test_implied_convenience_yield_roundtrip():
    spot, r, u, y = 78.0, 0.045, 0.08, 0.05
    curve = generate_futures_curve(spot, r, u, y)
    fwd = float(curve["futures_price"].iloc[5])
    recovered = implied_convenience_yield(spot, fwd, 0.5, r, u)
    assert abs(recovered - y) < 1e-9


def test_spot_paths_deterministic_and_shaped():
    first = generate_spot_paths()
    second = generate_spot_paths()
    assert first.shape == (252, 3)
    assert (first > 0).all().all()
    assert first.equals(second)
    # Natural gas is the most volatile of the three.
    vols = np.log(first / first.shift(1)).dropna().std()
    assert vols["NATGAS"] > vols["WTI"] > vols["GOLD"]


def test_book_var_ordering_and_scenarios():
    spots = generate_spot_paths()
    last = {c: float(spots[c].iloc[-1]) for c in spots.columns}
    returns = np.log(spots / spots.shift(1)).dropna()
    book = [
        {"type": "future", "commodity": "WTI", "qty": 100.0},
        {"type": "call", "commodity": "WTI", "qty": 20.0, "strike": 80.0, "T": 0.5, "sigma": 0.32},
    ]
    var95 = historical_var(returns, book, last, R, 0.95)
    var99 = historical_var(returns, book, last, R, 0.99)
    assert var99["var"] >= var95["var"]
    assert var99["expected_shortfall"] >= var99["var"]
    mc = monte_carlo_var(
        book, last, {"WTI": 0.32, "NATGAS": 0.65, "GOLD": 0.15}, R, 0.95
    )
    assert mc["var"] > 0
    assert mc["expected_shortfall"] >= mc["var"]
    scen = scenario_shocks(book, last, R)
    down = scen[scen["scenario"] == "spot -10%"]["pnl"].iloc[0]
    up = scen[scen["scenario"] == "spot +10%"]["pnl"].iloc[0]
    assert down < 0 < up  # long book loses on down moves, gains on up moves
    assert book_value(book, last, R) > 0


def test_monte_carlo_price_std_error_shrinks():
    _, se_small = monte_carlo_price(F, K, T, R, SIGMA, n_paths=10_000)
    _, se_large = monte_carlo_price(F, K, T, R, SIGMA, n_paths=200_000)
    assert se_large < se_small
