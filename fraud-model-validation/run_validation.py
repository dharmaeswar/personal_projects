#!/usr/bin/env python3
"""CLI entry point: run the full fraud-model validation and print/write the report.

Usage:
    python run_validation.py [--output validation_report.txt]
"""

from __future__ import annotations

import argparse

import numpy as np

from fraud_validation.data import (
    FEATURES,
    MERCHANT_CATEGORIES,
    generate_transactions,
    train_test_split,
)
from fraud_validation.fairness import max_flag_rate_gap, slice_metrics
from fraud_validation.metrics import evaluate_model, tune_threshold
from fraud_validation.models import fit_all, predict_all
from fraud_validation.monitoring import drift_report
from fraud_validation.report import build_report, write_report
from fraud_validation.credit_risk import (
    CREDIT_FEATURES,
    build_credit_features,
    build_credit_risk_section,
    decision_cutoff_analysis,
    generate_credit_applications,
    gini_coefficient,
    roll_rate,
    score_band_performance,
    vintage_analysis,
)
from fraud_validation.approval import (
    ModelRecord,
    build_approval_section,
    evaluate_approval,
    evidence_from_results,
    sign_off,
)
from fraud_validation.safeguards import build_safeguards_section, generate_harm_events
from fraud_validation.reconciliation import (
    break_aging,
    build_reconciliation_section,
    capital_flow_summary,
    generate_ledger,
    reconcile,
)
from fraud_validation.rule_backtesting import (
    RULES,
    backtest_rules,
    build_rule_backtesting_section,
    combine_flags,
    compute_kris,
    shadow_test,
    staged_rollout,
    tune_score_threshold,
)
from fraud_validation.transaction_risk import (
    N_EVENT_DAYS,
    RISK_FEATURES,
    add_event_days,
    build_transaction_risk_section,
    delayed_label_evaluation,
    latency_quality_tradeoff,
    pattern_shift_report,
    regression_check,
)


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
    safeguards_section = build_safeguards_section(harm_events)

    # 8. Transaction-risk scoring (new module, Nov 2026).
    dated_test = add_event_days(test)
    latest_day = int(dated_test["event_day"].max())
    delayed = delayed_label_evaluation(
        y_true, scores["champion"],
        dated_test["event_day"].to_numpy(), latest_day=latest_day,
    )
    dated_test = dated_test.assign(
        period=np.where(
            dated_test["event_day"] < N_EVENT_DAYS // 2, "baseline", "recent"
        ),
        merchant_category=dated_test["merchant_category"].map(
            lambda code: MERCHANT_CATEGORIES[int(code)]
        ),
    )
    shifts = pattern_shift_report(dated_test, y_true, scores["champion"], threshold=threshold)
    tradeoff = latency_quality_tradeoff(models, test, y_true, threshold=threshold)
    base_mask = (dated_test["period"] == "baseline").to_numpy()
    recent_mask = ~base_mask
    metric_keys = ("roc_auc", "precision", "recall", "f1")
    base_eval = evaluate_model(
        y_true[base_mask], scores["champion"][base_mask], threshold=threshold
    )
    recent_eval = evaluate_model(
        y_true[recent_mask], scores["champion"][recent_mask], threshold=threshold
    )
    regression = regression_check(
        {k: base_eval[k] for k in metric_keys},
        {k: recent_eval[k] for k in metric_keys},
    )
    risk_section = build_transaction_risk_section(
        delayed, shifts, tradeoff, regression, n_features=len(RISK_FEATURES)
    )

    # 9. Credit-risk analytics (new module, Nov 2026).
    credit_apps = build_credit_features(generate_credit_applications())
    credit_gini = gini_coefficient(
        credit_apps["is_bad"].to_numpy(),
        credit_apps["bureau_score"].to_numpy(dtype=float),
    )
    credit_bands = score_band_performance(credit_apps)
    credit_cutoffs = decision_cutoff_analysis(credit_apps)
    credit_vintages = vintage_analysis(credit_apps)
    credit_rolls = roll_rate(credit_apps)
    credit_section = build_credit_risk_section(
        credit_bands,
        credit_gini,
        credit_cutoffs,
        credit_vintages,
        credit_rolls,
    )

    # 10. Model approval workflow (new module, Nov 2026): gate the champion's
    # validation evidence through the approval process and sign it off.
    record = ModelRecord(
        model_id="FRD-001",
        name="Card Fraud Scoring (champion)",
        owner="Fraud Analytics",
        model_tier=1,
        purpose="Flag card transactions for review",
    )
    evidence = evidence_from_results(results, drift, gap, len(test))
    approval = evaluate_approval(evidence)
    trail_entry = sign_off(
        record, approval, validator="Model Validation", sign_date="2026-11-20"
    )
    approval_section = build_approval_section(record, approval, trail_entry)

    # 11. Financial-flow reconciliation (new module, Nov 2026): reconcile
    # the synthetic ledger against downstream flow records, summarise
    # capital flows by product, and age the unresolved breaks.
    recon_ledger, recon_flows = generate_ledger()
    recon_summary, recon_breaks = reconcile(recon_ledger, recon_flows)
    recon_section = build_reconciliation_section(
        recon_summary,
        capital_flow_summary(recon_ledger, recon_flows),
        break_aging(recon_breaks),
    )

    report = (
        report.rstrip("\n") + "\n" + risk_section + safeguards_section
        + credit_section + approval_section + recon_section
        + "\n" + "=" * 70 + "\n"
    )

    # 12. Card-fraud rule backtesting (new module, Nov 2026): backtest the
    # rule set on the test set, shadow-test a broader challenger set
    # against the champion set, simulate a staged rollout, tune the
    # champion score threshold on false positives vs fraud loss, and
    # track KRIs for the executive view.
    champion_rules = ["velocity_1h_burst", "cross_border_cnp_high_amount"]
    challenger_flags = combine_flags(test, RULES)
    rule_backtest = backtest_rules(test)
    rule_shadow = shadow_test(test, champion_rules, RULES)
    rule_rollout = staged_rollout(test, challenger_flags)
    rule_tuned = tune_score_threshold(
        y_true, scores["champion"], test["amount"].to_numpy()
    )
    rule_kris = compute_kris(test, challenger_flags)
    rule_section = build_rule_backtesting_section(
        rule_backtest, rule_shadow, rule_rollout, rule_tuned, rule_kris
    )
    report = report.rstrip("\n") + "\n" + rule_section + "\n" + "=" * 70 + "\n"

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
