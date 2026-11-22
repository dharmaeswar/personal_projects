"""Synthetic, seeded futures and FX market data for signal research.

All prices are simulated with a geometric Brownian motion that has a
slowly varying volatility regime, so results are reproducible from the
seed alone. No real market data is used anywhere in this project.
"""

import numpy as np
import pandas as pd

# Annualised drift / volatility per instrument. Futures are quoted as
# continuous front-month prices; FX pairs are quoted as spot rates.
INSTRUMENTS = {
    "ES": {"kind": "futures", "market": "equity index", "drift": 0.06, "vol": 0.16, "start": 4000.0},
    "NQ": {"kind": "futures", "market": "equity index", "drift": 0.08, "vol": 0.22, "start": 15000.0},
    "TY": {"kind": "futures", "market": "rates", "drift": 0.02, "vol": 0.06, "start": 115.0},
    "CL": {"kind": "futures", "market": "energy", "drift": 0.00, "vol": 0.35, "start": 75.0},
    "GC": {"kind": "futures", "market": "metals", "drift": 0.03, "vol": 0.15, "start": 1900.0},
    "EURUSD": {"kind": "fx", "market": "fx", "drift": 0.00, "vol": 0.08, "start": 1.10},
    "USDJPY": {"kind": "fx", "market": "fx", "drift": 0.00, "vol": 0.09, "start": 140.0},
    "GBPUSD": {"kind": "fx", "market": "fx", "drift": 0.00, "vol": 0.09, "start": 1.27},
    "AUDUSD": {"kind": "fx", "market": "fx", "drift": 0.00, "vol": 0.10, "start": 0.66},
}

# Annualised rate differential (foreign minus domestic, in percent) used
# as the FX carry input. Slowly mean-reverts around the base level.
CARRY_BASE = {
    "EURUSD": -1.50,
    "USDJPY": -4.00,
    "GBPUSD": 0.25,
    "AUDUSD": 0.50,
}

TRADING_DAYS = 252


def generate_prices(start="2021-01-01", end="2025-12-31", seed=42):
    """Generate daily close prices for every instrument in INSTRUMENTS.

    Returns a DataFrame indexed by business day with one column per
    instrument. A deterministic vol-regime multiplier (0.7 / 1.0 / 1.4)
    changes at fixed fractions of the sample so backtests see calm and
    stressed periods.
    """
    index = pd.bdate_range(start=start, end=end)
    n = len(index)
    rng = np.random.default_rng(seed)
    dt = 1.0 / TRADING_DAYS
    # Vol-regime path: calm first third, normal middle, stressed last.
    regime = np.ones(n)
    regime[: n // 3] = 0.7
    regime[2 * n // 3 :] = 1.4
    out = {}
    for name, spec in INSTRUMENTS.items():
        shocks = rng.standard_normal(n)
        drift = (spec["drift"] - 0.5 * (spec["vol"] ** 2)) * dt
        rets = drift + spec["vol"] * regime * np.sqrt(dt) * shocks
        out[name] = spec["start"] * np.exp(np.cumsum(rets))
    prices = pd.DataFrame(out, index=index)
    prices.index.name = "date"
    return prices


def generate_carry(prices, seed=7):
    """Generate a slowly varying annualised carry (rate differential, %).

    Only FX pairs carry a rate differential; futures get a roll-yield
    proxy of zero here, because carry for futures comes from the term
    structure rather than a policy-rate gap. Returns a DataFrame aligned
    to ``prices`` with one column per FX pair.
    """
    rng = np.random.default_rng(seed)
    n = len(prices)
    out = {}
    for pair, base in CARRY_BASE.items():
        # AR(1) around the base level: half-life of roughly 60 days.
        phi = 0.988
        eps = rng.standard_normal(n) * 0.06
        x = np.empty(n)
        x[0] = base
        for t in range(1, n):
            x[t] = base + phi * (x[t - 1] - base) + eps[t]
        out[pair] = x
    carry = pd.DataFrame(out, index=prices.index)
    carry.index.name = "date"
    return carry


def daily_returns(prices):
    """Simple daily returns, first row dropped (no prior price)."""
    return prices.pct_change().dropna()
