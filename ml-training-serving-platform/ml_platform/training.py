"""Training pipeline: plain-Python logistic regression + evaluation metrics.

No third-party ML libraries — gradient descent on standardised features,
so the whole pipeline runs on the standard library.
"""

import math
import random

from .data import FEATURES, generate_applications, scale_features, to_matrix


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x)) if x >= -700 else 0.0


class LogisticModel:
    """Logistic regression with weights, means/stds, and feature list."""

    def __init__(self, weights, bias, means, stds, features=None):
        self.weights = weights
        self.bias = bias
        self.means = means
        self.stds = stds
        self.features = features or list(FEATURES)

    def predict_proba(self, features):
        x = [(features[f] - m) / s for f, m, s in zip(self.features, self.means, self.stds)]
        z = self.bias + sum(w * v for w, v in zip(self.weights, x))
        return _sigmoid(z)

    def predict(self, features, threshold=0.5):
        return 1 if self.predict_proba(features) >= threshold else 0

    def to_dict(self):
        return {
            "weights": self.weights,
            "bias": self.bias,
            "means": self.means,
            "stds": self.stds,
            "features": self.features,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["weights"], d["bias"], d["means"], d["stds"], d["features"])


def train(rows, epochs=300, lr=0.1, seed=7):
    """Train on (features, label) rows; returns a LogisticModel."""
    X, y = to_matrix(rows)
    Xs, means, stds = scale_features(X)
    rng = random.Random(seed)
    weights = [rng.uniform(-0.1, 0.1) for _ in FEATURES]
    bias = 0.0
    n = len(Xs)
    for _ in range(epochs):
        grad_w = [0.0] * len(FEATURES)
        grad_b = 0.0
        for xi, yi in zip(Xs, y):
            z = bias + sum(w * v for w, v in zip(weights, xi))
            p = _sigmoid(z)
            err = p - yi
            for j in range(len(weights)):
                grad_w[j] += err * xi[j]
            grad_b += err
        weights = [w - lr * g / n for w, g in zip(weights, grad_w)]
        bias -= lr * grad_b / n
    return LogisticModel(weights, bias, means, stds)


def evaluate(model, rows):
    """Return accuracy, precision, recall, and AUC on held-out rows."""
    scored = [(model.predict_proba(r[0]), r[1]) for r in rows]
    tp = sum(1 for p, y in scored if p >= 0.5 and y == 1)
    tn = sum(1 for p, y in scored if p < 0.5 and y == 0)
    fp = sum(1 for p, y in scored if p >= 0.5 and y == 0)
    fn = sum(1 for p, y in scored if p < 0.5 and y == 1)
    total = len(scored) or 1
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    # AUC via pairwise comparison.
    pos = [p for p, y in scored if y == 1]
    neg = [p for p, y in scored if y == 0]
    if not pos or not neg:
        auc = 0.5
    else:
        wins = sum(1 for p in pos for q in neg if p > q) + 0.5 * sum(
            1 for p in pos for q in neg if p == q
        )
        auc = wins / (len(pos) * len(neg))
    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "auc": round(auc, 4),
        "n": len(scored),
    }


def train_pipeline(n_train=2000, n_test=500, seed=42, **train_kwargs):
    """Generate data, train, evaluate. Returns (model, metrics, baseline_rows)."""
    rows = generate_applications(n_train + n_test, seed=seed)
    train_rows, test_rows = rows[:n_train], rows[n_train:]
    model = train(train_rows, **train_kwargs)
    metrics = evaluate(model, test_rows)
    return model, metrics, train_rows
