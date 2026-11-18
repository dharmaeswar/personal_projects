"""Champion / challenger / benchmark loss-forecasting models.

Champion: logistic regression on the default indicator (calibrated to a
loss-rate forecast by scaling with the portfolio's mean loss severity).
Challenger: linear regression directly on the observed loss rate.
Benchmark: historical average loss rate (no features).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "gdp_growth",
    "unemployment_rate",
    "hpi_growth",
    "credit_spread",
    "ltv",
    "fico_score",
]


def _feature_matrix(df: pd.DataFrame) -> np.ndarray:
    return df[FEATURES].to_numpy(dtype=float)


class ChampionModel:
    """Logistic-regression default forecaster, mapped to a loss-rate forecast."""

    def __init__(self) -> None:
        self.scaler = StandardScaler()
        self.model = LogisticRegression(max_iter=1000, C=1.0)
        self.severity = 1.0  # mean loss rate among defaulted loans, fitted on train

    def fit(self, df: pd.DataFrame) -> "ChampionModel":
        x = self.scaler.fit_transform(_feature_matrix(df))
        self.model.fit(x, df["defaulted"].to_numpy())
        defaulted = df[df["defaulted"] == 1]
        self.severity = float(defaulted["observed_loss_rate"].mean()) if len(defaulted) else 1.0
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = self.scaler.transform(_feature_matrix(df))
        prob = self.model.predict_proba(x)[:, 1]
        return np.clip(prob * self.severity, 0.0, 1.0)


class ChallengerModel:
    """Linear regression directly on the observed loss rate."""

    def __init__(self) -> None:
        self.scaler = StandardScaler()
        self.model = LinearRegression()

    def fit(self, df: pd.DataFrame) -> "ChallengerModel":
        x = self.scaler.fit_transform(_feature_matrix(df))
        self.model.fit(x, df["observed_loss_rate"].to_numpy())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = self.scaler.transform(_feature_matrix(df))
        return np.clip(self.model.predict(x), 0.0, 1.0)


class BenchmarkModel:
    """Historical average loss rate (no features)."""

    def __init__(self) -> None:
        self.mean_loss = 0.0

    def fit(self, df: pd.DataFrame) -> "BenchmarkModel":
        self.mean_loss = float(df["observed_loss_rate"].mean())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.full(len(df), self.mean_loss)


def fit_all(train: pd.DataFrame) -> dict:
    """Fit champion, challenger, and benchmark on the training set."""
    champion = ChampionModel().fit(train)
    challenger = ChallengerModel().fit(train)
    benchmark = BenchmarkModel().fit(train)
    return {"champion": champion, "challenger": challenger, "benchmark": benchmark}
