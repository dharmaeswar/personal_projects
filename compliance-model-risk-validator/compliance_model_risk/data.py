"""Synthetic compliance data, seeded for reproducibility.

The alert book is a synthetic set of monitored transactions. Each row is
one transaction that passed through a transaction-monitoring system; the
label is whether a human investigator later confirmed it SAR-worthy.
No real bank, customer, or transaction data is used.
"""

import numpy as np
import pandas as pd

FEATURES = [
    "amount_log",
    "velocity_7d",
    "cross_border",
    "night_flag",
    "new_device",
    "structuring_proximity",
]

GROUPS = ["Group A", "Group B", "Group C"]


def _scores(rng, n):
    """Latent risk score driving the synthetic SAR-worthy label."""
    amount_log = rng.normal(8.0, 1.2, n)
    velocity_7d = rng.poisson(4.0, n).astype(float)
    cross_border = rng.binomial(1, 0.25, n).astype(float)
    night_flag = rng.binomial(1, 0.18, n).astype(float)
    new_device = rng.binomial(1, 0.12, n).astype(float)
    structuring = np.clip(rng.normal(0.15, 0.25, n), 0.0, 1.0)
    z = (
        -4.2
        + 0.45 * (amount_log - 8.0)
        + 0.35 * velocity_7d
        + 0.9 * cross_border
        + 0.6 * night_flag
        + 0.7 * new_device
        + 1.4 * structuring
    )
    return amount_log, velocity_7d, cross_border, night_flag, new_device, structuring, z


def generate_alert_book(n=6000, seed=42):
    """Synthetic transaction-monitoring alert book.

    Returns a DataFrame with the six model features, the SAR-worthy
    label, and a customer group used only for fairness slices.
    """
    rng = np.random.default_rng(seed)
    amount_log, velocity, cross_border, night, new_device, structuring, z = _scores(rng, n)
    prob = 1.0 / (1.0 + np.exp(-z))
    label = (rng.random(n) < prob).astype(int)
    group = rng.choice(GROUPS, size=n, p=[0.5, 0.3, 0.2])
    return pd.DataFrame(
        {
            "amount_log": amount_log,
            "velocity_7d": velocity,
            "cross_border": cross_border,
            "night_flag": night,
            "new_device": new_device,
            "structuring_proximity": structuring,
            "sar_worthy": label,
            "group": group,
        }
    )


def generate_monitoring_book(n=6000, seed=7, drift=0.0):
    """A later-period book, optionally shifted to simulate score drift.

    ``drift`` shifts the latent score upward, mimicking a change in the
    monitored population after the model was put into production.
    """
    rng = np.random.default_rng(seed)
    amount_log, velocity, cross_border, night, new_device, structuring, z = _scores(rng, n)
    z = z + drift
    prob = 1.0 / (1.0 + np.exp(-z))
    label = (rng.random(n) < prob).astype(int)
    group = rng.choice(GROUPS, size=n, p=[0.5, 0.3, 0.2])
    return pd.DataFrame(
        {
            "amount_log": amount_log,
            "velocity_7d": velocity,
            "cross_border": cross_border,
            "night_flag": night,
            "new_device": new_device,
            "structuring_proximity": structuring,
            "sar_worthy": label,
            "group": group,
        }
    )
