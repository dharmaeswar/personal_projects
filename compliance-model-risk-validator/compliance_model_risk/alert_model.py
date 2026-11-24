"""Champion / challenger / benchmark alert models.

Champion: logistic regression on scaled features.
Challenger: gradient boosting classifier.
Benchmark: base-rate predictor (overall SAR-worthy rate, no features).
"""

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import FEATURES


def train_champion(train):
    """Logistic-regression alert scorer."""
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=42))
    model.fit(train[FEATURES], train["sar_worthy"])
    return model


def train_challenger(train):
    """Gradient-boosting alert scorer."""
    model = GradientBoostingClassifier(random_state=42)
    model.fit(train[FEATURES], train["sar_worthy"])
    return model


def train_benchmark(train):
    """Base-rate predictor: every transaction scores the overall rate."""

    class _BaseRate:
        def __init__(self, rate):
            self.rate = float(rate)

        def predict_proba(self, X):
            n = len(X)
            return np.column_stack([np.full(n, 1.0 - self.rate), np.full(n, self.rate)])

    return _BaseRate(train["sar_worthy"].mean())


def predict_scores(model, frame):
    """Predicted SAR-worthy probability for each row."""
    return model.predict_proba(frame[FEATURES])[:, 1]
