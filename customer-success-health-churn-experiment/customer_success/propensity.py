"""Churn and expansion propensity models: logistic regression from scratch.

Standard library only (no scikit-learn at runtime): standardization, batch
gradient descent with L2, and rank-based AUC / log-loss / accuracy so the
model is judged on held-out customers, not on the data it was fit to.
"""
import math


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x)) if x > -30 else 0.0


def _standardize(rows):
    cols = list(zip(*rows))
    means = [sum(c) / len(c) for c in cols]
    sds = [(sum((v - m) ** 2 for v in c) / len(c)) ** 0.5 or 1.0 for c, m in zip(cols, means)]
    scaled = [[(v - m) / s for v, m, s in zip(r, means, sds)] for r in rows]
    return scaled, means, sds


def train_logistic(rows, labels, lr=0.1, epochs=400, l2=0.01):
    """Fit logistic regression; return (weights incl. intercept, means, sds)."""
    scaled, means, sds = _standardize(rows)
    w = [0.0] * (len(rows[0]) + 1)
    n = len(rows)
    for _ in range(epochs):
        grads = [0.0] * len(w)
        for x, y in zip(scaled, labels):
            p = _sigmoid(w[0] + sum(wi * xi for wi, xi in zip(w[1:], x)))
            err = p - y
            grads[0] += err
            for j, xi in enumerate(x):
                grads[j + 1] += err * xi
        for j in range(len(w)):
            reg = l2 * w[j] if j else 0.0
            w[j] -= lr * (grads[j] / n + reg)
    return w, means, sds


def predict_proba(model, rows):
    w, means, sds = model
    out = []
    for r in rows:
        x = [(v - m) / s for v, m, s in zip(r, means, sds)]
        out.append(_sigmoid(w[0] + sum(wi * xi for wi, xi in zip(w[1:], x))))
    return out


def auc(labels, scores):
    """Rank-based AUC (Mann-Whitney): P(positive scores above negative)."""
    pos = [s for y, s in zip(labels, scores) if y == 1]
    neg = [s for y, s in zip(labels, scores) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = ties = 0.0
    for p in pos:
        for q in neg:
            if p > q:
                wins += 1
            elif p == q:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def log_loss(labels, scores):
    total = 0.0
    for y, p in zip(labels, scores):
        p = min(max(p, 1e-9), 1 - 1e-9)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(labels)


def accuracy(labels, scores, threshold=0.5):
    return sum(1 for y, p in zip(labels, scores) if (p >= threshold) == bool(y)) / len(labels)


def evaluate(model, rows, labels):
    scores = predict_proba(model, rows)
    return {
        "auc": round(auc(labels, scores), 3),
        "log_loss": round(log_loss(labels, scores), 3),
        "accuracy": round(accuracy(labels, scores), 3),
        "n": len(labels),
    }


def train_test_split(rows, labels, test_frac=0.25, seed=7):
    import random

    idx = list(range(len(rows)))
    random.Random(seed).shuffle(idx)
    cut = int(len(idx) * (1 - test_frac))
    tr, te = idx[:cut], idx[cut:]
    return ([rows[i] for i in tr], [labels[i] for i in tr],
            [rows[i] for i in te], [labels[i] for i in te])
