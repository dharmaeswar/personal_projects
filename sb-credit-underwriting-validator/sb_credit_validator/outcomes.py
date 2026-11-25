"""Outcomes analysis: rank-ordering, calibration, threshold performance."""

import math


def roc_auc(y_true, scores):
    """Mann-Whitney AUC. Returns 0.5 when one class is absent."""
    pos = [s for y, s in zip(y_true, scores) if y == 1]
    neg = [s for y, s in zip(y_true, scores) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def ks_statistic(y_true, scores):
    """Two-sample KS on score distributions (defaults vs non-defaults)."""
    pos = sorted(s for y, s in zip(y_true, scores) if y == 1)
    neg = sorted(s for y, s in zip(y_true, scores) if y == 0)
    if not pos or not neg:
        return 0.0
    grid = sorted(set(scores))
    best = 0.0
    for t in grid:
        cdf_p = sum(1 for s in pos if s <= t) / len(pos)
        cdf_n = sum(1 for s in neg if s <= t) / len(neg)
        best = max(best, abs(cdf_p - cdf_n))
    return best


def gini(y_true, scores):
    return 2.0 * roc_auc(y_true, scores) - 1.0


def decile_capture(y_true, scores, n_deciles=10):
    """Share of all defaults captured by each predicted-PD decile (best first)."""
    paired = sorted(zip(scores, y_true), reverse=True)
    total_defaults = sum(y_true) or 1
    per = len(paired) // n_deciles
    out = []
    for d in range(n_deciles):
        chunk = paired[d * per:(d + 1) * per] if d < n_deciles - 1 else paired[d * per:]
        out.append(round(sum(y for _, y in chunk) / total_defaults, 3))
    return out


def calibration_by_decile(y_true, scores, n_deciles=10):
    """Mean predicted PD vs observed default rate per decile."""
    paired = sorted(zip(scores, y_true), reverse=True)
    per = len(paired) // n_deciles
    out = []
    for d in range(n_deciles):
        chunk = paired[d * per:(d + 1) * per] if d < n_deciles - 1 else paired[d * per:]
        mean_pred = sum(s for s, _ in chunk) / len(chunk)
        obs = sum(y for _, y in chunk) / len(chunk)
        out.append((round(mean_pred, 3), round(obs, 3)))
    return out


def confusion_at_threshold(y_true, scores, threshold=0.5):
    tp = fp = tn = fn = 0
    for y, s in zip(y_true, scores):
        pred = 1 if s >= threshold else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3)}
