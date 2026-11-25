"""Backtesting, monitoring, data checks, and reproduction checks."""

import math


def vintage_backtest(loans, scores):
    """Predicted vs realised default rate by origination quarter."""
    by_q = {}
    for loan, s in zip(loans, scores):
        q = loan["origination_quarter"]
        by_q.setdefault(q, []).append((s, loan["defaulted"]))
    out = {}
    for q in sorted(by_q):
        rows = by_q[q]
        pred = sum(s for s, _ in rows) / len(rows)
        obs = sum(y for _, y in rows) / len(rows)
        ratio = pred / obs if obs else 0.0
        out[q] = {"n": len(rows), "predicted": round(pred, 3),
                  "observed": round(obs, 3), "ratio": round(ratio, 2),
                  "breach": not (0.80 <= ratio <= 1.25)}
    return out


def psi(expected, actual, bins=10):
    """Population Stability Index between two score distributions."""
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi == lo:
        return 0.0
    width = (hi - lo) / bins
    total = 0.0
    for b in range(bins):
        a, c = lo + b * width, lo + (b + 1) * width
        e_share = sum(1 for v in expected if a <= v < c or (b == bins - 1 and v == hi)) / len(expected)
        a_share = sum(1 for v in actual if a <= v < c or (b == bins - 1 and v == hi)) / len(actual)
        e_share = max(e_share, 0.0001)
        a_share = max(a_share, 0.0001)
        total += (a_share - e_share) * math.log(a_share / e_share)
    return round(total, 4)


def score_drift(expected, actual):
    mean_e = sum(expected) / len(expected)
    mean_a = sum(actual) / len(actual)
    return round((mean_a - mean_e) / mean_e, 3) if mean_e else 0.0


def data_completeness_checks(loans):
    """Accuracy / completeness checks on model input data (SQL-style)."""
    fields = ["annual_revenue", "years_in_business", "cashflow_coverage",
              "credit_score", "loan_amount", "industry_risk"]
    issues = []
    ids = [l["loan_id"] for l in loans]
    if len(ids) != len(set(ids)):
        issues.append("duplicate loan_id values present")
    for f in fields:
        missing = sum(1 for l in loans if l.get(f) is None)
        if missing:
            issues.append("%d missing values in %s" % (missing, f))
    bad_scores = sum(1 for l in loans if not (300 <= l["credit_score"] <= 850))
    if bad_scores:
        issues.append("%d credit scores outside 300-850" % bad_scores)
    neg = sum(1 for l in loans if l["annual_revenue"] <= 0 or l["loan_amount"] <= 0)
    if neg:
        issues.append("%d loans with non-positive revenue or amount" % neg)
    stale = sum(1 for l in loans if l["years_in_business"] > 60)
    if stale:
        issues.append("%d loans with implausible years in business" % stale)
    return issues


def reproduction_check(champion_scores, refit_scores, tol=0.02):
    """Re-fit the developer model independently and compare outputs."""
    diffs = [abs(a - b) for a, b in zip(champion_scores, refit_scores)]
    max_diff = max(diffs) if diffs else 0.0
    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    return {"max_abs_diff": round(max_diff, 4),
            "mean_abs_diff": round(mean_diff, 4),
            "reproduced": max_diff <= tol}
