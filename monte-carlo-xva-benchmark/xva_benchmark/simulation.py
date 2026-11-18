"""Geometric Brownian motion path simulation (exact stepping, seeded)."""

from __future__ import annotations

import numpy as np


def time_grid(horizon_years: float, n_steps: int) -> np.ndarray:
    """Uniform time grid including t=0, shape (n_steps + 1,)."""
    return np.linspace(0.0, horizon_years, n_steps + 1)


def simulate_gbm(spot: float, volatility: float, drift: float,
                 times: np.ndarray, n_paths: int,
                 rng: np.random.Generator) -> np.ndarray:
    """Simulate GBM paths. Returns array of shape (n_paths, len(times)).

    Exact lognormal stepping:
        S_{i+1} = S_i * exp((drift - sigma^2/2) dt + sigma sqrt(dt) Z)
    The first column is exactly the spot price.
    """
    times = np.asarray(times, dtype=float)
    dt = np.diff(times)
    z = rng.standard_normal((n_paths, len(dt)))
    log_increments = ((drift - 0.5 * volatility ** 2) * dt
                      + volatility * np.sqrt(dt) * z)
    log_paths = np.cumsum(log_increments, axis=1)
    paths = spot * np.exp(log_paths)
    initial = np.full((n_paths, 1), float(spot))
    return np.hstack([initial, paths])


def simulate_terminal(spot: float, volatility: float, drift: float,
                      horizon: float, n_paths: int,
                      rng: np.random.Generator,
                      antithetic: bool = True) -> np.ndarray:
    """Terminal GBM values at a single horizon, optionally antithetic.

    Antithetic variates (Z and -Z pairs) are used by the benchmark checks to
    cut the Monte Carlo standard error well inside the tolerance band.
    """
    if antithetic:
        n_pairs = (n_paths + 1) // 2
        z = rng.standard_normal(n_pairs)
        z = np.concatenate([z, -z])[:n_paths]
    else:
        z = rng.standard_normal(n_paths)
    drift_term = (drift - 0.5 * volatility ** 2) * horizon
    return spot * np.exp(drift_term + volatility * np.sqrt(horizon) * z)
