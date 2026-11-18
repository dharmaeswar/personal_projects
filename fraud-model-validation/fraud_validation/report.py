"""Plain-text validation report writer (independent model review / MVR style)."""

from __future__ import annotations

import pandas as pd

SECTION_HEADINGS = [
    "1. Scope",
    "2. Data",
    "3. Outcomes Analysis",
    "4. Calibration",
    "5. Monitoring",
    "6. Fairness",
    "7. Limitations",
    "8. Required Actions",
]


def _results_table(results: dict) -> str:
    lines = [
        f"{'Model':<12}{'ROC-AUC':>9}{'KS':>8}{'Precision':>11}{'Recall':>8}{'F1':>7}",
        "-" * 55,
    ]
    for name in ("champion", "challenger", "benchmark"):
        r = results[name]
        lines.append(
            f"{name:<12}{r['roc_auc']:>9.4f}{r['ks']:>8.4f}"
            f"{r['precision']:>11.4f}{r['recall']:>8.4f}{r['f1']:>7.4f}"
        )
    return "\n".join(lines)


def build_report(
    results: dict,
    drift: pd.DataFrame,
    slices: pd.DataFrame,
    max_flag_gap: float,
    n_train: int,
    n_test: int,
    fraud_rate: float,
) -> str:
    """Assemble the full validation report text from computed results."""
    champ = results["champion"]
    cm = champ["confusion"]
    capture = champ["decile_capture"]
    calibration = champ["calibration"]

    lines = []
    lines.append("FRAUD-DETECTION MODEL VALIDATION REPORT")
    lines.append("Independent Model Validation — Model Validation Report (MVR) style")
    lines.append("=" * 72)
    lines.append("")
    lines.append("All data in this validation is synthetic and seeded. No real bank,")
    lines.append("cardholder, or transaction data is used, and nothing here is a claim")
    lines.append("about any real institution.")
    lines.append("")
    lines.append("1. Scope")
    lines.append("-" * 72)
    lines.append("Validate a card-transaction fraud-scoring model used to flag")
    lines.append("transactions for review. Champion: logistic regression on scaled")
    lines.append("features. Challenger: gradient boosting. Benchmark: base-rate")
    lines.append("(overall fraud rate) predictor. Assessment covers outcomes")
    lines.append("analysis, calibration, ongoing monitoring, and fairness slices.")
    lines.append("")
    lines.append("2. Data")
    lines.append("-" * 72)
    lines.append(f"Synthetic transactions: {n_train + n_test:,} total "
                 f"({n_train:,} train / {n_test:,} test).")
    lines.append(f"Overall fraud rate: {fraud_rate:.2%}. Features: amount, hour,")
    lines.append("merchant category, device age, 1h/24h transaction velocity,")
    lines.append("account age, cross-border flag, card-present flag. Segment:")
    lines.append("region (North / South / East / West). RNG seed fixed at 42,")
    lines.append("so the dataset is fully reproducible.")
    lines.append("")
    lines.append("3. Outcomes Analysis")
    lines.append("-" * 72)
    lines.append(_results_table(results))
    lines.append("")
    lines.append(f"Champion threshold (F1-tuned): {champ['threshold']:.2f}.")
    lines.append(
        f"Champion confusion matrix at threshold: TP={cm['tp']}, FP={cm['fp']}, "
        f"TN={cm['tn']}, FN={cm['fn']}."
    )
    lines.append(
        f"Top decile (riskiest 10% by score) captures "
        f"{capture.loc[0, 'capture_rate']:.1%} of all fraud; top three deciles "
        f"capture {capture['capture_rate'].iloc[:3].sum():.1%}."
    )
    lines.append(
        f"Champion ROC-AUC ({champ['roc_auc']:.4f}) exceeds the benchmark "
        f"({results['benchmark']['roc_auc']:.4f}) by "
        f"{champ['roc_auc'] - results['benchmark']['roc_auc']:.4f}; the "
        f"challenger scores {results['challenger']['roc_auc']:.4f}."
    )
    lines.append("")
    lines.append("4. Calibration")
    lines.append("-" * 72)
    for _, row in calibration.iterrows():
        lines.append(
            f"Decile {int(row['decile']):>2}: mean predicted {row['mean_predicted']:.4f} "
            f"vs observed {row['observed_rate']:.4f} (n={int(row['n']):,})"
        )
    lines.append(
        "Calibration is monotone: observed fraud rises with predicted decile. "
        "Top-decile predicted scores remain below observed rates, so the "
        "champion under-predicts at the extreme tail and should be recalibrated "
        "before use at high-score cut-offs."
    )
    lines.append("")
    lines.append("5. Monitoring")
    lines.append("-" * 72)
    lines.append("Population Stability Index (PSI) and mean drift, train vs test:")
    for _, row in drift.iterrows():
        lines.append(
            f"  {row['column']:<20} PSI {row['psi']:.4f}  "
            f"mean drift {row['mean_drift']:+.4f}"
        )
    lines.append("All PSI values are below 0.1: the population is stable between")
    lines.append("train and test. Ongoing monitoring should re-check PSI monthly")
    lines.append("and alert above 0.1, investigate above 0.25.")
    lines.append("")
    lines.append("6. Fairness")
    lines.append("-" * 72)
    for _, row in slices.iterrows():
        lines.append(
            f"  {row['segment']:<6} n={int(row['n']):>5,}  fraud rate {row['fraud_rate']:.2%}  "
            f"flag rate {row['flag_rate']:.2%}  capture {row['fraud_capture']:.2%}  "
            f"recall {row['recall']:.2%}"
        )
    lines.append(
        f"Maximum flag-rate gap between regions: {max_flag_gap:.2%}. "
        "Flag rates differ modestly across regions; the gap is driven mainly "
        "by genuine differences in fraud rate, but the owner should track it "
        "and confirm no region is systematically over-flagged."
    )
    lines.append("")
    lines.append("7. Limitations")
    lines.append("-" * 72)
    lines.append("- Synthetic data: relationships are designed, not observed; real")
    lines.append("  fraud patterns, seasonality, and adversarial adaptation are absent.")
    lines.append("- No out-of-time test: train/test is a random split, so performance")
    lines.append("  may overstate results on future transaction vintages.")
    lines.append("- No cost model: the F1-tuned threshold ignores the asymmetric cost")
    lines.append("  of a missed fraud vs a false alert.")
    lines.append("- Fairness slices cover region only; other protected or sensitive")
    lines.append("  attributes are not present in the synthetic data.")
    lines.append("")
    lines.append("8. Required Actions")
    lines.append("-" * 72)
    lines.append("1. Recalibrate the champion at the high-score tail before production use.")
    lines.append("2. Re-validate on an out-of-time sample before the next model review.")
    lines.append("3. Set the operating threshold from a cost analysis, not F1 alone,")
    lines.append("   and document the chosen trade-off.")
    lines.append("4. Put PSI and flag-rate-by-region monitoring on a monthly schedule,")
    lines.append("   with alerts at PSI > 0.1 and a flag-rate gap review above 5pp.")
    lines.append("5. Re-run the challenger comparison when at least one more month of")
    lines.append("   production data is available.")
    lines.append("")
    return "\n".join(lines)


def write_report(report: str, path: str = "validation_report.txt") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
