"""Synthetic credit-application data.

All data is generated with a seeded RNG. Features are deliberately simple
so the training pipeline is transparent and reproducible:

- income: annual income in USD
- debt_ratio: monthly debt payments / monthly income, 0..1
- credit_history_years: length of credit history
- delinquencies: number of past delinquencies
- amount: requested credit amount in USD

The label is 1 when the application would default, generated from a known
logistic rule plus noise, so a trained model can recover real signal.
"""

import math
import random

FEATURES = ["income", "debt_ratio", "credit_history_years", "delinquencies", "amount"]


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x)) if x >= -700 else 0.0


def generate_applications(n, seed=42):
    """Return a list of (features dict, label int) synthetic applications."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        income = rng.uniform(25_000, 180_000)
        debt_ratio = rng.uniform(0.05, 0.85)
        history = rng.uniform(0.5, 25.0)
        delinq = rng.choice([0, 0, 0, 1, 1, 2, 3])
        amount = rng.uniform(500, 25_000)
        z = (
            -1.2
            + 2.6 * debt_ratio
            - 0.000012 * income
            - 0.06 * history
            + 0.55 * delinq
            + 0.00003 * amount
        )
        label = 1 if rng.random() < _sigmoid(z) else 0
        rows.append(
            (
                {
                    "income": round(income, 2),
                    "debt_ratio": round(debt_ratio, 4),
                    "credit_history_years": round(history, 2),
                    "delinquencies": delinq,
                    "amount": round(amount, 2),
                },
                label,
            )
        )
    return rows


def to_matrix(rows):
    """Convert rows to (X, y) with features in FEATURES order."""
    X = [[float(r[0][f]) for f in FEATURES] for r in rows]
    y = [r[1] for r in rows]
    return X, y


def scale_features(X, means=None, stds=None):
    """Standardise columns; returns (scaled X, means, stds)."""
    n_cols = len(X[0])
    if means is None:
        means = [sum(row[c] for row in X) / len(X) for c in range(n_cols)]
    if stds is None:
        stds = []
        for c in range(n_cols):
            var = sum((row[c] - means[c]) ** 2 for row in X) / len(X)
            stds.append(math.sqrt(var) or 1.0)
    scaled = [[(row[c] - means[c]) / stds[c] for c in range(n_cols)] for row in X]
    return scaled, means, stds
