"""Challenger models scored through the same interface as the MLP.

- Logistic regression, also from scratch in NumPy (gradient descent).
- Base-rate benchmark: predicts the overall default rate for everyone.
Both are fit on the same training split and scored on the same test split,
so the comparison with the deep-learning candidate is apples-to-apples.
"""
import numpy as np


class LogisticRegression:
    """Binary logistic regression trained with batch gradient descent."""

    def __init__(self, lr=0.1, epochs=500, l2=1e-4, seed=7):
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.seed = seed
        self.coef_ = None
        self.intercept_ = 0.0

    def fit(self, X, y):
        rng = np.random.default_rng(self.seed)
        n, d = X.shape
        y = y.astype(float).reshape(-1)
        self.coef_ = rng.normal(0.0, 0.01, d)
        for _ in range(self.epochs):
            z = np.clip(X @ self.coef_ + self.intercept_, -30, 30)
            p = 1.0 / (1.0 + np.exp(-z))
            grad = (X.T @ (p - y)) / n + self.l2 * self.coef_
            self.coef_ -= self.lr * grad
            self.intercept_ -= self.lr * float(np.mean(p - y))
        return self

    def predict_proba(self, X):
        z = np.clip(np.asarray(X, dtype=float) @ self.coef_ + self.intercept_, -30, 30)
        return 1.0 / (1.0 + np.exp(-z))

    def predict(self, X, threshold=0.5):
        return (self.predict_proba(X) >= threshold).astype(int)


class BaseRateModel:
    """Predicts the training default rate for every application."""

    def __init__(self):
        self.rate_ = 0.0

    def fit(self, X, y):
        self.rate_ = float(np.mean(y))
        return self

    def predict_proba(self, X):
        return np.full(len(X), self.rate_)

    def predict(self, X, threshold=0.5):
        return (self.predict_proba(X) >= threshold).astype(int)
