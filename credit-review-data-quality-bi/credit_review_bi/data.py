"""Seeded synthetic credit-review data.

Three tables, mirroring what a Credit Review team works with:

- loans: the reviewed portfolio (segment, outstanding, risk rating).
- reviews: one row per credit review (type, dates, outcome, cycle time).
- findings: issues raised by a review (severity, category, status).

A small number of bad rows are planted on purpose so the quality checks
in quality.py have real defects to catch: a loan with a missing risk
rating, a duplicated loan id, a negative outstanding balance, and a
finding that points at a review that does not exist.
"""

import random
from dataclasses import dataclass, field

SEGMENTS = ("Commercial", "CRE", "C&I", "Consumer")
REVIEW_TYPES = ("Annual", "Interim", "Trigger")
OUTCOMES = ("Pass", "Pass with findings", "Fail")
SEVERITIES = ("Low", "Moderate", "High", "Critical")
FINDING_CATEGORIES = ("Data Quality", "Documentation", "Policy", "Model")
FINDING_STATUSES = ("Open", "Remediated", "Overdue")


@dataclass
class Dataset:
    loans: list = field(default_factory=list)
    reviews: list = field(default_factory=list)
    findings: list = field(default_factory=list)


def build_dataset(seed: int = 42) -> Dataset:
    rng = random.Random(seed)
    loans, reviews, findings = [], [], []

    for i in range(1, 121):
        loans.append({
            "loan_id": f"LN-{i:04d}",
            "borrower": f"Borrower {i:03d}",
            "segment": rng.choice(SEGMENTS),
            "outstanding": round(rng.uniform(250_000, 45_000_000), 2),
            "risk_rating": rng.randint(1, 6),
            "review_due": f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "status": rng.choice(("Active", "Active", "Active", "Watch", "Closed")),
        })

    review_id = 0
    for loan in loans:
        if rng.random() < 0.85:  # most loans have a completed review
            review_id += 1
            cycle = rng.randint(5, 60)
            reviews.append({
                "review_id": f"RV-{review_id:04d}",
                "loan_id": loan["loan_id"],
                "reviewer": f"Reviewer {rng.randint(1, 12):02d}",
                "review_type": rng.choice(REVIEW_TYPES),
                "started": "2026-01-05",
                "cycle_days": cycle,
                "outcome": rng.choice(OUTCOMES),
            })

    finding_id = 0
    for review in reviews:
        for _ in range(rng.randint(0, 3)):
            finding_id += 1
            findings.append({
                "finding_id": f"FD-{finding_id:04d}",
                "review_id": review["review_id"],
                "severity": rng.choice(SEVERITIES),
                "category": rng.choice(FINDING_CATEGORIES),
                "status": rng.choice(FINDING_STATUSES),
                "opened": "2026-02-10",
                "due_in_days": rng.randint(-30, 90),
            })

    # Planted defects for the quality checks to catch.
    loans.append({"loan_id": "LN-0001", "borrower": "Borrower 001",
                  "segment": "Commercial", "outstanding": 1_000_000.0,
                  "risk_rating": 3, "review_due": "2026-06-01",
                  "status": "Active"})  # duplicate loan_id
    loans.append({"loan_id": "LN-9999", "borrower": "Borrower 999",
                  "segment": "CRE", "outstanding": -500.0,
                  "risk_rating": None, "review_due": "2026-06-01",
                  "status": "Active"})  # negative balance, missing rating
    findings.append({"finding_id": "FD-9999", "review_id": "RV-9999",
                     "severity": "High", "category": "Data Quality",
                     "status": "Open", "opened": "2026-02-10",
                     "due_in_days": -5})  # orphan finding, no such review

    return Dataset(loans=loans, reviews=reviews, findings=findings)
