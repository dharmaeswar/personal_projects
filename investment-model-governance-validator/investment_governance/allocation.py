"""Asset-allocation validation: risk parity, diversification, drawdown."""

import numpy as np


def risk_parity_weights(cov, max_iter=500, tol=1e-10):
    """Risk-parity weights via cyclic coordinate descent (Spinu, 2013).

    Each asset contributes equally to portfolio risk. Long-only, sums to 1.
    """
    cov = np.asarray(cov, dtype=float)
    n = cov.shape[0]
    w = np.full(n, 1.0 / n)
    for _ in range(max_iter):
        w_prev = w.copy()
        sigma = cov @ w
        port_var = float(w @ sigma)
        target = port_var / n
        for i in range(n):
            # Solve for w_i so that w_i * (cov w)_i = target, holding others fixed.
            a = cov[i, i]
            b = float(cov[i] @ w - a * w[i])
            disc = b * b + 4.0 * a * target
            w[i] = (-b + np.sqrt(max(disc, 0.0))) / (2.0 * a)
        w = np.maximum(w, 0.0)
        w = w / w.sum()
        if np.max(np.abs(w - w_prev)) < tol:
            break
    return w


def risk_contributions(weights, cov):
    """Each asset's share of total portfolio variance (sums to 1)."""
    w = np.asarray(weights, dtype=float)
    cov = np.asarray(cov, dtype=float)
    marginal = cov @ w
    port_var = float(w @ marginal)
    if port_var <= 0:
        return np.full(len(w), 1.0 / len(w))
    return (w * marginal) / port_var


def diversification_ratio(weights, vols, cov):
    """Weighted-average asset vol / portfolio vol; > 1 means diversified."""
    w = np.asarray(weights, dtype=float)
    vols = np.asarray(vols, dtype=float)
    port_vol = float(np.sqrt(max(w @ np.asarray(cov, dtype=float) @ w, 0.0)))
    if port_vol == 0:
        return 1.0
    return float(np.sum(w * vols) / port_vol)


def max_drawdown(cumulative_returns):
    """Largest peak-to-trough fall of a cumulative-return series."""
    c = np.asarray(cumulative_returns, dtype=float)
    if len(c) == 0:
        return 0.0
    peak = np.maximum.accumulate(c)
    dd = (c - peak) / np.where(peak == 0, 1.0, peak)
    return float(-np.min(dd))
