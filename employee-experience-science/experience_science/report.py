"""Plain-text experience report: headline numbers, confirmed defects
with effect sizes and confidence intervals, and the feedback-theme
benchmark. Written for a mixed audience: numbers first, then what
each finding means in one sentence.
"""

from .stats import mean, pearson


def build_report(rows, defects, corrected_alpha, fb_bench):
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
    return "\n".join(lines) + "\n"
