"""Data-quality monitoring: completeness, uniqueness, validity,
referential integrity, plus metadata, lineage and business definitions.

Each check returns a dict with the check name, the table it ran on, a
pass/fail verdict and the ids of the rows that failed, so a dashboard can
show exactly what broke instead of a single red/green flag.
"""

from dataclasses import dataclass, field

# Business definitions: one plain-language definition per governed field.
# A metric is only trusted when every field it uses has a definition here.
BUSINESS_DEFINITIONS = {
    "loan_id": "Unique identifier of a loan in the reviewed portfolio.",
    "outstanding": "Current outstanding balance in USD; must be zero or positive.",
    "risk_rating": "Internal credit risk rating, 1 (strongest) to 6 (weakest).",
    "review_id": "Unique identifier of a credit review.",
    "cycle_days": "Calendar days from review start to sign-off.",
    "severity": "Finding severity: Low, Moderate, High or Critical.",
    "status": "Current status of a loan, review or finding.",
}

# Lineage: every dashboard metric traces back to its source tables.
LINEAGE = {
    "open_findings_by_severity": ["findings"],
    "overdue_reviews": ["reviews", "loans"],
    "median_review_cycle_days": ["reviews"],
    "rating_migration": ["loans"],
    "data_quality_score": ["loans", "reviews", "findings"],
}


@dataclass
class CheckResult:
    name: str
    table: str
    passed: bool
    failed_ids: list = field(default_factory=list)
    detail: str = ""


def _check(name, table, rows, predicate, id_key):
    failed = [r[id_key] for r in rows if not predicate(r)]
    return CheckResult(name=name, table=table, passed=not failed,
                       failed_ids=failed,
                       detail=f"{len(failed)} of {len(rows)} rows failed")


def run_quality_checks(dataset) -> list:
    """Run every quality check over the three tables."""
    checks = []
    loans, reviews, findings = dataset.loans, dataset.reviews, dataset.findings

    checks.append(_check("completeness: risk_rating present", "loans", loans,
                         lambda r: r.get("risk_rating") is not None, "loan_id"))
    checks.append(_check("completeness: outstanding present", "loans", loans,
                         lambda r: r.get("outstanding") is not None, "loan_id"))
    checks.append(_check("uniqueness: loan_id", "loans", loans,
                         lambda r: [x["loan_id"] for x in loans].count(r["loan_id"]) == 1,
                         "loan_id"))
    checks.append(_check("validity: outstanding >= 0", "loans", loans,
                         lambda r: r.get("outstanding") is not None and r["outstanding"] >= 0,
                         "loan_id"))
    checks.append(_check("validity: risk_rating in 1..6", "loans", loans,
                         lambda r: r.get("risk_rating") in (1, 2, 3, 4, 5, 6),
                         "loan_id"))
    checks.append(_check("validity: cycle_days in 1..90", "reviews", reviews,
                         lambda r: 1 <= r["cycle_days"] <= 90, "review_id"))
    review_ids = {r["review_id"] for r in reviews}
    checks.append(_check("referential integrity: finding.review_id exists",
                         "findings", findings,
                         lambda r: r["review_id"] in review_ids, "finding_id"))
    loan_ids = {r["loan_id"] for r in loans}
    checks.append(_check("referential integrity: review.loan_id exists",
                         "reviews", reviews,
                         lambda r: r["loan_id"] in loan_ids, "review_id"))
    checks.append(_check("validity: severity in allowed set", "findings", findings,
                         lambda r: r["severity"] in ("Low", "Moderate", "High", "Critical"),
                         "finding_id"))
    return checks


def quality_score(checks: list) -> float:
    """Share of checks passing, 0.0-1.0. Empty check list scores 0.0."""
    if not checks:
        return 0.0
    return round(sum(1 for c in checks if c.passed) / len(checks), 3)


def lineage_for(metric: str) -> list:
    """Source tables a dashboard metric is built from."""
    return list(LINEAGE.get(metric, []))


def definition_for(field_name: str):
    """Business definition for a governed field, or None if undefined."""
    return BUSINESS_DEFINITIONS.get(field_name)
