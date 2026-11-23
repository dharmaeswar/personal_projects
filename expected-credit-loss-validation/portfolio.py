"""Deterministic synthetic loan portfolio for ECL validation.

Every draw comes from a seeded ``random.Random`` instance, so the same seed
always produces the same portfolio. A small share of loans is pushed into
Stage 2 (score drop or 30+ days past due) and Stage 3 (defaulted or 90+
days past due) so staging, back-testing and monitoring all have signal.
"""

import random

from ecl_model import Loan


def generate_portfolio(n=500, seed=42):
    """Generate n synthetic loans. Deterministic for a given seed."""
    rng = random.Random(seed)
    loans = []
    for i in range(n):
        score_orig = rng.randint(580, 820)
        # Most loans stay healthy; a minority deteriorate.
        roll = rng.random()
        if roll < 0.06:
            # Defaulted / deep delinquency -> Stage 3.
            days_past_due = rng.randint(90, 180)
            score_now = max(300, score_orig - rng.randint(120, 250))
            defaulted = rng.random() < 0.7
        elif roll < 0.22:
            # SICR -> Stage 2: delinquency or a big score drop.
            if rng.random() < 0.5:
                days_past_due = rng.randint(30, 89)
                score_now = max(300, score_orig - rng.randint(20, 80))
            else:
                days_past_due = rng.randint(0, 29)
                score_now = max(300, score_orig - rng.randint(100, 180))
            defaulted = False
        else:
            days_past_due = rng.randint(0, 15)
            score_now = max(300, score_orig - rng.randint(0, 40))
            defaulted = False
        balance = round(rng.uniform(5_000, 250_000), 2)
        # PD rises as the current score falls.
        if score_now >= 720:
            pd_12m = rng.uniform(0.002, 0.008)
        elif score_now >= 660:
            pd_12m = rng.uniform(0.008, 0.03)
        elif score_now >= 600:
            pd_12m = rng.uniform(0.03, 0.08)
        else:
            pd_12m = rng.uniform(0.08, 0.20)
        pd_lifetime = min(0.95, pd_12m * rng.uniform(2.0, 4.0))
        lgd = round(rng.uniform(0.20, 0.60), 4)
        loans.append(
            Loan(
                loan_id=f"LN-{i + 1:04d}",
                balance=balance,
                pd_12m=round(pd_12m, 6),
                pd_lifetime=round(pd_lifetime, 6),
                lgd=lgd,
                days_past_due=days_past_due,
                credit_score_now=score_now,
                credit_score_orig=score_orig,
                defaulted=defaulted,
            )
        )
    return loans


def simulate_realised_losses(loans, seed=7):
    """Simulate realised losses: a loan defaults with prob. pd_lifetime.

    A defaulted loan loses balance x LGD. Seeded, so results are repeatable.
    Returns {loan_id: realised loss}.
    """
    rng = random.Random(seed)
    realised = {}
    for loan in loans:
        if rng.random() < loan.pd_lifetime:
            realised[loan.loan_id] = round(loan.balance * loan.lgd, 2)
        else:
            realised[loan.loan_id] = 0.0
    return realised
