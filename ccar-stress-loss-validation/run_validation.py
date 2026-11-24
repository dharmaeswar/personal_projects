#!/usr/bin/env python3
"""CLI entry point: run the full CCAR stress-loss validation and print/write the report.

Usage:
    python run_validation.py [--output validation_report.txt]
"""

from __future__ import annotations

import argparse

import numpy as np

from ccar_validation.backtest import backtest_all, calibration_by_decile
from ccar_validation.counterparty import build_counterparty_section, generate_counterparty_book
from ccar_validation.data import MACRO_COLUMNS, generate_portfolio, train_test_split
from ccar_validation.deployment import (
    ModelRegistry,
    build_deployment_section,
    promotion_gate,
    run_pipeline,
)
from ccar_validation.macro import build_macro_section
from ccar_validation.models import fit_all
from ccar_validation.monitoring import drift_report
from ccar_validation.optimize import benchmark_scoring, build_optimization_section
from ccar_validation.prepayment import build_prepayment_section, generate_prepayment_pool
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

    # 7. Agency prepayment model validation (new module, Nov 2026).
    prepay_pool = generate_prepayment_pool()
    report = report.rstrip("\n") + "\n" + build_prepayment_section(prepay_pool) + "\n" + "=" * 70 + "\n"

    # 8. Counterparty credit-risk exposure validation (new module, Nov 2026).
    counterparties, trades = generate_counterparty_book()
    report = report.rstrip("\n") + "\n" + build_counterparty_section(counterparties, trades) + "\n" + "=" * 70 + "\n"

    # 9. Macro-forecasting model validation (new module, Nov 2026).
    report = report.rstrip("\n") + "\n" + build_macro_section(train, test, models["champion"]) + "\n" + "=" * 70 + "\n"

    # 10. Deployment pipeline (new module, Nov 2026): run the champion
    # through the staged execution pipeline, register champion/challenger,
    # and evaluate the promotion gate.
    deployment_run = run_pipeline(models["champion"], test, actual, "stress-loss-forecaster", "1.0")
    registry = ModelRegistry()
    registry.register("stress-loss-forecaster", "1.0", backtest["champion"], status="champion")
    registry.register("stress-loss-forecaster", "2.0", backtest["challenger"])
    gate = promotion_gate(backtest["champion"], backtest["challenger"])
    report = report.rstrip("\n") + "\n" + build_deployment_section(deployment_run, registry, gate) + "\n" + "=" * 70 + "\n"

    # 11. Scoring-execution optimization (new module, Nov 2026): benchmark
    # row-wise vs batch vs chunked scoring of the champion and pick the
    # fastest chunk size, verifying chunked scores match batch scores.
    benchmark = benchmark_scoring(models["champion"], test)
    report = report.rstrip("\n") + "\n" + build_optimization_section(benchmark) + "\n" + "=" * 70 + "\n"
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
