"""Champion and challenger underwriting models (pure Python).

Champion: the developer's logistic regression on the raw underwriting
features. Challenger: an independent logistic regression that adds
interaction terms (revenue x coverage, score x years in business) and
recalibrates on the validation sample. Both are fit from scratch here so
the validator can reproduce the developer's code and compare outputs.
"""

import math

from sb_credit_validator.features import engineer_features

FEATURES = ["annual_revenue", "years_in_business", "cashflow_coverage",
            "credit_score", "loan_amount", "industry_risk"]


def _sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _standardize(rows, features):
    means = {}
    sds = {}
    for f in features:
        vals = [r[f] for r in rows]
        m = sum(vals) / len(vals)
        sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        means[f] = m
        sds[f] = sd
    return means, sds


def _design_row(row, means, sds, interactions):
    x = [1.0]
    for f in FEATURES:
        x.append((row[f] - means[f]) / sds[f])
    if interactions:
        x.append(((row["annual_revenue"] - means["annual_revenue"])
                  / sds["annual_revenue"])
                 * ((row["cashflow_coverage"] - means["cashflow_coverage"])
                    / sds["cashflow_coverage"]))
        x.append(((row["credit_score"] - means["credit_score"])
                  / sds["credit_score"])
                 * ((row["years_in_business"] - means["years_in_business"])
                    / sds["years_in_business"]))
    return x


class LogisticModel:
    """Logistic regression fit by batch gradient descent."""

    def __init__(self, interactions=False, lr=0.05, epochs=400):
        self.interactions = interactions
        self.lr = lr
        self.epochs = epochs
        self.weights = None
        self.means = None
        self.sds = None

    def fit(self, rows):
        self.means, self.sds = _standardize(rows, FEATURES)
        n_feat = len(FEATURES) + 1 + (2 if self.interactions else 0)
        w = [0.0] * n_feat
        X = [_design_row(r, self.means, self.sds, self.interactions)
             for r in rows]
        y = [r["defaulted"] for r in rows]
        for _ in range(self.epochs):
            grad = [0.0] * n_feat
            for xi, yi in zip(X, y):
                p = _sigmoid(sum(wi * xij for wi, xij in zip(w, xi)))
                err = p - yi
                for j in range(n_feat):
                    grad[j] += err * xi[j]
            for j in range(n_feat):
                w[j] -= self.lr * grad[j] / len(rows)
        self.weights = w
        return self

    def predict_proba(self, rows):
        out = []
        for r in rows:
            x = _design_row(r, self.means, self.sds, self.interactions)
            out.append(_sigmoid(sum(wi * xij
                                    for wi, xij in zip(self.weights, x))))
        return out


class GradientBoostingChallenger:
    """Second challenger: scikit-learn gradient boosting on engineered features.

    Same fit/predict_proba interface as LogisticModel, so the validator can
    score it, compare it with the champion, and test whether the gain is
    statistically significant. The import is lazy so the pure-Python
    logistic path still works on a machine without scikit-learn.
    """

    def __init__(self, max_iter=200, learning_rate=0.08, max_depth=3,
                 random_state=42):
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.random_state = random_state
        self.model = None

    def fit(self, rows):
        from sklearn.ensemble import HistGradientBoostingClassifier
        X = [engineer_features(r) for r in rows]
        y = [r["defaulted"] for r in rows]
        self.model = HistGradientBoostingClassifier(
            max_iter=self.max_iter, learning_rate=self.learning_rate,
            max_depth=self.max_depth, random_state=self.random_state)
        self.model.fit(X, y)
        return self

    def predict_proba(self, rows):
        X = [engineer_features(r) for r in rows]
        return [float(p) for p in self.model.predict_proba(X)[:, 1]]
