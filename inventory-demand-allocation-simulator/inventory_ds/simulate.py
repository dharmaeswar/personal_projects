"""Monte Carlo fulfillment simulation.

Draws weekly demand for each style-region from a normal distribution centred on
the forecast (standard deviation estimated from history), then allocates inventory
under each policy and records fill rate, unmet units and cost. Percentile bands
show the range of outcomes instead of a single point estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .allocate import allocation_metrics, greedy_allocate, lp_allocate


def _demand_sd(history: pd.DataFrame) -> dict:
    """Residual standard deviation per style-region around a 4-week rolling mean."""
    sds = {}
    for (style, region), sub in history.groupby(["style", "region"]):
        s = sub.sort_values("week")["demand"].astype(float)
        resid = s - s.rolling(4, center=True).mean()
        sds[(style, region)] = float(np.nanstd(resid)) or float(s.std() * 0.1)
    return sds


def simulate(forecast: pd.DataFrame, inventory: pd.DataFrame, history: pd.DataFrame,
             n_reps: int = 500, seed: int = 99) -> pd.DataFrame:
    """Run `n_reps` demand draws; return one row per replication per policy."""
    rng = np.random.default_rng(seed)
    sds = _demand_sd(history)
    rows = []
    for rep in range(n_reps):
        drawn = forecast.copy()
        noise = [rng.normal(0, sds[(r["style"], r["region"])]) for _, r in drawn.iterrows()]
        drawn["forecast_week1"] = np.maximum(0, drawn["forecast_week1"] + noise)
        for alloc_fn in (greedy_allocate, lp_allocate):
            alloc = alloc_fn(drawn, inventory)
            m = allocation_metrics(alloc, drawn)
            m["replication"] = rep
            rows.append(m)
    return pd.DataFrame(rows)


def simulation_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Mean and 5th/95th percentile of fill rate and cost per policy."""
    out = []
    for policy, sub in results.groupby("policy"):
        out.append({
            "policy": policy,
            "mean_fill_rate": round(float(sub["fill_rate"].mean()), 4),
            "p5_fill_rate": round(float(sub["fill_rate"].quantile(0.05)), 4),
            "p95_fill_rate": round(float(sub["fill_rate"].quantile(0.95)), 4),
            "mean_total_cost": round(float(sub["total_cost"].mean()), 2),
            "p5_total_cost": round(float(sub["total_cost"].quantile(0.05)), 2),
            "p95_total_cost": round(float(sub["total_cost"].quantile(0.95)), 2),
            "mean_unmet_units": round(float(sub["unmet_units"].mean()), 1),
        })
    return pd.DataFrame(out)
