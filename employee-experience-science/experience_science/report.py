"""Plain-text experience report: headline numbers, confirmed defects
with effect sizes and confidence intervals, and the feedback-theme
benchmark. Written for a mixed audience: numbers first, then what
each finding means in one sentence.
"""

from .stats import mean, pearson


def planning_section(plan):
    """Workforce-planning section: attrition-risk model + forecasts."""
    m = plan["attrition_model"]
    lines = []
    lines.append("")
    lines.append("WORKFORCE PLANNING FORECASTS")
    lines.append(
        f"Attrition-risk model (logistic regression, held-out n={m['n_test']}): "
        f"AUC {m['auc']:.3f}, Brier {m['brier']:.4f} vs base-rate "
        f"{m['base_brier']:.4f} (base attrition rate {m['base_rate']:.1%})."
    )
    lines.append("Risk drivers (standardised coefficients, held-out fit):")
    for name, coef in m["coefficients"].items():
        lines.append(f"- {name}: {coef:+.3f}")
    lines.append("Calibration (predicted vs observed attrition, quintiles):")
    for b in m["calibration"]:
        lines.append(
            f"- predicted {b['mean_predicted']:.3f} vs observed "
            f"{b['observed_rate']:.3f} (n={b['n']})"
        )
    lines.append(
        "Calibration limit: the top quintile is under-predicted "
        "(predicted ~0.21 vs observed ~0.38) — attrition jumps at low "
        "experience scores, a threshold effect a linear logit only "
        "partly captures. Treat the top-quintile risk as a floor, not a "
        "point estimate."
    )
    bt = plan["backtest"]
    lines.append(
        f"Headcount forecast backtest (fit months 1-9, scored months 10-12): "
        f"MAPE {bt['mape']:.1%}, 95% interval coverage {bt['coverage']:.0%} "
        f"over {plan['months']}-month history "
        f"({plan['total_attritions_12m']} simulated attritions)."
    )
    for d in bt["detail"]:
        mark = "inside" if d["in_interval"] else "OUTSIDE"
        lines.append(
            f"- Month {d['month']}: forecast {d['forecast']:.1f} "
            f"(95% CI [{d['lo']:.1f}, {d['hi']:.1f}]), actual {d['actual']} — {mark}."
        )
    lines.append("Next-quarter attrition forecast (trend model, 95% intervals):")
    for f in plan["forecast_next_3m"]:
        lines.append(
            f"- Month {f['month']}: {f['forecast']:.1f} attritions "
            f"(95% CI [{f['lo']:.1f}, {f['hi']:.1f}])"
        )
    return lines


def build_report(rows, defects, corrected_alpha, fb_bench, plan=None):
    n = len(rows)
    exp = [r["experience_score"] for r in rows]
    wb = [r["wellbeing_score"] for r in rows]
    lines = []
    lines.append("EMPLOYEE EXPERIENCE SCIENCE REPORT")
    lines.append(f"Employees analysed: {n}")
    lines.append(f"Mean experience score (1-5): {mean(exp):.2f}")
    lines.append(f"Mean wellbeing score (1-5): {mean(wb):.2f}")
    lines.append(f"Attrition rate: {sum(r['attrition'] for r in rows) / n:.1%}")
    lines.append(
        "Overtime vs wellbeing correlation (Pearson r): "
        f"{pearson([r['overtime_hours_week'] for r in rows], wb):.3f}"
    )
    lines.append("")
    lines.append(f"CONFIRMED EXPERIENCE DEFECTS (Bonferroni alpha = {corrected_alpha:.4f})")
    confirmed = [d for d in defects if d["confirmed"]]
    lines.append(f"Confirmed defects: {len(confirmed)} of {len(defects)} segments tested")
    for d in defects:
        mark = "CONFIRMED" if d["confirmed"] else "not confirmed"
        lines.append(
            f"- {d['segment']}: mean {d['mean_in']} vs {d['mean_out']} "
            f"(diff {d['mean_diff']:+.2f}, 95% CI [{d['ci_lo']:+.2f}, {d['ci_hi']:+.2f}], "
            f"Cohen's d {d['cohens_d']:+.2f}, p={d['p']:.2g}) — {mark}. "
            f"Attrition {d['attrition_in']:.1%} vs {d['attrition_out']:.1%} "
            f"(chi2 p={d['p_attrition']:.2g})."
        )
    lines.append("")
    lines.append("FEEDBACK-THEME BENCHMARK (rule-based classifier vs true themes)")
    lines.append(f"Accuracy: {fb_bench['accuracy']:.3f}  Macro F1: {fb_bench['macro_f1']:.3f}")
    for theme, m in fb_bench["per_theme"].items():
        lines.append(
            f"- {theme}: precision {m['precision']:.3f}, recall {m['recall']:.3f}, "
            f"F1 {m['f1']:.3f} (n={m['support']})"
        )
    lines.append("")
    lines.append("WHAT THIS MEANS")
    for d in confirmed:
        lines.append(
            f"- {d['segment']}: employees in this group score "
            f"{abs(d['mean_diff']):.2f} points lower on experience and leave at "
            f"{d['attrition_in']:.0%} vs {d['attrition_out']:.0%}; fix this first."
        )
    lines.append(
        "- The feedback classifier is a transparent baseline: a GenAI summariser "
        "must beat its macro F1 before it can be trusted on employee comments."
    )
    if plan is not None:
        lines.extend(planning_section(plan))
    return "\n".join(lines) + "\n"
