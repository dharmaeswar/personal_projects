"""Threshold sensitivity and alert-review burden.

A compliance alert model lives or dies by its operating threshold:
lower it and investigators drown in false positives; raise it and
SAR-worthy activity slips through. This module prices that trade-off.
"""

import numpy as np


def threshold_table(y_true, scores, thresholds=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7)):
    """Alerts, precision, recall and F1 at each candidate threshold."""
    y_true = np.asarray(y_true)
    scores = np.asarray(scores)
    total_pos = int(y_true.sum())
    rows = []
    for t in thresholds:
        pred = (scores >= t).astype(int)
        tp = int(((pred == 1) & (y_true == 1)).sum())
        fp = int(((pred == 1) & (y_true == 0)).sum())
        fn = total_pos - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / total_pos if total_pos else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append(
            {
                "threshold": t,
                "alerts": int(pred.sum()),
                "alert_rate_pct": 100.0 * pred.mean(),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            }
        )
    return rows


def review_burden(alerts, minutes_per_alert=20.0, investigators=5, hours_per_day=7.5):
    """Human-review workload implied by an alert count.

    Returns total review hours and the working days a team of
    investigators needs to clear the queue.
    """
    total_hours = alerts * minutes_per_alert / 60.0
    capacity_hours_per_day = investigators * hours_per_day
    return {
        "alerts": int(alerts),
        "review_hours": round(total_hours, 1),
        "team_days": round(total_hours / capacity_hours_per_day, 2),
    }
