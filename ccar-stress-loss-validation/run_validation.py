#!/usr/bin/env python3
"""CLI entry point: run the full CCAR stress-loss validation and print/write the report.

Usage:
    python run_validation.py [--output validation_report.txt]
"""

from __future__ import annotations

import argparse

import numpy as np

from ccar_validation.backtest import backtest_all, calibration_by_decile
from ccar_validation.data import MACRO_COLUMNS, generate_portfolio, train_test_split
from ccar_validation.models import fit_all
from ccar_validation.monitoring import drift_report
from ccar_validation.report import build_report, write_report
from ccar_validation.scenarios import compare_scenarios


def run_validation(output: str = "validation_report.txt") -> str:
    # 1. Data (seeded synthetic portfolio).
    portfolio = generate_portfolio()
    train, test = train_test_split(portfolio)

    # 2. Fit champion, challenger, benchmark.
    models = fit_all(train)
    forecasts = {name: model.predict(test) for name, model in models.items()}
    actual = test["observed_loss_rate"].to_numpy()

    # 3. Outcomes analysis.
    backtest = backtest_all(actual, forecasts)
    calibration = calibration_by_decile(actual, forecasts["champion"])

    # 4. Scenario analysis (champion under baseline vs severely adverse).
    scenario_comparison = compare_scenarios(models["champion"], test)

    # 5. Monitoring: drift of a synthetic "current" sample vs the training reference.
    # Current sample: same generator, different seed, to simulate a later vintage.
    current = generate_portfolio(seed=123)
    drift = drift_report(train, current, MACRO_COLUMNS + ["ltv", "fico_score"])

    # 6. Report.
    report = build_report(backtest, calibration, scenario_comparison, drift, len(train), len(test))
    write_report(report, output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CCAR stress-loss validation.")
    parser.add_argument("--output", default="validation_report.txt",
                        help="Path for the written report.")
    args = parser.parse_args()
    report = run_validation(args.output)
    print(report)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
