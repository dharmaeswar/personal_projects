"""Ongoing monitoring: population stability and drift between the
validation population and a later production population.
"""

import numpy as np


def psi(expected, actual, bins=10):
    """Population Stability Index between two score distributions."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    edges = np.quantile(expected, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if len(edges) < 2:
        return 0.0
    e_counts, _ = np.histogram(expected, bins=edges)
    a_counts, _ = np.histogram(actual, bins=edges)
    e_pct = np.clip(e_counts / len(expected), 1e-6, None)
    a_pct = np.clip(a_counts / len(actual), 1e-6, None)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


def mean_drift_pct(baseline, current):
    """Percentage change in the mean of a feature or score."""
    baseline = np.asarray(baseline, dtype=float)
    current = np.asarray(current, dtype=float)
    base_mean = baseline.mean()
    if base_mean == 0:
        return 0.0
    return float(100.0 * (current.mean() - base_mean) / abs(base_mean))
