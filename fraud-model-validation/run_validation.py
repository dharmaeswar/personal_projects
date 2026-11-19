#!/usr/bin/env python3
"""CLI entry point: run the full fraud-model validation and print/write the report.

Usage:
    python run_validation.py [--output validation_report.txt]
"""

from __future__ import annotations

import argparse

from fraud_validation.data import FEATURES, generate_transactions, train_test_split
from fraud_validation.fairness import max_flag_rate_gap, slice_metrics
from fraud_validation.metrics import evaluate_model, tune_threshold
from fraud_validation.models import fit_all, predict_all
from fraud_validation.monitoring import drift_report
from fraud_validation.report import build_report, write_report
from fraud_validation.safeguards import build_safeguards_section, generate_harm_events


def run_validation(output: str = "validation_report.txt") -> str:
    # 1. Data (seeded synthetic transactions).
    data = generate_transactions()
    train, test = train_test_split(data)

    # 2. Fit champion, challenger, benchmark; score the test set.
    models = fit_all(train)
    scores = predict_all(models, test)
    y_true = test["is_fraud"].to_numpy()

    # 3. Outcomes analysis (F1-tuned threshold from the champion).
    threshold = tune_threshold(y_true, scores["champion"])
    results = {
        name: evaluate_model(y_true, score, threshold=threshold)
        for name, score in scores.items()
    }

    # 4. Monitoring: drift between train and test (same generator, fresh split).
    drift = drift_report(train, test, FEATURES)

    # 5. Fairness: slices by region at the operating threshold.
    slices = slice_metrics(y_true, scores["champion"], test["region"], threshold)
    gap = max_flag_rate_gap(slices)

    # 6. Report.
    report = build_report(
        results, drift, slices, gap,
        len(train), len(test), float(data["is_fraud"].mean()),
    )

    # 7. Safeguards analytics (new module, Nov 2026).
    harm_events = generate_harm_events()
    report = report.rstrip("\n") + "\n" + build_safeguards_section(harm_events) + "\n" + "=" * 70 + "\n"
    write_report(report, output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fraud-model validation.")
    parser.add_argument("--output", default="validation_report.txt",
                        help="Path for the written report.")
    args = parser.parse_args()
    report = run_validation(args.output)
    print(report)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
