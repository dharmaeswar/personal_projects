"""End-to-end run: generate -> clean -> features -> decline fit -> backtest
-> validate -> package the deployment artifact. Prints a short report."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ep_data.cleaning import clean_production, monthly_summary, validate_dictionary
from ep_data.data import COLUMN_DESCRIPTIONS, generate_dataset
from ep_data.decline import estimate_eur, fit_decline
from ep_data.deployment import MODEL_VERSION, load_and_predict, package_model
from ep_data.features import add_features
from ep_data.forecast import backtest


def main() -> None:
    raw = generate_dataset(n_wells=40, n_months=36, seed=42, with_issues=True)
    print(f"raw rows: {len(raw)}")
    clean, log = clean_production(raw)
    print(f"cleaning log: {log}")
    issues = validate_dictionary(clean)
    print(f"dictionary issues: {issues or 'none'}")

    feat = add_features(clean)
    summary = monthly_summary(clean)
    print(f"wells: {len(summary)}, total oil: {summary['total_oil_bbl'].sum():,.0f} bbl")

    # Decline-curve fit + EUR for the first well, as a worked example.
    first = feat[feat["api_number"] == feat["api_number"].iloc[0]].sort_values("month_index")
    fit = fit_decline(first["month_index"].to_numpy(),
                      (first["oil_bbl"] / 30.0).to_numpy())
    eur = estimate_eur(fit, len(first))
    print(f"example well fit: qi={fit['qi']:.0f} bbl/d, di={fit['di']:.3f}, "
          f"b={fit['b']:.2f}, R2(log)={fit['r2_log']:.3f}")
    print(f"example well EUR: {eur['eur_bbl']:,.0f} bbl over "
          f"{eur['months_to_limit']} months")

    bt = backtest(feat)
    print(f"backtest (train 24m / test 12m): RMSE={bt['rmse_bbl']:.1f} bbl, "
          f"MAPE={bt['mape']:.1%}, baseline persistence RMSE="
          f"{bt['baseline_persistence_rmse_bbl']:.1f} bbl, "
          f"beats baseline: {bt['beats_baseline']}")

    from ep_data.deployment import validate
    report = validate(feat, log)
    print(f"validation checks: {report['checks']}")
    print(f"all checks pass: {report['all_checks_pass']}")

    artifact = package_model(bt["model"], "model_artifact.json")
    row = feat[feat["month_index"] == 30].iloc[0]
    from ep_data.features import FEATURE_COLUMNS
    pred = load_and_predict(artifact, [float(row[c]) for c in FEATURE_COLUMNS])
    print(f"deployment artifact v{MODEL_VERSION} written to {artifact}; "
          f"loaded-artifact prediction for one well-month: {pred:.1f} bbl "
          f"(actual next month: {row['oil_bbl']:.1f} bbl)")


if __name__ == "__main__":
    main()
