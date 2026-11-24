"""Outcomes analysis for the alert model: backtesting the way a
second-line validator would — ROC-AUC, KS statistic, confusion matrix
at the operating threshold, precision/recall/F1, decile capture, and
calibration by predicted decile.
"""

import numpy as np
from sklearn.metrics import confusion_matrix, roc_auc_score


def ks_statistic(y_true, scores):
    """Two-sample KS statistic between scores of positives and negatives."""
    pos = np.sort(scores[y_true == 1])
    neg = np.sort(scores[y_true == 0])
    if len(pos) == 0 or len(neg) == 0:
        return 0.0
    grid = np.sort(np.concatenate([pos, neg]))
    cdf_pos = np.searchsorted(pos, grid, side="right") / len(pos)
    cdf_neg = np.searchsorted(neg, grid, side="right") / len(neg)
    return float(np.max(np.abs(cdf_pos - cdf_neg)))


def outcomes_summary(y_true, scores, threshold=0.5):
    """Backtest summary at one operating threshold."""
    y_true = np.asarray(y_true)
    scores = np.asarray(scores)
    pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold,
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "ks": ks_statistic(y_true, scores),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "alert_rate": float(pred.mean()),
        "base_rate": float(y_true.mean()),
    }


def decile_capture(y_true, scores):
    """Share of SAR-worthy cases captured in each predicted-score decile.

    Decile 10 is the highest-scored 10% of transactions.
    """
    y_true = np.asarray(y_true)
    scores = np.asarray(scores)
    order = np.argsort(scores)
    n = len(scores)
    total_pos = int(y_true.sum())
    out = []
    for d in range(10):
        lo = d * n // 10
        hi = (d + 1) * n // 10
        idx = order[lo:hi]
        captured = int(y_true[idx].sum())
        out.append(
            {
                "decile": d + 1,
                "count": int(hi - lo),
                "positives": captured,
                "capture_pct": 100.0 * captured / total_pos if total_pos else 0.0,
                "mean_score": float(scores[idx].mean()),
            }
        )
    return out


def calibration_by_decile(y_true, scores):
    """Mean predicted vs observed SAR-worthy rate by predicted decile."""
    y_true = np.asarray(y_true)
    scores = np.asarray(scores)
    order = np.argsort(scores)
    n = len(scores)
    out = []
    for d in range(10):
        lo = d * n // 10
        hi = (d + 1) * n // 10
        idx = order[lo:hi]
        out.append(
            {
                "decile": d + 1,
                "mean_predicted": float(scores[idx].mean()),
                "observed_rate": float(y_true[idx].mean()),
            }
        )
    return out
