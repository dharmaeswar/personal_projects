"""Synthetic commodity market data: spot and futures prices, seeded.

Three commodities, the way a front-office quant team would look at
them: WTI crude (energy, moderate vol), Henry Hub natural gas
(energy, high vol with a winter seasonal), and gold (metal, low vol).
All prices are simulated with geometric Brownian motion from a fixed
seed — no real market data is used, and nothing here is a claim about
any real price, curve, or return.

The seasonal term for natural gas is a sinusoid peaking in January
(winter heating demand), added to log returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COMMODITIES = {
    "WTI": {"spot0": 78.0, "vol": 0.32, "drift": 0.02},
    "NATGAS": {"spot0": 3.20, "vol": 0.65, "drift": 0.0, "seasonal_amp": 0.35},
    "GOLD": {"spot0": 2650.0, "vol": 0.15, "drift": 0.03},
}

N_DAYS = 252


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_spot_paths(seed: int = 42, n_days: int = N_DAYS) -> pd.DataFrame:
    """Daily spot paths for the three commodities, 252 trading days."""
    rng = _rng(seed)
    dates = pd.bdate_range("2026-01-02", periods=n_days)
    frames = {}
    for name, spec in COMMODITIES.items():
        dt = 1.0 / 252.0
        shocks = rng.standard_normal(n_days)
        log_ret = (spec["drift"] - 0.5 * spec["vol"] ** 2) * dt + spec["vol"] * np.sqrt(dt) * shocks
        if "seasonal_amp" in spec:
            day_of_year = np.array([d.dayofyear for d in dates])
            seasonal = spec["seasonal_amp"] * np.sin(
                2.0 * np.pi * (day_of_year - 15) / 365.0
            )
            log_ret = log_ret + seasonal * dt * 10.0
        path = spec["spot0"] * np.exp(np.cumsum(log_ret))
        frames[name] = path
    out = pd.DataFrame(frames, index=dates)
    out.index.name = "date"
    return out


def generate_futures_curve(
    spot: float, r: float, storage_cost: float, convenience_yield: float, months: int = 12
) -> pd.DataFrame:
    """A futures curve from cost of carry: F(T) = S * exp((r + u - y) * T).

    Positive (r + u - y) gives contango (curve rising with maturity);
    negative gives backwardation (curve falling). ``months`` contracts
    are monthly out to ``months`` months.
    """
    tenors = [(m + 1) / 12.0 for m in range(months)]
    carry = r + storage_cost - convenience_yield
    prices = [spot * float(np.exp(carry * t)) for t in tenors]
    return pd.DataFrame(
        {"tenor_years": tenors, "futures_price": prices}
    )
