"""Predictive scoring for the claims lakehouse: paid-amount model + outlier flags.

Spark / Databricks mapping: this mirrors a Spark ML Pipeline on Databricks
(VectorAssembler + StandardScaler + OneHotEncoder + LinearRegression) run as
a Databricks notebook step after the gold publish, batch-scoring the silver
claims and writing the scores to a Delta table (here: gold/model_scores).
Locally it runs with scikit-learn on the same cleansed frame.

The model predicts paid_amount from billed_amount, service month, plan,
diagnosis group, and age band — deliberately NOT from adjustment, so the
residual measures whether a claim's paid amount looks unusual for its billed
amount and cohort. Claims with |residual z-score| >= 3 are flagged
"high_residual" for human review. The model never auto-denies, auto-pays, or
otherwise decides a claim: flags are a review queue only (see the
responsible-AI note in the README). All data is synthetic (seed 42).
"""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC_FEATURES = ["billed_amount", "service_month_num"]
CATEGORICAL_FEATURES = ["plan", "diag_group", "age_band"]
TARGET = "paid_amount"
Z_THRESHOLD = 3.0
SEED = 42


def build_features(df):
    """Feature frame + target from a cleansed claims frame."""
    x = df[["billed_amount", "plan", "diag_group", "age_band"]].copy()
    x["service_month_num"] = pd.to_datetime(df["service_date"]).dt.month.astype(float)
    return x, df[TARGET].astype(float)


def train_paid_model(cleansed, seed=SEED):
    """Train the paid-amount model; return model + test metrics + residual scale."""
    x, y = build_features(cleansed)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=seed)
    model = Pipeline([
        ("prep", ColumnTransformer([
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
             CATEGORICAL_FEATURES),
        ])),
        ("reg", Ridge(alpha=1.0)),
    ])
    model.fit(x_train, y_train)
    train_pred = model.predict(x_train)
    test_pred = model.predict(x_test)
    residual_std = float(np.std(y_train - train_pred))
    metrics = {
        "test_mae": round(float(mean_absolute_error(y_test, test_pred)), 2),
        "test_r2": round(float(r2_score(y_test, test_pred)), 4),
        "train_residual_std": round(residual_std, 2),
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
    }
    return model, metrics, residual_std


def score_claims(model, residual_std, df, z_threshold=Z_THRESHOLD):
    """Score every claim: predicted paid, residual, z-score, review flag."""
    x, y = build_features(df)
    predicted = np.asarray(model.predict(x), dtype=float)
    actual = np.asarray(y, dtype=float)
    residual = actual - predicted
    residual_z = residual / residual_std if residual_std else np.zeros_like(residual)
    scores = pd.DataFrame({
        "claim_id": df["claim_id"].values,
        "member_id": df["member_id"].values,
        "service_date": pd.to_datetime(df["service_date"]).values,
        "plan": df["plan"].values,
        "diag_group": df["diag_group"].values,
        "billed_amount": df["billed_amount"].astype(float).values,
        "paid_amount": actual,
        "predicted_paid": np.round(predicted, 2),
        "residual": np.round(residual, 2),
        "residual_z": np.round(residual_z, 2),
        "model_flag": np.where(np.abs(residual_z) >= z_threshold,
                               "high_residual", ""),
    })
    return scores
