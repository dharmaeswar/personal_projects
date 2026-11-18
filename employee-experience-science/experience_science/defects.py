"""Experience-defect detection.

Compares pre-registered employee segments on experience score and
attrition rate with Welch's t-test / chi-square, bootstrap confidence
intervals and Cohen's d, then applies a Bonferroni correction across
all comparisons so only defects that survive the correction are
reported as confirmed.
"""

from .stats import welch_t, chi_square_test, bootstrap_ci_mean_diff, bonferroni, mean

SEGMENTS = [
    ("Night shift vs Day shift", lambda r: r["shift"] == "Night", lambda r: r["shift"] == "Day"),
    ("Overtime >10h vs <=10h", lambda r: r["overtime_hours_week"] > 10, lambda r: r["overtime_hours_week"] <= 10),
    ("New manager (<1y) vs experienced", lambda r: r["manager_tenure_years"] < 1.0, lambda r: r["manager_tenure_years"] >= 1.0),
    ("4+ schedule changes vs fewer", lambda r: r["schedule_changes_month"] >= 4, lambda r: r["schedule_changes_month"] < 4),
    ("Tenure <1y vs >=1y", lambda r: r["tenure_years"] < 1.0, lambda r: r["tenure_years"] >= 1.0),
]


def find_defects(rows):
    results = []
    for name, in_group, out_group in SEGMENTS:
        a = [r["experience_score"] for r in rows if in_group(r)]
        b = [r["experience_score"] for r in rows if out_group(r)]
        t, p, d = welch_t(a, b)
        lo, hi = bootstrap_ci_mean_diff(a, b)
        # Attrition: 2x2 table [[attr in, stay in], [attr out, stay out]]
        a_attr = sum(r["attrition"] for r in rows if in_group(r))
        b_attr = sum(r["attrition"] for r in rows if out_group(r))
        table = [[a_attr, len(a) - a_attr], [b_attr, len(b) - b_attr]]
        chi2, dof, p_attr = chi_square_test(table)
        results.append({
            "segment": name,
            "n_in": len(a), "n_out": len(b),
            "mean_in": round(mean(a), 3), "mean_out": round(mean(b), 3),
            "mean_diff": round(mean(a) - mean(b), 3),
            "t": round(t, 3), "p": p, "cohens_d": round(d, 3),
            "ci_lo": round(lo, 3), "ci_hi": round(hi, 3),
            "attrition_in": round(a_attr / len(a), 3),
            "attrition_out": round(b_attr / len(b), 3),
            "chi2": round(chi2, 3), "p_attrition": p_attr,
        })
    corrected_alpha, flags = bonferroni([r["p"] for r in results])
    for r, flag in zip(results, flags):
        r["confirmed"] = bool(flag)
    return results, corrected_alpha
