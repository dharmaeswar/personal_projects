"""Futures curve analytics: calendar spreads, shape, convenience yield.

A curve is in contango when deferred contracts cost more than nearby
ones (positive cost of carry) and in backwardation when they cost
less. The implied convenience yield backs out of the cost-of-carry
relation y = r + u - ln(F/S) / T; a high implied yield means the
market pays up for prompt barrels (tight prompt supply).
"""

from __future__ import annotations

import math

import pandas as pd


def calendar_spreads(curve: pd.DataFrame) -> pd.DataFrame:
    """Month-over-month spreads: one row per adjacent contract pair."""
    out = curve.copy()
    out["spread"] = out["futures_price"].diff()
    out["spread_pct"] = out["futures_price"].pct_change() * 100.0
    return out.dropna().reset_index(drop=True)


def curve_shape(curve: pd.DataFrame) -> str:
    """'contango' if the curve rises with maturity, else 'backwardation'."""
    first = float(curve["futures_price"].iloc[0])
    last = float(curve["futures_price"].iloc[-1])
    return "contango" if last > first else "backwardation"


def implied_convenience_yield(
    spot: float, futures: float, T: float, r: float, storage_cost: float
) -> float:
    """y from F = S * exp((r + u - y) * T)."""
    if T <= 0 or spot <= 0 or futures <= 0:
        raise ValueError("spot, futures and T must be positive")
    return r + storage_cost - math.log(futures / spot) / T


def curve_summary(curve: pd.DataFrame) -> dict:
    """Front price, 12-month price, shape and average monthly spread."""
    spreads = calendar_spreads(curve)
    return {
        "front_price": round(float(curve["futures_price"].iloc[0]), 2),
        "deferred_price": round(float(curve["futures_price"].iloc[-1]), 2),
        "shape": curve_shape(curve),
        "avg_monthly_spread": round(float(spreads["spread"].mean()), 4),
        "contracts": len(curve),
    }
