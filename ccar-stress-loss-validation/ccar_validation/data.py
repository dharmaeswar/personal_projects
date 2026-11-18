"""CCAR stress-loss validation: synthetic loan-portfolio data generation.

All data is synthetic and seeded for reproducibility. No real borrower,
bank, or regulatory data is used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RNG_SEED = 42

MACRO_COLUMNS = [
    "gdp_growth",        # quarterly real GDP growth, %
    "unemployment_rate",  # %
    "hpi_growth",         # house price index growth, %
    "credit_spread",      # corporate credit spread, bps
]

LOAN_COLUMNS = [
    "loan_id",
    "segment",            # 'mortgage', 'auto', 'credit_card', 'commercial'
    "origination_year",
    "ltv",                # loan-to-value, %
    "fico_score",
    "loan_balance",
]

N_LOANS = 5_000


def generate_portfolio(n_loans: int = N_LOANS, seed: int = RNG_SEED) -> pd.DataFrame:
    """Generate a seeded synthetic loan portfolio with observed loss rates.

    Loss rates are produced from a known logistic-style data-generating
    process so a champion logistic-regression forecaster can beat a
    historical-average benchmark.
    """
    rng = np.random.default_rng(seed)

    segments = rng.choice(
        ["mortgage", "auto", "credit_card", "commercial"],
        size=n_loans,
        p=[0.40, 0.25, 0.20, 0.15],
    )
    segment_effect = np.array(
        [{"mortgage": -0.8, "auto": 0.0, "credit_card": 1.2, "commercial": 0.4}[s]
         for s in segments]
    )

    # Macro features: one quarterly observation set per loan (synthetic).
    gdp_growth = rng.normal(2.0, 1.5, n_loans)
    unemployment_rate = rng.normal(5.0, 1.8, n_loans).clip(2.0, 12.0)
    hpi_growth = rng.normal(3.0, 4.0, n_loans)
    credit_spread = rng.normal(150.0, 60.0, n_loans).clip(40.0, 500.0)

    ltv = rng.normal(70.0, 15.0, n_loans).clip(20.0, 100.0)
    fico_score = rng.normal(700.0, 60.0, n_loans).clip(500.0, 850.0)
    loan_balance = rng.lognormal(np.log(120_000.0), 0.8, n_loans)
    origination_year = rng.integers(2015, 2025, n_loans)

    # Known data-generating process: logit of loss rate.
    logit = (
        -3.0
        + segment_effect
        - 0.25 * gdp_growth
        + 0.35 * unemployment_rate
        - 0.06 * hpi_growth
        + 0.004 * credit_spread
        + 0.02 * (ltv - 70.0)
        - 0.006 * (fico_score - 700.0)
    )
    prob_loss = 1.0 / (1.0 + np.exp(-logit))
    # Observed loss rate: a defaulted loan loses a fraction (LGD) of its
    # balance; a performing loan loses nothing. Small measurement noise.
    lgd = rng.normal(0.45, 0.10, n_loans).clip(0.10, 0.80)
    defaulted = rng.random(n_loans) < prob_loss
    observed_loss_rate = np.clip(
        defaulted * lgd + rng.normal(0.0, 0.005, n_loans), 0.0, 1.0
    )

    df = pd.DataFrame(
        {
            "loan_id": np.arange(1, n_loans + 1),
            "segment": segments,
            "origination_year": origination_year,
            "ltv": np.round(ltv, 2),
            "fico_score": np.round(fico_score, 0).astype(int),
            "loan_balance": np.round(loan_balance, 2),
            "gdp_growth": np.round(gdp_growth, 3),
            "unemployment_rate": np.round(unemployment_rate, 3),
            "hpi_growth": np.round(hpi_growth, 3),
            "credit_spread": np.round(credit_spread, 1),
            "observed_loss_rate": np.round(observed_loss_rate, 4),
            "defaulted": defaulted.astype(int),
        }
    )
    return df


def train_test_split(df: pd.DataFrame, test_size: float = 0.25, seed: int = RNG_SEED):
    """Deterministic chronological-ish split by loan_id hash (seeded shuffle)."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(df))
    n_test = int(len(df) * test_size)
    test_idx, train_idx = idx[:n_test], idx[n_test:]
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)
