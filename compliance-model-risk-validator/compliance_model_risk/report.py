"""Write the validation report: outcomes, threshold trade-off,
monitoring, fairness, and governance — the pack a validator hands to
the model owner and the Model Risk Office.
"""

from .alert_model import predict_scores
from .fairness import (
    disparate_impact_ratio,
    equal_opportunity_gap,
    flag_rates_by_group,
)
from .monitoring import mean_drift_pct, psi
from .outcomes import calibration_by_decile, decile_capture, outcomes_summary
from .threshold import review_burden, threshold_table


def build_report(train, test, later, champion, challenger, benchmark, inventory, threshold=0.5):
    """Assemble the full validation report as a dict."""
    y_test = test["sar_worthy"].to_numpy()
    scores = {
        "champion": predict_scores(champion, test),
        "challenger": predict_scores(challenger, test),
        "benchmark": predict_scores(benchmark, test),
    }
    outcomes = {name: outcomes_summary(y_test, s, threshold) for name, s in scores.items()}
    later_scores = predict_scores(champion, later)
    flag_rates = flag_rates_by_group(test, scores["champion"], threshold)
    verdict = "PASS" if outcomes["champion"]["roc_auc"] >= 0.70 and outcomes["champion"]["ks"] >= 0.30 else "CONDITIONAL"
    findings = []
    if disparate_impact_ratio(flag_rates) < 0.8:
        findings.append("Disparate impact ratio below 0.80 — review flag-rate differences across groups.")
    if psi(scores["champion"], later_scores) >= 0.25:
        findings.append("PSI at or above 0.25 — material score drift since validation.")
    if outcomes["champion"]["roc_auc"] < outcomes["challenger"]["roc_auc"] - 0.03:
        findings.append("Challenger beats champion ROC-AUC by more than 0.03 — consider challenger promotion.")
    return {
        "verdict": verdict,
        "threshold": threshold,
        "outcomes": outcomes,
        "decile_capture": decile_capture(y_test, scores["champion"]),
        "calibration": calibration_by_decile(y_test, scores["champion"]),
        "threshold_table": threshold_table(y_test, scores["champion"]),
        "review_burden_at_threshold": review_burden(
            int((scores["champion"] >= threshold).sum())
        ),
        "psi": psi(scores["champion"], later_scores),
        "score_mean_drift_pct": mean_drift_pct(scores["champion"], later_scores),
        "flag_rates": flag_rates,
        "disparate_impact_ratio": disparate_impact_ratio(flag_rates),
        "equal_opportunity_gap": equal_opportunity_gap(flag_rates),
        "governance_gaps": inventory.gaps_report(),
        "findings": findings,
    }


def render_text(report):
    """Render the report dict as plain text."""
    lines = []
    lines.append("COMPLIANCE MODEL RISK VALIDATION REPORT")
    lines.append(f"Verdict: {report['verdict']}  (threshold {report['threshold']})")
    lines.append("")
    lines.append("Outcomes analysis (test set):")
    for name, o in report["outcomes"].items():
        lines.append(
            f"  {name:11s} ROC-AUC {o['roc_auc']:.3f}  KS {o['ks']:.3f}  "
            f"precision {o['precision']:.3f}  recall {o['recall']:.3f}  F1 {o['f1']:.3f}"
        )
    lines.append("")
    lines.append("Decile capture (champion, decile 10 = highest scored):")
    for d in report["decile_capture"]:
        lines.append(
            f"  decile {d['decile']:2d}: {d['positives']:4d} positives, "
            f"{d['capture_pct']:5.1f}% of all SAR-worthy cases"
        )
    lines.append("")
    lines.append("Threshold trade-off:")
    for row in report["threshold_table"]:
        lines.append(
            f"  t={row['threshold']:.1f}: {row['alerts']:5d} alerts "
            f"({row['alert_rate_pct']:.1f}%), precision {row['precision']:.3f}, "
            f"recall {row['recall']:.3f}, F1 {row['f1']:.3f}"
        )
    b = report["review_burden_at_threshold"]
    lines.append(
        f"  Review burden at t={report['threshold']}: {b['alerts']} alerts, "
        f"{b['review_hours']} hours, {b['team_days']} team-days"
    )
    lines.append("")
    lines.append(
        f"Monitoring: PSI {report['psi']:.3f}, score mean drift "
        f"{report['score_mean_drift_pct']:.1f}%"
    )
    lines.append(
        f"Fairness: disparate impact ratio {report['disparate_impact_ratio']:.3f}, "
        f"equal-opportunity gap {report['equal_opportunity_gap']:.3f}"
    )
    for group, v in report["flag_rates"].items():
        lines.append(
            f"  {group}: flag rate {v['flag_rate']:.3f}, capture {v['capture_rate']:.3f}, "
            f"base rate {v['base_rate']:.3f}"
        )
    lines.append("")
    lines.append("Governance gaps:")
    for row in report["governance_gaps"]:
        lines.append(f"  {row['model_id']} ({row['tier']}, {row['stage']}): {', '.join(row['gaps'])}")
    lines.append("")
    lines.append("Findings:")
    for f in report["findings"] or ["None — no material findings."]:
        lines.append(f"  - {f}")
    return "\n".join(lines) + "\n"
