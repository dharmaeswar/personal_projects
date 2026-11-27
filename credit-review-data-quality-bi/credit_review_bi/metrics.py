"""Business-intelligence metrics for the Credit Review dashboard.

Every metric is computed from the seeded data set only, and each one
names its source tables so the lineage in quality.py can be checked
against it.
"""

import statistics
from collections import Counter


def _median(values):
    return round(statistics.median(values), 1) if values else None


def build_dashboard(dataset, checks=None) -> dict:
    loans, reviews, findings = dataset.loans, dataset.reviews, dataset.findings

    open_findings = [f for f in findings if f["status"] in ("Open", "Overdue")]
    overdue_findings = [f for f in findings
                        if f["status"] == "Overdue" or
                        (f["status"] == "Open" and f["due_in_days"] < 0)]
    overdue_reviews = [r for r in reviews
                       if r["outcome"] == "Fail" and r["cycle_days"] > 45]

    findings_by_severity = dict(Counter(f["severity"] for f in open_findings))
    findings_by_category = dict(Counter(f["category"] for f in open_findings))
    reviews_by_outcome = dict(Counter(r["outcome"] for r in reviews))
    reviews_by_type = dict(Counter(r["review_type"] for r in reviews))
    loans_by_segment = dict(Counter(r["segment"] for r in loans))
    ratings = Counter(r["risk_rating"] for r in loans if r.get("risk_rating") is not None)

    total_outstanding = round(sum(r["outstanding"] for r in loans
                                  if r.get("outstanding") and r["outstanding"] > 0), 2)

    dashboard = {
        "portfolio": {
            "loan_count": len(loans),
            "total_outstanding_usd": total_outstanding,
            "loans_by_segment": loans_by_segment,
            "loans_by_risk_rating": {str(k): v for k, v in sorted(ratings.items())},
        },
        "reviews": {
            "review_count": len(reviews),
            "reviews_by_outcome": reviews_by_outcome,
            "reviews_by_type": reviews_by_type,
            "median_cycle_days": _median([r["cycle_days"] for r in reviews]),
            "overdue_reviews": len(overdue_reviews),
        },
        "findings": {
            "finding_count": len(findings),
            "open_findings": len(open_findings),
            "overdue_findings": len(overdue_findings),
            "open_findings_by_severity": findings_by_severity,
            "open_findings_by_category": findings_by_category,
        },
    }
    if checks is not None:
        from .quality import quality_score
        dashboard["data_quality"] = {
            "checks_run": len(checks),
            "checks_passed": sum(1 for c in checks if c.passed),
            "score": quality_score(checks),
            "failed_checks": [c.name for c in checks if not c.passed],
        }
    return dashboard


def format_dashboard(dashboard: dict) -> str:
    """Plain-text dashboard report, readable in a terminal or as a file."""
    lines = ["CREDIT REVIEW — DATA QUALITY & BI DASHBOARD", "=" * 44, ""]
    p = dashboard["portfolio"]
    lines.append(f"Portfolio: {p['loan_count']} loans, "
                 f"${p['total_outstanding_usd']:,.0f} outstanding")
    lines.append(f"  by segment: {p['loans_by_segment']}")
    lines.append(f"  by risk rating: {p['loans_by_risk_rating']}")
    r = dashboard["reviews"]
    lines.append(f"Reviews: {r['review_count']} completed, "
                 f"median cycle {r['median_cycle_days']} days, "
                 f"{r['overdue_reviews']} overdue")
    lines.append(f"  by outcome: {r['reviews_by_outcome']}")
    lines.append(f"  by type: {r['reviews_by_type']}")
    f = dashboard["findings"]
    lines.append(f"Findings: {f['finding_count']} total, {f['open_findings']} open, "
                 f"{f['overdue_findings']} overdue")
    lines.append(f"  open by severity: {f['open_findings_by_severity']}")
    lines.append(f"  open by category: {f['open_findings_by_category']}")
    if "data_quality" in dashboard:
        q = dashboard["data_quality"]
        lines.append(f"Data quality: {q['checks_passed']}/{q['checks_run']} checks passed "
                     f"(score {q['score']})")
        for name in q["failed_checks"]:
            lines.append(f"  FAILED: {name}")
    return "\n".join(lines) + "\n"
