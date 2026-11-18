"""Synthetic daily payment-acceptance-rate series.

A seeded generator so every run is reproducible: a slow upward trend,
a weekly seasonal pattern (weekend dip), Gaussian noise, and two short
holiday dips. Rates stay inside (0, 1).
"""

import math
import random
from datetime import date, timedelta

START = date(2025, 1, 6)  # a Monday


def generate_series(n_days=365, seed=7):
    """Return a list of (date, acceptance_rate) tuples."""
    rng = random.Random(seed)
    out = []
    for i in range(n_days):
        day = START + timedelta(days=i)
        trend = 0.00008 * i
        # Weekly seasonality: weekend dip, mid-week peak.
        seasonal = 0.02 * math.sin(2 * math.pi * (i % 7) / 7.0)
        noise = rng.gauss(0.0, 0.008)
        rate = 0.86 + trend + seasonal + noise
        # Two short holiday dips (days 60-66 and 300-306).
        if 60 <= i <= 66 or 300 <= i <= 306:
            rate -= 0.05
        rate = min(max(rate, 0.50), 0.99)
        out.append((day.isoformat(), round(rate, 4)))
    return out


def to_values(series):
    return [rate for _, rate in series]
