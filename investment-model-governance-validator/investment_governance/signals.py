"""Alpha / signal model validation.

Checks a cross-sectional alpha signal the way a second-line model risk
team would: predictive power (information coefficient), how fast that
power decays with horizon, turnover, and hit rate. All inputs are plain
NumPy arrays; all data used here is synthetic and seeded.
"""

import numpy as np


def _rank(values):
    """Ordinal ranks (0..n-1) with average ranks for ties."""
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    # Average ranks within ties.
    _, inverse, counts = np.unique(
        values, return_inverse=True, return_counts=True
    )
    if np.any(counts > 1):
        sums = np.zeros(len(counts))
        np.add.at(sums, inverse, ranks)
        ranks = sums[inverse] / counts[inverse]
    return ranks


def pearson_ic(signals, forward_returns):
    """Pearson information coefficient between signal and forward return."""
    s = np.asarray(signals, dtype=float)
    r = np.asarray(forward_returns, dtype=float)
    if len(s) != len(r) or len(s) < 3:
        raise ValueError("need at least 3 paired observations")
    if np.std(s) == 0 or np.std(r) == 0:
        return 0.0
    return float(np.corrcoef(s, r)[0, 1])


def spearman_ic(signals, forward_returns):
    """Rank (Spearman) information coefficient."""
    return pearson_ic(_rank(signals), _rank(forward_returns))


def ic_decay(signals, forward_returns_by_horizon):
    """IC per horizon; a healthy signal decays smoothly, never inverts.

    ``forward_returns_by_horizon`` maps a horizon label (e.g. "1d", "5d")
    to an array of forward returns aligned with ``signals``.
    """
    return {
        horizon: spearman_ic(signals, rets)
        for horizon, rets in forward_returns_by_horizon.items()
    }


def signal_turnover(weights_today, weights_yesterday):
    """One-way turnover: 0.5 * sum |w_t - w_{t-1}|, in [0, 1]."""
    w0 = np.asarray(weights_yesterday, dtype=float)
    w1 = np.asarray(weights_today, dtype=float)
    if w0.shape != w1.shape:
        raise ValueError("weight vectors must have the same shape")
    return float(0.5 * np.sum(np.abs(w1 - w0)))


def hit_rate(signals, forward_returns):
    """Share of names where the signal's sign matches the return's sign."""
    s = np.asarray(signals, dtype=float)
    r = np.asarray(forward_returns, dtype=float)
    mask = (s != 0) & (r != 0)
    if not np.any(mask):
        return 0.0
    return float(np.mean(np.sign(s[mask]) == np.sign(r[mask])))


def information_ratio(ic_series):
    """Mean IC / std IC — stability of the signal's predictive power."""
    ic = np.asarray(ic_series, dtype=float)
    if len(ic) < 2 or np.std(ic, ddof=1) < 1e-12:
        return 0.0
    return float(np.mean(ic) / np.std(ic, ddof=1))
