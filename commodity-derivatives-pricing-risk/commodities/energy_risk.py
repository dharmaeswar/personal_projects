"""Energy risk analytics: earnings at risk, potential future exposure,
and weather-derivative (degree-day) pricing.

These are the risk measures a Quantitative Risk Management team at an
energy marketer runs every day: EaR on the merchant generation book,
PFE on the forward/swap book, and valuation of the weather derivatives
used to hedge temperature-driven demand. All inputs are synthetic and
seeded; nothing here is a claim about any real price, temperature, or
return.

Approximations are labelled where they are made: forward MtM is
undiscounted in the PFE grid, and simulated commodities move with
independent shocks.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

ENERGY_SPOTS = {
    "POWER": {"spot0": 45.0, "vol": 0.55, "drift": 0.0},
    "NATGAS": {"spot0": 3.20, "vol": 0.65, "drift": 0.0},
    "WTI": {"spot0": 78.0, "vol": 0.32, "drift": 0.02},
}


def _seasonal_factor(month: int, commodity: str) -> float:
    """Seasonal price uplift: power peaks in summer and winter,
    natural gas peaks in winter. Returns a multiplier on the price."""
    if commodity == "POWER":
        # Peaks in July (summer cooling) and January (winter heating).
        return 1.0 + 0.25 * math.cos(2.0 * math.pi * (month - 7) / 12.0) ** 2 \
            + 0.15 * math.cos(2.0 * math.pi * (month - 1) / 12.0) ** 2
    if commodity == "NATGAS":
        return 1.0 + 0.35 * math.cos(2.0 * math.pi * (month - 1) / 12.0) ** 2
    return 1.0


def simulate_monthly_prices(
    commodities: list[str],
    n_paths: int = 20_000,
    months: int = 12,
    seed: int = 7,
) -> dict[str, np.ndarray]:
    """Monthly price paths (n_paths x months) per commodity, GBM with a
    seasonal multiplier applied to each month's price level."""
    rng = np.random.default_rng(seed)
    out: dict[str, np.ndarray] = {}
    for name in commodities:
        spec = ENERGY_SPOTS[name]
        dt = 1.0 / 12.0
        shocks = rng.standard_normal((n_paths, months))
        log_ret = (spec["drift"] - 0.5 * spec["vol"] ** 2) * dt \
            + spec["vol"] * math.sqrt(dt) * shocks
        paths = spec["spot0"] * np.exp(np.cumsum(log_ret, axis=1))
        seasonal = np.array([_seasonal_factor(m + 1, name) for m in range(months)])
        out[name] = paths * seasonal
    return out


def earnings_at_risk(
    assets: list[dict],
    n_paths: int = 20_000,
    months: int = 12,
    seed: int = 7,
) -> dict:
    """Earnings at Risk for a merchant power/gas portfolio.

    Each asset is {"commodity": "POWER"/"NATGAS", "volume_mwh": float,
    "fixed_cost": float} — monthly volume sold at the simulated price,
    less a fixed monthly cost. EaR(conf) = expected earnings minus the
    (1 - conf) quantile of earnings: the earnings shortfall that is
    only exceeded with probability (1 - conf).
    """
    commodities = sorted({a["commodity"] for a in assets})
    prices = simulate_monthly_prices(commodities, n_paths, months, seed)
    earnings = np.zeros(n_paths)
    for asset in assets:
        monthly = prices[asset["commodity"]] * float(asset["volume_mwh"]) \
            - float(asset["fixed_cost"])
        earnings += monthly.sum(axis=1)
    expected = float(earnings.mean())
    ear95 = expected - float(np.quantile(earnings, 0.05))
    ear99 = expected - float(np.quantile(earnings, 0.01))
    return {
        "expected_earnings": round(expected, 2),
        "ear_95": round(ear95, 2),
        "ear_99": round(ear99, 2),
        "worst_earnings": round(float(earnings.min()), 2),
        "best_earnings": round(float(earnings.max()), 2),
        "n_paths": n_paths,
    }


def potential_future_exposure(
    forwards: list[dict],
    confidence: float = 0.95,
    n_paths: int = 20_000,
    seed: int = 11,
) -> pd.DataFrame:
    """Potential Future Exposure for a forward/swap book.

    Each forward is {"commodity", "qty", "fixed_price",
    "maturity_years"}. At each monthly horizon out to the longest
    maturity, MtM = qty * (simulated spot - fixed price); exposure is
    max(MtM, 0) and PFE is its confidence quantile across paths.
    MtM is undiscounted here — a stated approximation. Forwards past
    maturity contribute zero at later horizons.
    """
    commodities = sorted({f["commodity"] for f in forwards})
    max_years = max(float(f["maturity_years"]) for f in forwards)
    months = max(1, int(math.ceil(max_years * 12)))
    prices = simulate_monthly_prices(commodities, n_paths, months, seed)
    rows = []
    for m in range(1, months + 1):
        horizon = m / 12.0
        exposure = np.zeros(n_paths)
        for fwd in forwards:
            if float(fwd["maturity_years"]) + 1e-9 < horizon:
                continue
            mtm = float(fwd["qty"]) * (
                prices[fwd["commodity"]][:, m - 1] - float(fwd["fixed_price"])
            )
            exposure += np.maximum(mtm, 0.0)
        rows.append(
            {
                "horizon_years": round(horizon, 3),
                "pfe": round(float(np.quantile(exposure, confidence)), 2),
                "expected_exposure": round(float(exposure.mean()), 2),
            }
        )
    return pd.DataFrame(rows)


def simulate_degree_days(
    n_days: int = 31,
    base_temp_f: float = 38.0,
    temp_vol: float = 6.0,
    mean_reversion: float = 0.35,
    n_paths: int = 50_000,
    seed: int = 13,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulate daily average temperatures for one month and return the
    heating-degree-day (HDD) and cooling-degree-day (CDD) index per
    path. Temperature follows a mean-reverting AR(1) around a seasonal
    base; degree days are measured against a 65F balance point, the
    standard convention."""
    rng = np.random.default_rng(seed)
    temps = np.full((n_paths, n_days), base_temp_f)
    for d in range(1, n_days):
        temps[:, d] = base_temp_f + (1.0 - mean_reversion) * (
            temps[:, d - 1] - base_temp_f
        ) + temp_vol * math.sqrt(mean_reversion) * rng.standard_normal(n_paths)
    hdd = np.maximum(65.0 - temps, 0.0).sum(axis=1)
    cdd = np.maximum(temps - 65.0, 0.0).sum(axis=1)
    return hdd, cdd


def weather_degree_day_option(
    kind: str = "HDD",
    option: str = "call",
    strike: float = 700.0,
    tick: float = 20_000.0,
    r: float = 0.045,
    T: float = 1.0 / 12.0,
    n_days: int = 31,
    base_temp_f: float = 38.0,
    n_paths: int = 50_000,
    seed: int = 13,
) -> dict:
    """Price a weather derivative: a call or put on a monthly HDD or
    CDD index, by Monte Carlo on simulated daily temperatures.

    Payoff = tick * max(index - strike, 0) for a call (or the reverse
    for a put), discounted at ``r``. The price, the expected index,
    and the Monte Carlo standard error are returned.
    """
    hdd, cdd = simulate_degree_days(
        n_days=n_days, base_temp_f=base_temp_f, n_paths=n_paths, seed=seed
    )
    index = hdd if kind.upper() == "HDD" else cdd
    if option.lower() == "call":
        payoff = tick * np.maximum(index - strike, 0.0)
    else:
        payoff = tick * np.maximum(strike - index, 0.0)
    discount = math.exp(-r * T)
    price = float(payoff.mean()) * discount
    se = float(payoff.std(ddof=1) / math.sqrt(n_paths)) * discount
    return {
        "kind": kind.upper(),
        "option": option.lower(),
        "strike": strike,
        "tick": tick,
        "expected_index": round(float(index.mean()), 2),
        "index_std": round(float(index.std()), 2),
        "price": round(price, 2),
        "std_error": round(se, 2),
        "n_paths": n_paths,
    }
