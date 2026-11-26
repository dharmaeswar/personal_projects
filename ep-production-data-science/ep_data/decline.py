"""Arps decline-curve fitting and EUR estimation.

Fits the hyperbolic Arps model q(t) = qi / (1 + b*di*t)^(1/b) to a single
well's monthly oil rate by a small grid search over (b, di) with qi solved
by least squares on the log scale. EUR (estimated ultimate recovery) is
the integral of the fitted curve out to a 30-year economic limit, capped
where the rate falls below 5 bbl/day.
"""

from __future__ import annotations

import numpy as np

ECONOMIC_LIMIT_BBL_PER_DAY = 5.0
EUR_HORIZON_MONTHS = 360


def arps_rate(qi: float, di: float, b: float, t: np.ndarray) -> np.ndarray:
    """Hyperbolic Arps rate; b=0 is the exponential special case."""
    t = np.asarray(t, dtype=float)
    if b == 0:
        return qi * np.exp(-di * t)
    return qi / (1.0 + b * di * t) ** (1.0 / b)


def fit_decline(months: np.ndarray, rates_bbl_per_day: np.ndarray) -> dict:
    """Grid-search fit of (qi, di, b). Returns params plus fit quality."""
    t = np.asarray(months, dtype=float)
    q = np.asarray(rates_bbl_per_day, dtype=float)
    mask = q > 0
    t, q = t[mask], q[mask]
    if len(q) < 6:
        raise ValueError("need at least 6 positive monthly rates to fit")
    log_q = np.log(q)
    best = None
    for b in np.linspace(0.0, 2.0, 41):
        for di in np.linspace(0.01, 0.30, 58):
            # log q = log qi - (1/b) log(1 + b di t); b=0 -> log qi - di t
            if b == 0:
                x = t
            else:
                x = np.log(1.0 + b * di * t) / b
            # Least squares for intercept log(qi) with slope fixed at -1.
            log_qi = np.mean(log_q + x)
            resid = log_q - (log_qi - x)
            sse = float(np.sum(resid ** 2))
            if best is None or sse < best["sse"]:
                best = {"qi": float(np.exp(log_qi)), "di": float(di),
                        "b": float(b), "sse": sse}
    n = len(q)
    ss_tot = float(np.sum((log_q - log_q.mean()) ** 2))
    best["r2_log"] = 1.0 - best["sse"] / ss_tot if ss_tot > 0 else 0.0
    best["n_months"] = n
    return best


def estimate_eur(fit: dict, months_observed: int) -> dict:
    """Integrate the fitted curve to the economic limit (or 30 years)."""
    qi, di, b = fit["qi"], fit["di"], fit["b"]
    t = np.arange(0, EUR_HORIZON_MONTHS, dtype=float)
    rates = arps_rate(qi, di, b, t)  # bbl/day
    alive = rates >= ECONOMIC_LIMIT_BBL_PER_DAY
    # EUR counts produced volume from first production to the limit.
    eur_bbl = float(np.sum(rates[alive]) * 30.0)
    return {
        "eur_bbl": eur_bbl,
        "months_to_limit": int(alive.sum()),
        "final_rate_bbl_per_day": float(rates[alive][-1]) if alive.any() else 0.0,
    }
