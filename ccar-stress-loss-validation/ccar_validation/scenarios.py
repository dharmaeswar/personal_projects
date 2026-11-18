"""CCAR-style macro scenario paths and stressed loss forecasts.

Scenarios are illustrative CCAR-style paths (baseline vs severely adverse)
over a 9-quarter horizon, expressed as macro feature values per quarter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_QUARTERS = 9

# Illustrative CCAR-style scenario paths (synthetic, not real Fed scenarios).
SCENARIOS = {
    "baseline": {
        "gdp_growth": [2.0, 2.1, 2.0, 2.2, 2.1, 2.0, 2.0, 2.1, 2.0],
        "unemployment_rate": [4.5, 4.6, 4.7, 4.7, 4.8, 4.8, 4.9, 4.9, 5.0],
        "hpi_growth": [3.0, 3.1, 3.0, 2.9, 3.0, 3.0, 2.9, 3.0, 3.0],
        "credit_spread": [150.0, 152.0, 155.0, 155.0, 158.0, 160.0, 160.0, 162.0, 165.0],
    },
    "severely_adverse": {
        "gdp_growth": [-2.5, -4.0, -3.0, -1.0, 0.5, 1.0, 1.5, 2.0, 2.0],
        "unemployment_rate": [5.5, 7.0, 9.0, 10.0, 10.5, 10.0, 9.5, 9.0, 8.5],
        "hpi_growth": [-5.0, -12.0, -10.0, -8.0, -5.0, -2.0, 0.0, 1.0, 2.0],
        "credit_spread": [250.0, 420.0, 500.0, 480.0, 420.0, 350.0, 300.0, 250.0, 220.0],
    },
}


def scenario_frame(scenario: str) -> pd.DataFrame:
    """Return the macro path for a scenario as a DataFrame (one row per quarter)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario!r}. Choose from {sorted(SCENARIOS)}")
    data = SCENARIOS[scenario]
    frame = pd.DataFrame(data)
    frame.insert(0, "quarter", np.arange(1, N_QUARTERS + 1))
    return frame


def scenario_forecast(model, scenario: str, reference_df: pd.DataFrame) -> pd.DataFrame:
    """Forecast portfolio loss rates under a scenario.

    Applies the scenario's macro path to every loan in ``reference_df``
    (loan-level features such as LTV and FICO are held fixed) and averages
    the model's forecast per quarter.
    """
    path = scenario_frame(scenario)
    rows = []
    for _, quarter in path.iterrows():
        scenario_df = reference_df.copy()
        for col in ("gdp_growth", "unemployment_rate", "hpi_growth", "credit_spread"):
            scenario_df[col] = float(quarter[col])
        preds = model.predict(scenario_df)
        rows.append(
            {
                "quarter": int(quarter["quarter"]),
                "scenario": scenario,
                "mean_forecast_loss_rate": float(np.mean(preds)),
            }
        )
    return pd.DataFrame(rows)


def compare_scenarios(model, reference_df: pd.DataFrame) -> pd.DataFrame:
    """Forecast under baseline and severely adverse; return combined table."""
    base = scenario_forecast(model, "baseline", reference_df)
    adverse = scenario_forecast(model, "severely_adverse", reference_df)
    merged = base.merge(
        adverse[["quarter", "mean_forecast_loss_rate"]],
        on="quarter",
        suffixes=("_baseline", "_severely_adverse"),
    )
    merged["stress_uplift"] = (
        merged["mean_forecast_loss_rate_severely_adverse"]
        - merged["mean_forecast_loss_rate_baseline"]
    )
    return merged
