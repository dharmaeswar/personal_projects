"""Model validation and deployment packaging.

Validation runs the checks a model-risk reviewer would ask for:
- backtest error (RMSE / MAPE) against a naive persistence baseline
- residual bias: mean signed error should be near zero
- decline-curve fit quality per well (R^2 on the log scale)
- data-quality gate: the cleaning log must show zero nulls left and no
  negative rates

Deployment packaging serialises the trained model (weights, feature list,
standardisation, training window, version) to a JSON artifact that a
deployment platform can load without the training code, plus a `predict`
entry point that loads that artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .decline import arps_rate, fit_decline
from .features import FEATURE_COLUMNS
from .forecast import backtest

MODEL_VERSION = "1.0.0"


def validate(df: pd.DataFrame, cleaning_log: dict) -> dict:
    """Run all validation checks. Returns a report dict."""
    report: dict = {"checks": {}}

    bt = backtest(df)
    report["backtest"] = {
        "rmse_bbl": bt["rmse_bbl"],
        "mape": bt["mape"],
        "baseline_persistence_rmse_bbl": bt["baseline_persistence_rmse_bbl"],
        "beats_baseline": bt["beats_baseline"],
        "n_train": bt["n_train"],
        "n_test": bt["n_test"],
    }
    report["checks"]["backtest_beats_baseline"] = bool(bt["beats_baseline"])

    # Residual bias on the test window.
    work = df.sort_values(["api_number", "month_index"]).copy()
    work["target_next_oil"] = work.groupby("api_number")["oil_bbl"].shift(-1)
    work = work.dropna(subset=["target_next_oil"])
    test = work[work["month_index"] >= 24]
    from .forecast import _design, predict
    pred = predict(bt["model"], _design(test))
    actual = test["target_next_oil"].to_numpy(dtype=float)
    mean_err = float(np.mean(pred - actual))
    report["residual_bias_bbl"] = mean_err
    report["checks"]["residual_bias_small"] = abs(mean_err) < 0.05 * actual.mean()

    # Decline-curve fit quality per well (first 24 months of daily rates).
    r2s = []
    for _, well in df.groupby("api_number"):
        w = well.sort_values("month_index").head(24)
        try:
            fit = fit_decline(w["month_index"].to_numpy(),
                              (w["oil_bbl"] / 30.0).to_numpy())
            r2s.append(fit["r2_log"])
        except ValueError:
            continue
    report["decline_fit_median_r2_log"] = float(np.median(r2s)) if r2s else 0.0
    report["decline_fit_wells"] = len(r2s)
    report["checks"]["decline_fit_ok"] = report["decline_fit_median_r2_log"] > 0.80

    report["checks"]["data_quality_gate"] = (
        cleaning_log.get("nulls_remaining", -1) == 0
        and cleaning_log.get("negative_rows_dropped", -1) >= 0)
    report["all_checks_pass"] = all(report["checks"].values())
    return report


def package_model(model: dict, path: str | Path) -> Path:
    """Write the deployment artifact (JSON) for the trained model."""
    artifact = {
        "model": "ridge_next_month_oil_bbl",
        "version": MODEL_VERSION,
        "features": FEATURE_COLUMNS,
        "alpha": model["alpha"],
        "weights": [float(w) for w in model["weights"]],
        "feature_mean": [float(v) for v in model["mean"]],
        "feature_std": [float(v) for v in model["std"]],
        "training_window_months": 24,
        "notes": ("Trained on synthetic seeded E&P data. Refit on real well "
                  "data before any production use; see README limitations."),
    }
    out = Path(path)
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return out


def load_and_predict(artifact_path: str | Path, feature_row: list[float]) -> float:
    """Load a packaged artifact and predict next-month oil for one row."""
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    x = np.asarray(feature_row, dtype=float)
    xs = (x - np.asarray(artifact["feature_mean"])) / np.asarray(artifact["feature_std"])
    xb = np.append(xs, 1.0)
    return float(max(0.0, xb @ np.asarray(artifact["weights"])))
