"""Synthetic credit-card decision cases for GenAI model validation.

All data is synthetic and seeded. No real bank, cardholder, or account
data is used, and nothing here is a claim about any real institution.

Each case is a credit-card account review: the facts a decision-support
model may cite, and the ground-truth decision a human reviewer reached.
"""
from __future__ import annotations

CASES = [
    {
        "case_id": "C001",
        "facts": {"credit_limit": 5000, "balance": 1200, "apr": 24.99,
                  "min_payment": 35, "months_delinquent": 0, "utilization": 24},
        "truth": "approve",
    },
    {
        "case_id": "C002",
        "facts": {"credit_limit": 3000, "balance": 2850, "apr": 29.99,
                  "min_payment": 85, "months_delinquent": 2, "utilization": 95},
        "truth": "decline",
    },
    {
        "case_id": "C003",
        "facts": {"credit_limit": 8000, "balance": 900, "apr": 19.99,
                  "min_payment": 25, "months_delinquent": 0, "utilization": 11},
        "truth": "approve",
    },
    {
        "case_id": "C004",
        "facts": {"credit_limit": 2000, "balance": 1900, "apr": 27.99,
                  "min_payment": 60, "months_delinquent": 1, "utilization": 95},
        "truth": "review",
    },
    {
        "case_id": "C005",
        "facts": {"credit_limit": 10000, "balance": 4500, "apr": 22.99,
                  "min_payment": 110, "months_delinquent": 0, "utilization": 45},
        "truth": "approve",
    },
    {
        "case_id": "C006",
        "facts": {"credit_limit": 1500, "balance": 1480, "apr": 29.99,
                  "min_payment": 45, "months_delinquent": 3, "utilization": 99},
        "truth": "decline",
    },
    {
        "case_id": "C007",
        "facts": {"credit_limit": 6000, "balance": 3000, "apr": 21.99,
                  "min_payment": 75, "months_delinquent": 0, "utilization": 50},
        "truth": "review",
    },
    {
        "case_id": "C008",
        "facts": {"credit_limit": 4000, "balance": 400, "apr": 18.99,
                  "min_payment": 25, "months_delinquent": 0, "utilization": 10},
        "truth": "approve",
    },
    {
        "case_id": "C009",
        "facts": {"credit_limit": 2500, "balance": 2200, "apr": 26.99,
                  "min_payment": 70, "months_delinquent": 2, "utilization": 88},
        "truth": "decline",
    },
    {
        "case_id": "C010",
        "facts": {"credit_limit": 7500, "balance": 1500, "apr": 20.99,
                  "min_payment": 40, "months_delinquent": 0, "utilization": 20},
        "truth": "approve",
    },
    {
        "case_id": "C011",
        "facts": {"credit_limit": 3500, "balance": 1750, "apr": 23.99,
                  "min_payment": 50, "months_delinquent": 1, "utilization": 50},
        "truth": "review",
    },
    {
        "case_id": "C012",
        "facts": {"credit_limit": 9000, "balance": 8100, "apr": 28.99,
                  "min_payment": 240, "months_delinquent": 2, "utilization": 90},
        "truth": "decline",
    },
]


# Synthetic audit cohorts for fairness slices: alternating assignment by
# case order. Audit labels only — not real protected attributes — so a gap
# is a signal to investigate, not proof of bias. Six cases per cohort.
for _i, _c in enumerate(CASES):
    _c.setdefault("group", "cohort-a" if _i % 2 == 0 else "cohort-b")


def decision_rule(facts: dict) -> str:
    """Transparent reference rule: the challenger/benchmark decision logic.

    High utilization with delinquency declines; borderline utilization or
    a single delinquency goes to human review; the rest approve.
    """
    util = facts["utilization"]
    delinq = facts["months_delinquent"]
    if util >= 85 and delinq >= 2:
        return "decline"
    if util >= 85 or delinq >= 2:
        return "review"
    if util >= 50 or delinq == 1:
        return "review"
    return "approve"
