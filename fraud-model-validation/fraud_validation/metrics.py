"""Outcomes-analysis metrics for fraud scoring: pure functions on arrays."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """ROC-AUC; 0.5 for a constant (uninformative) score."""
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    if len(np.unique(y_score)) < 2:
        return 0.5
    return float(roc_auc_score(y_true, y_score))


def ks_statistic(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Kolmogorov-Smirnov statistic between fraud and non-fraud score CDFs."""
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    fraud = np.sort(y_score[y_true == 1])
    legit = np.sort(y_score[y_true == 0])
    if len(fraud) == 0 or len(legit) == 0:
        return 0.0
    grid = np.sort(np.unique(y_score))
    cdf_fraud = np.searchsorted(fraud, grid, side="right") / len(fraud)
    cdf_legit = np.searchsorted(legit, grid, side="right") / len(legit)
    return float(np.max(np.abs(cdf_fraud - cdf_legit)))


def confusion_matrix_at(
    y_true: np.ndarray, y_score: np.ndarray, threshold: float
) -> dict:
    """Confusion counts at a score threshold."""
    y_true = np.asarray(y_true)
    pred = (np.asarray(y_score, dtype=float) >= threshold).astype(int)
    return {
        "tp": int(np.sum((pred == 1) & (y_true == 1))),
        "fp": int(np.sum((pred == 1) & (y_true == 0))),
        "tn": int(np.sum((pred == 0) & (y_true == 0))),
        "fn": int(np.sum((pred == 0) & (y_true == 1))),
    }


def precision_recall_f1(cm: dict) -> dict:
    """Precision, recall, and F1 from a confusion-count dict."""
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": float(precision), "recall": float(recall), "f1": float(f1)}


def tune_threshold(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Threshold in (0, 1) that maximises F1 over a grid search."""
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in np.linspace(0.01, 0.99, 99):
        f1 = precision_recall_f1(confusion_matrix_at(y_true, y_score, threshold))["f1"]
        if f1 > best_f1:
            best_f1, best_threshold = f1, float(threshold)
    return best_threshold


def decile_capture(y_true: np.ndarray, y_score: np.ndarray, n_deciles: int = 10) -> pd.DataFrame:
    """Rank-ordering: fraud capture rate per score decile (decile 1 = riskiest).

    Capture rates sum to 1 across deciles.
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    order = np.argsort(-y_score)
    sorted_true = y_true[order]
    total_fraud = int(sorted_true.sum())
    rows = []
    for d in range(n_deciles):
        chunk = sorted_true[d * len(sorted_true) // n_deciles:(d + 1) * len(sorted_true) // n_deciles]
        rows.append(
            {
                "decile": d + 1,
                "n": int(len(chunk)),
                "fraud": int(chunk.sum()),
                "fraud_rate": float(chunk.mean()) if len(chunk) else 0.0,
                "capture_rate": float(chunk.sum() / total_fraud) if total_fraud else 0.0,
            }
        )
    return pd.DataFrame(rows)


def calibration_by_decile(
    y_true: np.ndarray, y_score: np.ndarray, n_deciles: int = 10
) -> pd.DataFrame:
    """Calibration: mean predicted vs observed fraud rate per predicted decile.

    Deciles are ascending by predicted score (decile 1 = lowest scores).
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    order = np.argsort(y_score)
    sorted_true, sorted_score = y_true[order], y_score[order]
    rows = []
    for d in range(n_deciles):
        lo = d * len(sorted_true) // n_deciles
        hi = (d + 1) * len(sorted_true) // n_deciles
        rows.append(
            {
                "decile": d + 1,
                "mean_predicted": float(sorted_score[lo:hi].mean()),
                "observed_rate": float(sorted_true[lo:hi].mean()),
                "n": int(hi - lo),
            }
        )
    return pd.DataFrame(rows)


def evaluate_model(
    y_true: np.ndarray, y_score: np.ndarray, threshold: float | None = None
) -> dict:
    """Full metric bundle for one model's scores."""
    if threshold is None:
        threshold = tune_threshold(y_true, y_score)
    cm = confusion_matrix_at(y_true, y_score, threshold)
    return {
        "threshold": threshold,
        "roc_auc": roc_auc(y_true, y_score),
        "ks": ks_statistic(y_true, y_score),
        "confusion": cm,
        **precision_recall_f1(cm),
        "decile_capture": decile_capture(y_true, y_score),
        "calibration": calibration_by_decile(y_true, y_score),
    }
