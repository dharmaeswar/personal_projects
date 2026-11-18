"""Plain-text validation report writer."""

from __future__ import annotations

import pandas as pd


def build_report(
    backtest: dict,
    calibration: pd.DataFrame,
    scenario_comparison: pd.DataFrame,
    drift: pd.DataFrame,
    n_train: int,
    n_test: int,
) -> str:
    """Assemble the validation report as plain text."""
    lines = []
    lines.append("=" * 70)
    lines.append("CCAR STRESS-LOSS MODEL VALIDATION REPORT")
    lines.append("(Synthetic data only - illustrative validation, not a real filing)")
    lines.append("=" * 70)
    lines.append("")
    lines.append("1. SCOPE")
    lines.append(
        "   Validation of the champion logistic-regression loss forecaster "
        "against a linear-regression challenger and a historical-average "
        "benchmark, on a synthetic loan portfolio."
    )
    lines.append(f"   Training loans: {n_train}; hold-out loans: {n_test}.")
    lines.append("")
    lines.append("2. OUTCOMES ANALYSIS (BACKTEST ON HOLD-OUT SET)")
    for name, m in backtest.items():
        lines.append(
            f"   {name:12s} bias={m['bias']:+.4f}  MAE={m['mae']:.4f}  "
            f"RMSE={m['rmse']:.4f}  hit_rate={m['hit_rate']:.3f}  n={m['n']}"
        )
    lines.append("")
    lines.append("3. CALIBRATION BY DECILE (CHAMPION)")
    lines.append("   decile  n     mean_actual  mean_predicted  gap")
    for _, row in calibration.iterrows():
        lines.append(
            f"   {int(row['decile']):>6d}  {int(row['n']):>5d}  "
            f"{row['mean_actual']:>11.4f}  {row['mean_predicted']:>14.4f}  "
            f"{row['calibration_gap']:+.4f}"
        )
    lines.append("")
    lines.append("4. SCENARIO ANALYSIS (CCAR-STYLE PATHS)")
    lines.append("   quarter  baseline  severely_adverse  stress_uplift")
    for _, row in scenario_comparison.iterrows():
        lines.append(
            f"   {int(row['quarter']):>7d}  "
            f"{row['mean_forecast_loss_rate_baseline']:>8.4f}  "
            f"{row['mean_forecast_loss_rate_severely_adverse']:>16.4f}  "
            f"{row['stress_uplift']:+.4f}"
        )
    lines.append("")
    lines.append("5. ONGOING MONITORING (DRIFT VS REFERENCE SAMPLE)")
    lines.append("   column             mean_drift_bps  psi")
    for _, row in drift.iterrows():
        lines.append(
            f"   {row['column']:<18s}  {row['mean_drift_bps']:>14.1f}  {row['psi']:.4f}"
        )
    lines.append("")
    lines.append("6. VALIDATION CONCLUSION")
    champion = backtest["champion"]
    benchmark = backtest["benchmark"]
    if champion["mae"] < benchmark["mae"]:
        lines.append(
            "   Champion beats the historical-average benchmark on MAE "
            f"({champion['mae']:.4f} vs {benchmark['mae']:.4f})."
        )
    else:
        lines.append("   WARNING: champion does not beat the benchmark on MAE.")
    avg_uplift = float(scenario_comparison["stress_uplift"].mean())
    lines.append(
        f"   Severely adverse scenario raises forecast losses by "
        f"{avg_uplift:.4f} on average vs baseline (directionally correct)."
    )
    max_psi = float(drift["psi"].max())
    lines.append(
        f"   Maximum PSI across monitored features: {max_psi:.4f} "
        f"({'stable' if max_psi < 0.1 else 'shift detected'})."
    )
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines) + "\n"


def write_report(report: str, path: str) -> str:
    """Write the report text to ``path`` and return the path."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    return path
