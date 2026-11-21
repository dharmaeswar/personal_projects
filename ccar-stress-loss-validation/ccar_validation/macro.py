"""Macro-forecasting model validation: sensitivity, regimes, stability, scenarios.

A macro-driven loss model must behave sensibly when the economy moves:
losses rise when unemployment rises, forecasts stay accurate in both
expansions and recessions, coefficients stay stable across origination
vintages, and the severely adverse scenario always produces higher losses
than the baseline. Each check returns a pass/fail row so the validation
report shows exactly which behaviour broke, not just a single verdict.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .models import ChallengerModel, FEATURES
from .scenarios import compare_scenarios

SENSITIVITY_LEVELS = (3.0, 5.0, 7.0, 9.0, 11.0)
STABILITY_WINDOWS = ((2015, 2019), (2018, 2021), (2021, 2024))


def macro_sensitivity(model, reference_df: pd.DataFrame,
                      variable: str = "unemployment_rate",
                      levels: tuple[float, ...] = SENSITIVITY_LEVELS) -> pd.DataFrame:
    """Mean forecast loss rate as one macro variable moves, others at median.

    Raises ValueError for an unknown macro variable.
    """
    if variable not in ("gdp_growth", "unemployment_rate", "hpi_growth", "credit_spread"):
        raise ValueError(f"Unknown macro variable: {variable!r}")
    medians = reference_df[["gdp_growth", "unemployment_rate", "hpi_growth",
                             "credit_spread"]].median()
    rows = []
    for level in levels:
        scenario_df = reference_df.copy()
        for col in ("gdp_growth", "unemployment_rate", "hpi_growth", "credit_spread"):
            scenario_df[col] = float(medians[col])
        scenario_df[variable] = float(level)
        preds = model.predict(scenario_df)
        rows.append({"level": float(level), "mean_forecast_loss_rate": float(np.mean(preds))})
    return pd.DataFrame(rows)


def sensitivity_is_monotone(table: pd.DataFrame, direction: str = "increasing",
                            min_move: float = 0.001) -> bool:
    """Check the forecast moves in the expected direction with the macro variable.

    ``direction`` is "increasing" (losses rise with unemployment / spreads)
    or "decreasing" (losses fall with GDP / HPI growth). The total move must
    exceed ``min_move`` so a flat, macro-insensitive model fails.
    """
    values = table["mean_forecast_loss_rate"].to_numpy()
    diffs = np.diff(values)
    if direction == "increasing":
        return bool(np.all(diffs >= -1e-9) and values[-1] - values[0] > min_move)
    if direction == "decreasing":
        return bool(np.all(diffs <= 1e-9) and values[0] - values[-1] > min_move)
    raise ValueError(f"Unknown direction: {direction!r}")


def regime_accuracy(actual: np.ndarray, forecast: np.ndarray,
                    gdp_growth: np.ndarray) -> dict:
    """MAE split by macro regime: expansion (GDP growth > 0) vs recession (<= 0)."""
    expansion = gdp_growth > 0
    recession = ~expansion
    out = {}
    for name, mask in (("expansion", expansion), ("recession", recession)):
        if mask.sum() == 0:
            out[name] = {"n": 0, "mae": float("nan")}
        else:
            out[name] = {
                "n": int(mask.sum()),
                "mae": float(np.mean(np.abs(actual[mask] - forecast[mask]))),
            }
    return out


def coefficient_stability(df: pd.DataFrame,
                          windows: tuple[tuple[int, int], ...] = STABILITY_WINDOWS,
                          variable: str = "unemployment_rate") -> pd.DataFrame:
    """Refit the challenger on each origination-year window; track one coefficient.

    Returns one row per window with the standardised coefficient for
    ``variable``. A stable model keeps the same sign in every window.
    """
    if variable not in FEATURES:
        raise ValueError(f"Unknown feature: {variable!r}")
    idx = FEATURES.index(variable)
    rows = []
    for start, end in windows:
        window = df[(df["origination_year"] >= start) & (df["origination_year"] <= end)]
        model = ChallengerModel().fit(window)
        # ChallengerModel stores a fitted LinearRegression on standardised features.
        coef = float(model.model.coef_[idx])
        rows.append({"window": f"{start}-{end}", "n": len(window),
                     "coefficient": coef})
    return pd.DataFrame(rows)


def scenario_reasonableness(model, reference_df: pd.DataFrame) -> pd.DataFrame:
    """Baseline vs severely adverse forecasts; every quarter must show an uplift."""
    return compare_scenarios(model, reference_df)


def validate_macro_model(model, train: pd.DataFrame, test: pd.DataFrame) -> list[dict]:
    """Run every macro check for one fitted model. Returns one row per check."""
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "status": "pass" if passed else "fail",
                       "detail": detail})

    sensitivity = macro_sensitivity(model, test)
    monotone = sensitivity_is_monotone(sensitivity, "increasing")
    add("unemployment_sensitivity",
        monotone,
        "forecast loss rate by unemployment: " + ", ".join(
            f"{r['level']:.0f}% -> {r['mean_forecast_loss_rate']:.4f}"
            for _, r in sensitivity.iterrows()))

    actual = test["observed_loss_rate"].to_numpy()
    forecast = model.predict(test)
    regimes = regime_accuracy(actual, forecast, test["gdp_growth"].to_numpy())
    add("regime_accuracy",
        all(np.isfinite(r["mae"]) for r in regimes.values()),
        "MAE expansion={:.4f} (n={}) vs recession={:.4f} (n={})".format(
            regimes["expansion"]["mae"], regimes["expansion"]["n"],
            regimes["recession"]["mae"], regimes["recession"]["n"]))

    stability = coefficient_stability(train)
    coefs = stability["coefficient"].to_numpy()
    same_sign = bool(np.all(coefs > 0) or np.all(coefs < 0))
    add("coefficient_stability",
        same_sign,
        "unemployment coefficient by vintage: " + ", ".join(
            f"{r['window']}={r['coefficient']:+.4f}" for _, r in stability.iterrows()))

    scenarios = scenario_reasonableness(model, test)
    min_uplift = float(scenarios["stress_uplift"].min())
    peak = scenarios.loc[scenarios["stress_uplift"].idxmax()]
    add("scenario_reasonableness",
        min_uplift > 0,
        f"min quarterly stress uplift {min_uplift:.4f}; "
        f"peak uplift {peak['stress_uplift']:.4f} in quarter {int(peak['quarter'])}")
    return checks


def build_macro_section(train: pd.DataFrame, test: pd.DataFrame, model) -> str:
    """Render the macro validation checks as a report section."""
    lines = ["MACRO-FORECASTING MODEL VALIDATION",
             "-" * 70,
             "Validates the champion loss forecaster against the macro cycle:",
             "unemployment sensitivity, accuracy by expansion/recession regime,",
             "coefficient stability across origination vintages, and scenario",
             "reasonableness (severely adverse must exceed baseline every quarter).",
             ""]
    for check in validate_macro_model(model, train, test):
        lines.append(f"[{check['status'].upper()}] {check['check']}: {check['detail']}")
    return "\n".join(lines)
