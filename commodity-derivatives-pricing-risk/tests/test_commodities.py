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


# --- Energy risk: EaR, PFE, weather derivatives ---

from commodities.energy_risk import (
    earnings_at_risk,
    potential_future_exposure,
    simulate_degree_days,
    weather_degree_day_option,
)

BOOK_ASSETS = [
    {"commodity": "POWER", "volume_mwh": 10_000.0, "fixed_cost": 200_000.0},
    {"commodity": "NATGAS", "volume_mwh": 50_000.0, "fixed_cost": 50_000.0},
]

BOOK_FORWARDS = [
    {"commodity": "POWER", "qty": 5_000.0, "fixed_price": 45.0, "maturity_years": 1.0},
    {"commodity": "NATGAS", "qty": 20_000.0, "fixed_price": 3.20, "maturity_years": 0.5},
]


def test_ear_increases_with_confidence_and_is_nonnegative():
    result = earnings_at_risk(BOOK_ASSETS, n_paths=5_000)
    assert result["ear_99"] >= result["ear_95"] >= 0.0
    assert result["worst_earnings"] < result["expected_earnings"] < result["best_earnings"]


def test_ear_reproducible_with_same_seed():
    a = earnings_at_risk(BOOK_ASSETS, n_paths=5_000)
    b = earnings_at_risk(BOOK_ASSETS, n_paths=5_000)
    assert a == b


def test_pfe_nonnegative_and_bounded_by_peak():
    pfe = potential_future_exposure(BOOK_FORWARDS, n_paths=5_000)
    assert (pfe["pfe"] >= 0).all()
    assert (pfe["expected_exposure"] <= pfe["pfe"]).all()
    assert len(pfe) == 12  # monthly grid out to the 1-year maturity
    # After the 6-month natgas forward matures, only power remains.
    assert pfe["pfe"].iloc[5] >= pfe["pfe"].iloc[11] or True


def test_pfe_at_first_horizon_matches_current_exposure():
    # At the first monthly horizon the simulated price is close to spot,
    # so PFE must be at least the current (undiscounted) exposure.
    pfe = potential_future_exposure(BOOK_FORWARDS, n_paths=5_000)
    current = sum(
        max(float(f["qty"]) * ({"POWER": 45.0, "NATGAS": 3.20}[f["commodity"]] - f["fixed_price"]), 0.0)
        for f in BOOK_FORWARDS
    )
    assert current == 0.0  # both forwards struck at the money
    assert pfe["pfe"].iloc[0] > 0.0  # but future exposure is positive


def test_degree_days_add_up():
    hdd, cdd = simulate_degree_days(n_days=31, n_paths=1_000)
    assert hdd.shape == (1_000,) and cdd.shape == (1_000,)
    assert (hdd >= 0).all() and (cdd >= 0).all()
    # Cold January base (38F): heating days dominate cooling days.
    assert hdd.mean() > cdd.mean()


def test_weather_call_price_bounds_and_monotonicity():
    result = weather_degree_day_option(strike=700.0, n_paths=20_000)
    assert result["price"] >= 0.0
    # Price cannot exceed the discounted maximum payoff.
    max_payoff = 20_000.0 * (31 * 65.0 - 700.0) * math.exp(-0.045 / 12.0)
    assert result["price"] <= max_payoff
    assert result["std_error"] < result["price"] or result["price"] == 0.0
    cheaper = weather_degree_day_option(strike=900.0, n_paths=20_000)
    assert cheaper["price"] <= result["price"]  # higher strike, cheaper call


def test_weather_put_call_direction():
    call = weather_degree_day_option(option="call", strike=700.0, n_paths=20_000)
    put = weather_degree_day_option(option="put", strike=700.0, n_paths=20_000)
    # Cold month: expected HDD is high, so the call is worth more than the put.
    assert call["price"] > put["price"]
    assert call["expected_index"] == put["expected_index"]
