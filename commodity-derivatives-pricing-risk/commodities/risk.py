"""Risk analytics for a small commodity book: VaR, expected shortfall,
scenario shocks.

The book is a list of positions: futures (linear in the futures
price) and European options on futures (priced with Black-76). Two
VaR engines are provided and cross-checked in the validation module:
historical VaR from the simulated spot-return history, and Monte
Carlo VaR from fresh simulated futures paths. Expected shortfall is
the mean loss beyond VaR. Scenario shocks reprice the book under
spot moves and vol moves.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .pricing import black76_call, black76_put


def position_value(position: dict, futures: dict[str, float], r: float) -> float:
    """Mark a position to market. Futures are linear; options use Black-76.

    A position is {"type": "future"/"call"/"put", "commodity": str,
    "qty": float, "strike": float (options), "T": float (options),
    "sigma": float (options)}. Long qty is positive.
    """
    F = futures[position["commodity"]]
    qty = float(position["qty"])
    if position["type"] == "future":
        return qty * F
    price = (
        black76_call(F, position["strike"], position["T"], r, position["sigma"])
        if position["type"] == "call"
        else black76_put(F, position["strike"], position["T"], r, position["sigma"])
    )
    return qty * price


def book_value(
    positions: list[dict], futures: dict[str, float], r: float
) -> float:
    """Total mark-to-market of the book."""
    return sum(position_value(p, futures, r) for p in positions)


def historical_var(
    returns: pd.DataFrame,
    positions: list[dict],
    spot: dict[str, float],
    r: float,
    confidence: float = 0.95,
) -> dict:
    """Historical VaR/ES: replay each historical return day on the book.

    Futures are revalued linearly; options are repriced with Black-76
    at the shocked futures price (same T, sigma — a first-order
    approximation that the report labels as such).
    """
    base = book_value(positions, spot, r)
    pnls = []
    for _, row in returns.iterrows():
        shocked = {
            c: spot[c] * math.exp(float(row[c])) for c in spot
        }
        pnls.append(book_value(positions, shocked, r) - base)
    pnls = np.array(pnls)
    losses = -pnls
    var = float(np.quantile(losses, confidence))
    tail = losses[losses >= var]
    return {
        "confidence": confidence,
        "var": round(var, 2),
        "expected_shortfall": round(float(tail.mean()) if len(tail) else var, 2),
        "base_value": round(base, 2),
        "worst_day_pnl": round(float(pnls.min()), 2),
    }


def monte_carlo_var(
    positions: list[dict],
    spot: dict[str, float],
    vols: dict[str, float],
    r: float,
    confidence: float = 0.95,
    horizon_days: int = 1,
    n_paths: int = 100_000,
    seed: int = 42,
) -> dict:
    """Monte Carlo 1-day VaR/ES: simulate futures moves, reprice the book."""
    rng = np.random.default_rng(seed)
    dt = horizon_days / 252.0
    base = book_value(positions, spot, r)
    # Independent shocks per commodity (the report labels this).
    shocks = {
        c: rng.standard_normal(n_paths) for c in spot
    }
    shocked_values = np.zeros(n_paths)
    for i in range(n_paths):
        shocked = {
            c: spot[c] * math.exp(-0.5 * vols[c] ** 2 * dt + vols[c] * math.sqrt(dt) * shocks[c][i])
            for c in spot
        }
        shocked_values[i] = book_value(positions, shocked, r)
    pnls = shocked_values - base
    losses = -pnls
    var = float(np.quantile(losses, confidence))
    tail = losses[losses >= var]
    return {
        "confidence": confidence,
        "var": round(var, 2),
        "expected_shortfall": round(float(tail.mean()) if len(tail) else var, 2),
        "base_value": round(base, 2),
    }


def scenario_shocks(
    positions: list[dict],
    spot: dict[str, float],
    r: float,
    spot_moves: tuple[float, ...] = (-0.10, -0.05, 0.05, 0.10),
    vol_moves: tuple[float, ...] = (0.0, 0.05),
) -> pd.DataFrame:
    """Reprice the book under spot moves (all commodities together)
    and vol bumps (options only). Returns a P&L table."""
    base = book_value(positions, spot, r)
    rows = []
    for move in spot_moves:
        shocked = {c: s * (1.0 + move) for c, s in spot.items()}
        rows.append(
            {
                "scenario": f"spot {move:+.0%}",
                "vol_bump": 0.0,
                "pnl": round(book_value(positions, shocked, r) - base, 2),
            }
        )
    for bump in vol_moves:
        if bump == 0.0:
            continue
        bumped = [
            {**p, "sigma": p["sigma"] + bump} if p["type"] in ("call", "put") else p
            for p in positions
        ]
        rows.append(
            {
                "scenario": "spot flat",
                "vol_bump": bump,
                "pnl": round(book_value(bumped, spot, r) - base, 2),
            }
        )
    return pd.DataFrame(rows)
