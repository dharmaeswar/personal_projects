"""Champion / challenger / benchmark fraud-scoring models.

Champion: logistic regression on scaled features.
Challenger: gradient boosting classifier.
Benchmark: base-rate predictor (predicts the overall training fraud rate).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from fraud_validation.data import FEATURES


def _feature_matrix(df: pd.DataFrame) -> np.ndarray:
    return df[FEATURES].to_numpy(dtype=float)


class ChampionModel:
    """Logistic-regression fraud scorer (scaled features)."""

    def __init__(self) -> None:
        self.scaler = StandardScaler()
        self.model = LogisticRegression(max_iter=1000, C=1.0)

    def fit(self, df: pd.DataFrame) -> "ChampionModel":
        x = self.scaler.fit_transform(_feature_matrix(df))
        self.model.fit(x, df["is_fraud"].to_numpy())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = self.scaler.transform(_feature_matrix(df))
        return self.model.predict_proba(x)[:, 1]


class ChallengerModel:
    """Gradient-boosting fraud scorer."""

    def __init__(self) -> None:
        self.model = GradientBoostingClassifier(
            n_estimators=150, learning_rate=0.08, max_depth=3,
            subsample=0.9, random_state=42,
        )

    def fit(self, df: pd.DataFrame) -> "ChallengerModel":
        self.model.fit(_feature_matrix(df), df["is_fraud"].to_numpy())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(_feature_matrix(df))[:, 1]


class BenchmarkModel:
    """Base-rate predictor: every transaction scores the training fraud rate."""

    def __init__(self) -> None:
        self.base_rate = 0.0

    def fit(self, df: pd.DataFrame) -> "BenchmarkModel":
        self.base_rate = float(df["is_fraud"].mean())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.full(len(df), self.base_rate)


def fit_all(train: pd.DataFrame) -> dict:
    """Fit champion, challenger, and benchmark on the training set."""
    champion = ChampionModel().fit(train)
    challenger = ChallengerModel().fit(train)
    benchmark = BenchmarkModel().fit(train)
    return {"champion": champion, "challenger": challenger, "benchmark": benchmark}


def predict_all(models: dict, df: pd.DataFrame) -> dict:
    """Score ``df`` with every fitted model; returns {name: probabilities}."""
    return {name: model.predict(df) for name, model in models.items()}
