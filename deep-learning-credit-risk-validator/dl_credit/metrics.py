"""Outcomes metrics for model validation: ROC-AUC, KS, Gini, confusion
matrix, decile capture, calibration, Brier score, and PSI drift.

All metrics are implemented from first principles (rank-based AUC,
empirical CDFs for KS, binned PSI) so the validation numbers do not
depend on a library's defaults.
"""
import numpy as np


def roc_auc(y, p):
    """Mann-Whitney rank AUC; 0.5 when one class is absent."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    if len(np.unique(y)) < 2:
        return 0.5
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    # Average ranks for ties.
    _, inv, counts = np.unique(p, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks)
    avg = sums / counts
    ranks = avg[inv]
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def gini(y, p):
    return float(2 * roc_auc(y, p) - 1)


def ks_statistic(y, p):
    """Max gap between the cumulative default / non-default distributions.

    CDFs are compared at each distinct score value, so tied scores (e.g.
    every prediction identical) correctly give KS 0 instead of an
    artefact of the sort order.
    """
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    n_pos = max(int(y.sum()), 1)
    n_neg = max(int((1 - y).sum()), 1)
    ks = 0.0
    for t in np.unique(p):
        f_pos = float(((p <= t) & (y == 1)).sum()) / n_pos
        f_neg = float(((p <= t) & (y == 0)).sum()) / n_neg
        ks = max(ks, abs(f_pos - f_neg))
    return float(ks)


def confusion_matrix(y, pred):
    y = np.asarray(y).astype(int)
    pred = np.asarray(pred).astype(int)
    tp = int(((y == 1) & (pred == 1)).sum())
    tn = int(((y == 0) & (pred == 0)).sum())
    fp = int(((y == 0) & (pred == 1)).sum())
    fn = int(((y == 1) & (pred == 0)).sum())
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def precision_recall_f1(cm):
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": float(precision), "recall": float(recall), "f1": float(f1)}


def decile_capture(y, p, n_bins=10):
    """Share of all defaults captured by each predicted-score decile."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    order = np.argsort(-p)
    ys = y[order]
    total = max(ys.sum(), 1)
    out = []
    for b in range(n_bins):
        lo = b * len(y) // n_bins
        hi = (b + 1) * len(y) // n_bins
        out.append(float(ys[lo:hi].sum() / total))
    return out


def calibration_by_decile(y, p, n_bins=10):
    """Mean predicted vs observed default rate per score decile."""
    y = np.asarray(y).astype(float)
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    ys, ps = y[order], p[order]
    rows = []
    for b in range(n_bins):
        lo = b * len(y) // n_bins
        hi = (b + 1) * len(y) // n_bins
        rows.append({
            "decile": b + 1,
            "n": int(hi - lo),
            "mean_predicted": float(ps[lo:hi].mean()),
            "observed_rate": float(ys[lo:hi].mean()),
        })
    return rows


def brier_score(y, p):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def psi(expected, actual, bins=10):
    """Population Stability Index between two score distributions."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    qs = np.quantile(expected, np.linspace(0, 1, bins + 1))
    qs[0], qs[-1] = -np.inf, np.inf
    qs = np.unique(qs)
    e_hist, _ = np.histogram(expected, bins=qs)
    a_hist, _ = np.histogram(actual, bins=qs)
    e_prop = np.maximum(e_hist / max(len(expected), 1), 1e-4)
    a_prop = np.maximum(a_hist / max(len(actual), 1), 1e-4)
    return float(np.sum((a_prop - e_prop) * np.log(a_prop / e_prop)))


def outcomes_summary(y, p, threshold=0.5):
    """One dict with the headline validation numbers for a model."""
    pred = (np.asarray(p) >= threshold).astype(int)
    cm = confusion_matrix(y, pred)
    prf = precision_recall_f1(cm)
    cal = calibration_by_decile(y, p)
    max_cal_gap = max(abs(r["mean_predicted"] - r["observed_rate"]) for r in cal)
    return {
        "n": int(len(y)),
        "default_rate": float(np.mean(y)),
        "roc_auc": roc_auc(y, p),
        "gini": gini(y, p),
        "ks": ks_statistic(y, p),
        "brier": brier_score(y, p),
        "confusion": cm,
        "precision": prf["precision"],
        "recall": prf["recall"],
        "f1": prf["f1"],
        "top_decile_capture": decile_capture(y, p)[0],
        "max_calibration_gap": float(max_cal_gap),
    }
