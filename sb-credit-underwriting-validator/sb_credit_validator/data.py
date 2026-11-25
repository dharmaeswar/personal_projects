"""Synthetic small-business loan portfolio for validation demos.

All data is synthetic and seeded. No real borrower, bank, or transaction
data is used. The generator mirrors a Square Loans-style book: small
businesses, one loan each, with a known default outcome.
"""

import random

INDUSTRIES = ["retail", "food", "services", "ecommerce", "health"]


def _sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + 2.718281828459045 ** (-x))
    e = 2.718281828459045 ** x
    return e / (1.0 + e)


def generate_portfolio(n=4000, seed=42, drift=False):
    """Generate n synthetic small-business loans.

    drift=True shifts the production population slightly (lower scores,
    higher loan sizes) so monitoring can detect it.
    """
    rng = random.Random(seed)
    loans = []
    for i in range(n):
        industry = rng.choice(INDUSTRIES)
        industry_risk = {"retail": 0.10, "food": 0.18, "services": 0.05,
                         "ecommerce": 0.12, "health": 0.02}[industry]
        revenue = rng.lognormvariate(11.5, 0.9)  # ~$100k median
        years = max(0.5, rng.gauss(6.0, 3.5))
        coverage = max(0.4, rng.gauss(1.6, 0.6))  # cash-flow coverage ratio
        score = rng.gauss(660, 55)
        if drift:
            score -= 18.0
            revenue *= 0.92
        loan = rng.uniform(5000, 120000) * (revenue / 200000.0 + 0.4)
        loan = min(max(loan, 5000), 250000)
        # True default driver: weak coverage, low score, short history.
        logit = (-1.9 - 0.9 * (coverage - 1.6) - 0.012 * (score - 660)
                 - 0.09 * (years - 6.0) + 0.35 * industry_risk
                 + 0.000004 * (loan - 40000))
        p_default = _sigmoid(logit)
        defaulted = 1 if rng.random() < p_default else 0
        quarter = rng.choice(["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4",
                              "2025-Q1", "2025-Q2"])
        loans.append({
            "loan_id": "SB-%06d" % (i + 1),
            "industry": industry,
            "industry_risk": round(industry_risk, 2),
            "annual_revenue": round(revenue, 2),
            "years_in_business": round(years, 1),
            "cashflow_coverage": round(coverage, 2),
            "credit_score": int(round(score)),
            "loan_amount": round(loan, 2),
            "origination_quarter": quarter,
            "defaulted": defaulted,
            "true_pd": round(p_default, 4),
        })
    return loans
