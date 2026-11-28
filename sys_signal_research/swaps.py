"""Interest-rate swap curve research: carry, roll-down and momentum.

AQR's team covers macro and managed futures as well as equities, and
the Quantitative Research Analyst posting lists exposure to futures,
currencies and/or swaps as preferred. This module adds the swaps leg
to the project: a synthetic 2y / 5y / 10y swap curve, a roll-down
(carry) signal from the curve slope, a momentum signal on the 10y
rate, and a simple receive-fixed / pay-fixed strategy P&L.

All data is synthetic and seeded. No real market data is used, and
nothing here is a claim about any real swap rate, strategy or return.
The P&L is a teaching model: a receive-fixed position gains when
rates fall (duration effect) and earns the curve slope as carry.
"""

import numpy as np
import pandas as pd

# Base swap rates (percent) and daily vol (percent points) per tenor.
# The curve is upward sloping on average: 2y 3.50, 5y 3.80, 10y 4.05.
TENORS = {
    "2Y": {"base": 3.50, "daily_vol": 0.045},
    "5Y": {"base": 3.80, "daily_vol": 0.040},
    "10Y": {"base": 4.05, "daily_vol": 0.035},
}

TRADING_DAYS = 252
# Duration proxy (years) for the 10y receive-fixed leg.
DURATION_10Y = 7.5


def generate_swap_curve(start="2021-01-01", end="2025-12-31", seed=11):
    """Generate a seeded synthetic 2y/5y/10y swap curve (rates in %).

    Each tenor mean-reverts around its base level with an AR(1) of
    phi = 0.995 (half-life of roughly 140 days), plus a shared curve
    factor so tenors move together. Returns a DataFrame indexed by
    business day with one column per tenor.
    """
    index = pd.bdate_range(start=start, end=end)
    n = len(index)
    rng = np.random.default_rng(seed)
    phi = 0.995
    # Shared curve factor: the whole curve shifts together.
    common = rng.standard_normal(n) * 0.02
    common = np.convolve(common, np.ones(20) / 20.0, mode="same")
    out = {}
    for tenor, spec in TENORS.items():
        eps = rng.standard_normal(n) * spec["daily_vol"]
        x = np.empty(n)
        x[0] = spec["base"]
        for t in range(1, n):
            x[t] = spec["base"] + phi * (x[t - 1] - spec["base"]) + eps[t] + common[t] * 0.5
        out[tenor] = x
    curve = pd.DataFrame(out, index=index)
    curve.index.name = "date"
    return curve


def curve_slope(curve):
    """10y minus 2y swap rate, in basis points."""
    return (curve["10Y"] - curve["2Y"]) * 100.0


def swap_carry_signal(curve, cap=1.0):
    """Roll-down / carry signal from the curve slope.

    A steep curve means the 10y rate is expected to roll down toward
    the 5y as time passes, so the signal is receive-fixed (long
    duration) when the slope is wide. Position is proportional to the
    slope: 100 bps of slope is a full position, clipped to [-1, 1].
    """
    return (curve_slope(curve) / 100.0).clip(-cap, cap)


def swap_rate_momentum(curve, lookback=63):
    """Momentum on the 10y rate: falling rates -> receive fixed.

    Position is the negative sign of the trailing ``lookback``-day
    change in the 10y rate, scaled by the strength of the move
    relative to its own history, in [-1, 1]. Computed only from data
    available at the close of day ``t``.
    """
    rate = curve["10Y"]
    change = rate - rate.shift(lookback)
    scale = change.rolling(lookback, min_periods=20).std()
    scaled = change / scale.replace(0, np.nan)
    return (-scaled).clip(-1, 1).fillna(0.0)


def combine_swap_signals(curve, weights=None):
    """Weighted average of the carry and momentum signals, in [-1, 1]."""
    from .signals import combine_signals

    return combine_signals(
        {
            "carry": swap_carry_signal(curve),
            "momentum": swap_rate_momentum(curve),
        },
        weights=weights or {"carry": 0.5, "momentum": 0.5},
    )


def swap_strategy_returns(curve, positions):
    """Daily strategy returns for a receive-fixed / pay-fixed position.

    ``positions`` is +1 for fully receive-fixed, -1 for fully
    pay-fixed. Positions apply from the next day (lag 1), so there is
    no look-ahead. Daily return = duration gain from the 10y rate
    move (receive-fixed gains when rates fall) plus carry accrual
    from the curve slope. Both terms are in decimal daily returns.
    """
    slope_bps = curve_slope(curve)
    d_rate = curve["10Y"].diff() / 100.0  # rate move in decimal
    pos = positions.reindex(curve.index).fillna(0.0)
    applied = pos.shift(1).fillna(0.0)
    duration_pnl = -applied * DURATION_10Y * d_rate.fillna(0.0)
    carry_accrual = applied * (slope_bps / 10_000.0) / TRADING_DAYS
    strat = (duration_pnl + carry_accrual).fillna(0.0)
    equity = (1.0 + strat).cumprod()
    return pd.DataFrame(
        {
            "return": strat,
            "duration_pnl": duration_pnl.fillna(0.0),
            "carry_accrual": carry_accrual.fillna(0.0),
            "position": applied,
            "equity": equity,
        }
    )


def swaps_report(curve):
    """One-call summary: curve shape, signals and backtested metrics."""
    from .backtest import portfolio_metrics

    positions = combine_swap_signals(curve)
    result = swap_strategy_returns(curve, positions)
    metrics = portfolio_metrics(result["equity"])
    slope = curve_slope(curve)
    return {
        "mean_slope_bps": round(float(slope.mean()), 2),
        "mean_10y_rate": round(float(curve["10Y"].mean()), 2),
        "mean_position": round(float(positions.mean()), 4),
        "sharpe": round(metrics["sharpe"], 4),
        "cagr": round(metrics["cagr"], 4),
        "annual_vol": round(metrics["annual_vol"], 4),
        "max_drawdown": round(metrics["max_drawdown"], 4),
        "mean_daily_carry_bps": round(float(result["carry_accrual"].mean() * 10_000), 4),
    }
