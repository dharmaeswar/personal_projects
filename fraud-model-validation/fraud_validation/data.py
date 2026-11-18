"""Seeded synthetic card-transaction generator for fraud-model validation.

All data is synthetic. No real bank, cardholder, or transaction data is used.
Fraud is rare (~2%) and its probability is driven by a small set of features
(high amount, night hours, cross-border, card-not-present, high velocity,
new device), so a model has real signal to find.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_TRANSACTIONS = 20_000
SEED = 42

FEATURES = [
    "amount",
    "hour",
    "merchant_category",
    "device_age_days",
    "velocity_1h",
    "velocity_24h",
    "account_age_days",
    "cross_border",
    "card_present",
]

MERCHANT_CATEGORIES = ["grocery", "fuel", "online_retail", "travel",
                       "dining", "electronics", "health", "other"]
REGIONS = ["North", "South", "East", "West"]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def generate_transactions(n: int = N_TRANSACTIONS, seed: int = SEED) -> pd.DataFrame:
    """Generate ``n`` synthetic card transactions with a binary fraud label."""
    rng = np.random.default_rng(seed)

    amount = rng.lognormal(mean=3.6, sigma=1.1, size=n)  # median ~$37
    hour = rng.integers(0, 24, size=n)
    merchant_category = rng.integers(0, len(MERCHANT_CATEGORIES), size=n)
    device_age_days = rng.exponential(scale=400.0, size=n)
    velocity_1h = rng.poisson(lam=1.2, size=n)
    velocity_24h = rng.poisson(lam=9.0, size=n)
    account_age_days = rng.exponential(scale=900.0, size=n)
    cross_border = rng.binomial(1, 0.12, size=n)
    card_present = rng.binomial(1, 0.72, size=n)
    region = rng.choice(REGIONS, size=n)

    # Fraud log-odds: a few features carry the signal.
    log_amount = np.log1p(amount)
    night = ((hour < 5) | (hour >= 23)).astype(float)
    new_device = (device_age_days < 30).astype(float)
    logit = (
        -5.3
        + 0.55 * (log_amount - log_amount.mean())
        + 0.9 * night
        + 1.1 * cross_border
        + 0.9 * (1 - card_present)
        + 0.35 * np.clip(velocity_1h - 1.0, 0, None)
        + 0.5 * new_device
        + 0.02 * np.clip(velocity_24h - 9.0, 0, None)
    )
    fraud_prob = _sigmoid(logit)
    is_fraud = rng.binomial(1, fraud_prob, size=n)

    return pd.DataFrame(
        {
            "amount": np.round(amount, 2),
            "hour": hour,
            "merchant_category": merchant_category,
            "device_age_days": np.round(device_age_days, 1),
            "velocity_1h": velocity_1h,
            "velocity_24h": velocity_24h,
            "account_age_days": np.round(account_age_days, 1),
            "cross_border": cross_border,
            "card_present": card_present,
            "region": region,
            "is_fraud": is_fraud,
        }
    )


def train_test_split(
    df: pd.DataFrame, test_size: float = 0.2, seed: int = SEED
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Random train/test split (shuffled, seeded)."""
    shuffled = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    n_test = int(round(len(shuffled) * test_size))
    test = shuffled.iloc[:n_test].reset_index(drop=True)
    train = shuffled.iloc[n_test:].reset_index(drop=True)
    return train, test
