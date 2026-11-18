"""Fairness / slice analysis: model behaviour by synthetic segment (region)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fraud_validation.metrics import confusion_matrix_at


def slice_metrics(
    y_true: np.ndarray,
    y_score: np.ndarray,
    segments: pd.Series,
    threshold: float,
) -> pd.DataFrame:
    """Per-segment flag rate and fraud capture at a fixed threshold.

    Flag rate = share of the segment's transactions flagged as fraud.
    Fraud capture = share of ALL fraud in the sample that is flagged in this
    segment (sums to overall recall across segments).
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    segments = pd.Series(np.asarray(segments))
    flagged = y_score >= threshold
    total_fraud = int((y_true == 1).sum())
    rows = []
    for segment in sorted(segments.unique()):
        mask = (segments == segment).to_numpy()
        cm = confusion_matrix_at(y_true[mask], y_score[mask], threshold)
        rows.append(
            {
                "segment": segment,
                "n": int(mask.sum()),
                "fraud": int(y_true[mask].sum()),
                "fraud_rate": float(y_true[mask].mean()),
                "flag_rate": float(flagged[mask].mean()),
                "fraud_capture": float(cm["tp"] / total_fraud) if total_fraud else 0.0,
                "precision": float(cm["tp"] / (cm["tp"] + cm["fp"])) if (cm["tp"] + cm["fp"]) else 0.0,
                "recall": float(cm["tp"] / (cm["tp"] + cm["fn"])) if (cm["tp"] + cm["fn"]) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def max_flag_rate_gap(slice_df: pd.DataFrame) -> float:
    """Largest difference in flag rate between any two segments."""
    return float(slice_df["flag_rate"].max() - slice_df["flag_rate"].min())
