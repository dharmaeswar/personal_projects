"""Seeded synthetic market data for the validation demos.

Nothing here is real market data: five synthetic assets, 252 trading
days, a factor-driven covariance, and an alpha signal that is genuinely
(but noisily) predictive. The seed makes every run reproducible.
"""

import numpy as np

ASSETS = ["US_EQUITY", "INTL_EQUITY", "TREASURY", "CREDIT", "REIT"]


def synthetic_market(seed=42, n_days=252):
    """Generate synthetic daily returns, signals and forward returns.

    Returns a dict with ``returns`` (n_days x 5), ``signals`` (n_days x 5),
    ``forward_returns`` (n_days x 5, next-day returns aligned to signals),
    ``expected_returns`` and ``cov``.
    """
    rng = np.random.default_rng(seed)
    vols = np.array([0.16, 0.18, 0.05, 0.08, 0.20]) / np.sqrt(252)
    corr = np.array(
        [
            [1.00, 0.70, -0.20, 0.30, 0.55],
            [0.70, 1.00, -0.15, 0.25, 0.45],
            [-0.20, -0.15, 1.00, 0.45, -0.10],
            [0.30, 0.25, 0.45, 1.00, 0.20],
            [0.55, 0.45, -0.10, 0.20, 1.00],
        ]
    )
    cov = np.outer(vols, vols) * corr
    mu = np.array([0.08, 0.07, 0.03, 0.045, 0.09]) / 252
    returns = rng.multivariate_normal(mu, cov, size=n_days)
    # Alpha signal: next-day return plus noise, so IC is positive but modest.
    noise = rng.normal(0.0, 1.0, size=returns.shape)
    forward = np.roll(returns, -1, axis=0)
    forward[-1] = rng.multivariate_normal(mu, cov)
    signals = 0.35 * forward / (np.std(forward) + 1e-12) + noise
    return {
        "returns": returns,
        "signals": signals,
        "forward_returns": forward,
        "expected_returns": mu * 252,
        "cov": cov * 252,
        "assets": ASSETS,
    }
