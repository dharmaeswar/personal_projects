"""Feature engineering for the underwriting models.

The champion logistic regression runs on the six raw underwriting fields.
The gradient-boosting challenger also gets engineered lending features:
affordability ratios, binned credit/coverage bands, and the interactions a
linear model cannot express on its own. Every feature is derived from the
same synthetic loan record, so the feature set is fully reproducible.
"""

import math

# Raw fields (same order as models.FEATURES) plus engineered columns.
FEATURE_COLUMNS = ["annual_revenue", "years_in_business", "cashflow_coverage",
                   "credit_score", "loan_amount", "industry_risk",
                   "loan_to_income", "log_revenue", "score_band",
                   "coverage_band", "revenue_x_coverage", "score_x_years"]


def score_band(score):
    """Credit-score band: 0 subprime (<580), 1 near-prime, 2 prime, 3 super-prime."""
    if score < 580:
        return 0
    if score < 670:
        return 1
    if score < 740:
        return 2
    return 3


def coverage_band(coverage):
    """Cash-flow coverage band: 0 thin (<1.0), 1 adequate, 2 strong, 3 very strong."""
    if coverage < 1.0:
        return 0
    if coverage < 1.5:
        return 1
    if coverage < 2.5:
        return 2
    return 3


def engineer_features(row):
    """Engineered feature vector for one loan record, in FEATURE_COLUMNS order."""
    revenue = row["annual_revenue"]
    loan = row["loan_amount"]
    coverage = row["cashflow_coverage"]
    score = row["credit_score"]
    years = row["years_in_business"]
    return [
        revenue,
        years,
        coverage,
        score,
        loan,
        row["industry_risk"],
        loan / revenue if revenue > 0 else 0.0,          # loan-to-income
        math.log(revenue) if revenue > 0 else 0.0,        # log revenue
        float(score_band(score)),
        float(coverage_band(coverage)),
        (revenue / 100000.0) * coverage,                  # revenue x coverage
        (score / 100.0) * years,                          # score x years
    ]
