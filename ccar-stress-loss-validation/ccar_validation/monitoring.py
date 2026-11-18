"""Ongoing monitoring: mean drift (bps) and Population Stability Index (PSI)."""

from __future__ import annotations

import numpy as np
import pandas as pd

PSI_BINS = 10


def mean_drift_bps(reference: np.ndarray, current: np.ndarray) -> float:
    """Mean drift expressed in basis points (1 bp = 0.01 percentage point of rate)."""
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    return float((np.mean(current) - np.mean(reference)) * 10_000.0)


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
    """Per-column drift (bps) and PSI between a reference and current sample."""
    rows = []
    for col in columns:
        rows.append(
            {
                "column": col,
                "mean_drift_bps": mean_drift_bps(
                    reference_df[col].to_numpy(), current_df[col].to_numpy()
                ),
                "psi": psi(reference_df[col].to_numpy(), current_df[col].to_numpy()),
            }
        )
    return pd.DataFrame(rows)
