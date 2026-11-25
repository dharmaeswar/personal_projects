"""Statistical and ML modelling for the energy telemetry layer.

Feature engineering, two models, and validation — the Landmark workflow:
develop features, build statistical or machine-learning models, test their
performance, interpret the results, and benchmark against a known reference
(the analytic ROP formula in `energy_data`, used here the way the beam and
thermal simulators are used as ground truth elsewhere in this project).

Models:
- OLS (ordinary least squares, NumPy) on standardised features — the
  deployable model: its coefficients serialise cleanly to JSON, so a
  software engineer can embed it in the energy software.
- Random forest (scikit-learn) — the challenger: a stronger fit that shows
  what a non-linear model buys, and a check on whether the linear model is
  leaving real signal on the table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .energy_data import FORMATION_FACTOR, analytic_rop

BASE_FEATURES = ["depth_ft", "wob_klbf", "rpm", "mud_flow_gpm", "torque_klbf_ft"]
ENGINEERED_FEATURES = [
    "specific_energy",
    "wob_per_depth",
    "flow_per_rpm",
    "torque_per_wob",
]
FEATURES = BASE_FEATURES + ENGINEERED_FEATURES
TARGET = "rop_ft_hr"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered features to a cleaned telemetry frame.

    specific_energy: torque * rpm — mechanical energy at the bit.
    wob_per_depth: weight on bit normalised by depth.
    flow_per_rpm: mud flow per revolution — hole-cleaning capacity.
    torque_per_wob: torque per unit weight — friction/formation response.
    """
    out = df.copy()
    out["specific_energy"] = out["torque_klbf_ft"] * out["rpm"] / 1000.0
    out["wob_per_depth"] = out["wob_klbf"] / out["depth_ft"] * 1000.0
    out["flow_per_rpm"] = out["mud_flow_gpm"] / out["rpm"]
    out["torque_per_wob"] = out["torque_klbf_ft"] / out["wob_klbf"]
    return out


def train_holdout_split(df: pd.DataFrame, test_fraction: float = 0.2,
                        seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Random train/holdout split (seeded, reproducible)."""
    shuffled = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    n_test = max(1, int(round(len(shuffled) * test_fraction)))
    return shuffled.iloc[:-n_test], shuffled.iloc[-n_test:]


class Standardiser:
    """Mean/std standardisation fitted on training data, reused at predict time."""

    def __init__(self) -> None:
        self.mean_: np.ndarray | None = None
        self.scale_: np.ndarray | None = None

    def fit(self, x: np.ndarray) -> "Standardiser":
        self.mean_ = x.mean(axis=0)
        self.scale_ = x.std(axis=0)
        self.scale_[self.scale_ == 0] = 1.0
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        assert self.mean_ is not None and self.scale_ is not None
        return (x - self.mean_) / self.scale_


class OlsModel:
    """OLS regression on standardised features (NumPy least squares)."""

    def __init__(self) -> None:
        self.standardiser = Standardiser()
        self.coef_: np.ndarray | None = None
        self.intercept_: float | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "OlsModel":
        self.standardiser.fit(x)
        xs = self.standardiser.transform(x)
        design = np.column_stack([np.ones(len(xs)), xs])
        solution, *_ = np.linalg.lstsq(design, y, rcond=None)
        self.intercept_ = float(solution[0])
        self.coef_ = solution[1:]
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        assert self.coef_ is not None and self.intercept_ is not None
        xs = self.standardiser.transform(x)
        return self.intercept_ + xs @ self.coef_


def fit_random_forest(x_train: np.ndarray, y_train: np.ndarray,
                      seed: int = 7) -> RandomForestRegressor:
    """Random-forest challenger model (scikit-learn, seeded)."""
    model = RandomForestRegressor(n_estimators=200, random_state=seed,
                                  n_jobs=1)
    model.fit(x_train, y_train)
    return model


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 3),
        "r2": round(float(r2_score(y_true, y_pred)), 3),
    }


def validate_models(df: pd.DataFrame, test_fraction: float = 0.2,
                    seed: int = 7) -> dict:
    """Train both models, score them on holdout, benchmark vs analytic truth.

    Returns metrics for the OLS model, the random-forest challenger, a naive
    mean baseline, and the analytic ROP formula itself on the same holdout —
    so a reviewer can see how much of the error is the model and how much
    is noise in the data.
    """
    featured = build_features(df)
    train, holdout = train_holdout_split(featured, test_fraction, seed)
    x_train = train[FEATURES].to_numpy(dtype=float)
    y_train = train[TARGET].to_numpy(dtype=float)
    x_test = holdout[FEATURES].to_numpy(dtype=float)
    y_test = holdout[TARGET].to_numpy(dtype=float)

    ols = OlsModel().fit(x_train, y_train)
    ols_pred = np.clip(ols.predict(x_test), 0.5, 120.0)
    forest = fit_random_forest(x_train, y_train, seed)
    forest_pred = np.clip(forest.predict(x_test), 0.5, 120.0)
    baseline_pred = np.full_like(y_test, y_train.mean(), dtype=float)
    truth = np.array([
        analytic_rop(row.wob_klbf, row.rpm, row.mud_flow_gpm, row.depth_ft,
                     FORMATION_FACTOR[row.well_id])
        for row in holdout.itertuples()
    ])

    result = {
        "n_train": int(len(train)),
        "n_holdout": int(len(holdout)),
        "features": FEATURES,
        "ols": _metrics(y_test, ols_pred),
        "random_forest": _metrics(y_test, forest_pred),
        "naive_mean_baseline": _metrics(y_test, baseline_pred),
        "analytic_truth_vs_observed": _metrics(y_test, truth),
        "ols_vs_analytic_truth": _metrics(truth, ols_pred),
        "ols_coefficients": {
            name: round(float(c), 4)
            for name, c in zip(FEATURES, ols.coef_)
        },
        "ols_intercept": round(float(ols.intercept_), 4),
        "forest_feature_importance": {
            name: round(float(v), 4)
            for name, v in zip(FEATURES, forest.feature_importances_)
        },
    }
    return result


def sensitivity_analysis(ols: OlsModel, x_reference: np.ndarray,
                         feature_names: list[str] | None = None,
                         bump: float = 0.10) -> list[dict]:
    """One-at-a-time sensitivity: bump each feature +10%, report the mean
    predicted ROP change. Names which inputs the model leans on most."""
    names = feature_names or FEATURES
    base = ols.predict(x_reference)
    rows = []
    for i, name in enumerate(names):
        bumped = x_reference.copy()
        bumped[:, i] = bumped[:, i] * (1.0 + bump)
        changed = ols.predict(bumped)
        rows.append({
            "feature": name,
            "bump_pct": bump * 100,
            "mean_predicted_change_ft_hr": round(
                float(np.mean(changed - base)), 3),
        })
    return rows


def model_card(validation: dict, cleaning_report: dict,
               dictionary_version: str) -> dict:
    """Model card: methods, assumptions, limitations — the document a
    reviewer or a software engineer reads before trusting the model."""
    return {
        "model": "OLS regression on standardised drilling-telemetry features "
                 "(random forest as challenger)",
        "target": "rate of penetration (rop_ft_hr)",
        "data_dictionary_version": dictionary_version,
        "rows_used": validation["n_train"] + validation["n_holdout"],
        "rows_dropped_in_cleaning": cleaning_report.get("rows_dropped_total"),
        "holdout_metrics_ols": validation["ols"],
        "holdout_metrics_random_forest": validation["random_forest"],
        "naive_mean_baseline": validation["naive_mean_baseline"],
        "assumptions": [
            "ROP follows a power-law in weight on bit, rotary speed and mud "
            "flow, with a per-well formation factor for rock hardness.",
            "Sensor readings are independent draws; no time-series "
            "autocorrelation is modelled.",
            "Cleaning drops missing, out-of-range and duplicate rows rather "
            "than imputing them.",
        ],
        "limitations": [
            "Synthetic, seeded data only — no real well or production data.",
            "No geology, bit type, or formation-top information is available "
            "as a feature; the formation factor is unobserved.",
            "OLS is linear on standardised features; the random forest is a "
            "challenger, not the deployed model.",
            "Model was validated on a random holdout, not on a new well — "
            "performance on an unseen formation is untested.",
        ],
    }
