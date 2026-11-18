"""Ongoing monitoring: Population Stability Index (PSI) and mean drift."""

from __future__ import annotations

import numpy as np
import pandas as pd

PSI_BINS = 10


def mean_drift(reference: np.ndarray, current: np.ndarray) -> float:
    """Difference in means between a current sample and the reference."""
    return float(np.mean(np.asarray(current, dtype=float)) - np.mean(np.asarray(reference, dtype=float)))


def psi(reference: np.ndarray, current: np.ndarray, n_bins: int = PSI_BINS) -> float:
    """Population Stability Index between a reference and a current sample.

    Bins are defined by reference quantiles. PSI < 0.1 is generally stable,
    0.1-0.25 is a moderate shift, > 0.25 is a significant shift.
    """
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    quantiles = np.linspace(0, 100, n_bins + 1)
    edges = np.unique(np.percentile(reference, quantiles))
    if len(edges) < 2:
        return 0.0
    ref_counts, _ = np.histogram(reference, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)
    ref_pct = np.maximum(ref_counts / len(reference), 1e-4)
    cur_pct = np.maximum(cur_counts / len(current), 1e-4)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def drift_report(reference_df: pd.DataFrame, current_df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """Per-column mean drift and PSI between a reference and current sample."""
    rows = []
    for col in columns:
        rows.append(
            {
                "column": col,
                "mean_drift": mean_drift(
                    reference_df[col].to_numpy(), current_df[col].to_numpy()
                ),
                "psi": psi(reference_df[col].to_numpy(), current_df[col].to_numpy()),
            }
        )
    return pd.DataFrame(rows)
