"""Seeded synthetic customer-success dataset for a QuickBooks-style SMB platform.

All customers, outcomes and effects are synthetic (fixed seed). The generator
plants two effects with known size so every estimate can be checked:
an onboarding intervention that shortens time-to-value and lowers churn, and
a coverage investment rolled out non-randomly to larger firms that lifts
retention. Nothing here describes real customers, real firms or a real
deployment.
"""
import math
import random

FEATURES = 8  # tracked product features (invoicing, payroll, inventory, ...)

PLANS = ("Starter", "Plus", "Advanced")


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x)) if x > -30 else 0.0


def generate(n=2400, seed=20261116):
    """Return a list of customer dicts with pre/post usage and outcomes."""
    rng = random.Random(seed)
    customers = []
    for i in range(n):
        employees = rng.choice([3, 8, 15, 30, 60, 120])
        plan = rng.choices(PLANS, weights=[0.45, 0.40, 0.15])[0]
        months = rng.randint(2, 36)
        latent = rng.betavariate(2.5, 2.0)  # underlying engagement, 0..1
        # Randomized onboarding intervention (50/50): guided setup + check-ins.
        onboard_treat = rng.random() < 0.5
        # Coverage investment: NON-randomized rollout, mostly larger firms.
        arr = employees * rng.uniform(90, 160) * (1.6 if plan == "Advanced" else 1.0)
        coverage_treat = (arr > 9000 and rng.random() < 0.80) or (
            6000 < arr <= 9000 and rng.random() < 0.25
        )
        # Time-to-value (days to first closed books / first invoice paid).
        ttv = max(1, round(rng.gauss(24 - 18 * latent, 7) - (6 if onboard_treat else 0)))
        features_adopted = min(
            FEATURES, max(0, round(latent * FEATURES + rng.gauss(0, 1.1)))
        )
        logins = max(0, round(rng.gauss(6 + 22 * latent, 5)))
        tickets = max(0, round(rng.gauss(3.5 - 2.5 * latent, 1.8)))
        nps = max(0, min(10, round(rng.gauss(2 + 7 * latent, 1.6))))
        seats = max(1, round(employees * rng.uniform(0.15, 0.5)))
        # Pre-period usage score (months 1-6) and post-period (months 7-12).
        usage_pre = max(0.0, min(1.0, latent + rng.gauss(0, 0.08)))
        usage_post = max(
            0.0,
            min(1.0, latent + rng.gauss(0, 0.08) + (0.08 if coverage_treat else 0.0)),
        )
        # Churn: logistic on engagement, support load, onboarding treatment.
        churn_logit = (
            1.1
            - 3.2 * latent
            + 0.35 * tickets
            - 0.35 * (1 if onboard_treat else 0)
            - 0.30 * (1 if coverage_treat else 0)
            - 0.02 * months
        )
        churn_p = _sigmoid(churn_logit)
        retained = rng.random() > churn_p
        # Expansion: grows with engagement, adoption and plan headroom.
        expand_logit = -2.2 + 2.4 * latent + 0.25 * features_adopted - 0.4 * (1 if plan == "Advanced" else 0)
        expanded = retained and rng.random() < _sigmoid(expand_logit)
        customers.append(
            {
                "customer_id": i,
                "employees": employees,
                "plan": plan,
                "months_on_platform": months,
                "arr": round(arr, 2),
                "seats": seats,
                "latent": round(latent, 4),
                "onboard_treat": onboard_treat,
                "coverage_treat": coverage_treat,
                "time_to_value_days": ttv,
                "features_adopted": features_adopted,
                "weekly_logins": logins,
                "tickets_90d": tickets,
                "nps": nps,
                "usage_pre": round(usage_pre, 4),
                "usage_post": round(usage_post, 4),
                "churn_p": round(churn_p, 4),
                "retained": retained,
                "expanded": expanded,
            }
        )
    return customers


def weekly_series(customers, weeks_pre=12, weeks_post=8, seed=99):
    """Weekly usage series per segment, derived from the same customers.

    Treated series: customers who got the coverage investment. Donors: the
    three plan segments among customers who did not. Pre weeks centre on each
    segment's mean pre-period usage, post weeks on its mean post-period usage
    (which carries the planted +0.08 lift for the treated group only).
    Small seeded noise keeps the series from being flat.
    """
    rng = random.Random(seed)

    def series(rows, key, weeks, noise=0.008):
        base = sum(r[key] for r in rows) / len(rows)
        return [round(max(0.0, min(1.0, base + rng.gauss(0, noise))), 4) for _ in range(weeks)]

    treated = [c for c in customers if c["coverage_treat"]]
    donors = {}
    for plan in PLANS:
        rows = [c for c in customers if not c["coverage_treat"] and c["plan"] == plan]
        if rows:
            donors[plan] = rows
    return {
        "treated_pre": series(treated, "usage_pre", weeks_pre),
        "treated_post": series(treated, "usage_post", weeks_post),
        "donors_pre": [series(rows, "usage_pre", weeks_pre) for rows in donors.values()],
        "donors_post": [series(rows, "usage_post", weeks_post) for rows in donors.values()],
        "donor_names": list(donors.keys()),
    }


def features_matrix(customers, target="retained"):
    """Design matrix + label for the propensity models (no leakage columns)."""
    rows, labels = [], []
    for c in customers:
        rows.append(
            [
                c["months_on_platform"],
                c["features_adopted"],
                c["weekly_logins"],
                c["tickets_90d"],
                c["nps"],
                c["time_to_value_days"],
                c["employees"],
                1 if c["plan"] == "Advanced" else 0,
            ]
        )
        labels.append(1 if c[target] else 0)
    return rows, labels
