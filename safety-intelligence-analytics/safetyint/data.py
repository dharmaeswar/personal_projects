# Safety Intelligence Analytics — trend detection, anomaly flags and risk
# scoring over synthetic flight-safety event data.
#
# Built for the Delta Air Lines — Sr. Data Scientist, Safety Intelligence
# (Ref 34970) application.
#
# Demo project. Synthetic data only. No real airline, flight, incident or
# safety report is used or claimed, and nothing here is a production
# safety system. Category names follow the shape of public safety
# reporting (unstable approach, TCAS resolution advisory, runway
# excursion precursor, bird strike, ground damage, maintenance finding)
# but every count, date and narrative is generated locally with a seed.
"""Synthetic flight-safety event data for Safety Intelligence analytics."""

from __future__ import annotations

import random
from dataclasses import dataclass

CATEGORIES = (
    "unstable-approach",
    "tcas-ra",
    "runway-excursion-precursor",
    "bird-strike",
    "ground-damage",
    "maintenance-finding",
)

# SMS-style severity weights (1 = minor, 5 = most severe). Stated demo
# assumptions, not a real airline's risk matrix.
SEVERITY_WEIGHTS = {
    "unstable-approach": 4,
    "tcas-ra": 4,
    "runway-excursion-precursor": 5,
    "bird-strike": 2,
    "ground-damage": 2,
    "maintenance-finding": 3,
}

# Baseline monthly event rate per 10,000 flights, per category.
BASELINE_RATES = {
    "unstable-approach": 6.0,
    "tcas-ra": 2.5,
    "runway-excursion-precursor": 0.8,
    "bird-strike": 9.0,
    "ground-damage": 3.0,
    "maintenance-finding": 12.0,
}


@dataclass(frozen=True)
class SafetyEvent:
    """One synthetic safety report."""

    month: str  # "YYYY-MM"
    category: str
    severity: int  # 1-5
    flights: int  # flights flown that month (same for all events in a month)


@dataclass(frozen=True)
class MonthFlights:
    """Flights flown in a month, used as the exposure denominator."""

    month: str
    flights: int


def month_labels(start_year: int, start_month: int, count: int) -> list[str]:
    """Consecutive YYYY-MM labels starting at (start_year, start_month)."""
    labels: list[str] = []
    year, month = start_year, start_month
    for _ in range(count):
        labels.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return labels


def generate_events(
    months: int = 24,
    seed: int = 34970,
    start_year: int = 2024,
    start_month: int = 1,
    drift_category: str = "unstable-approach",
    drift_from_month: int = 18,
    drift_factor: float = 1.8,
) -> tuple[list[SafetyEvent], list[MonthFlights]]:
    """Generate synthetic monthly safety events.

    A planted, documented drift raises the rate of ``drift_category``
    from ``drift_from_month`` (0-based) so trend detection has a real
    signal to find. Everything else follows the stated baselines with
    Poisson-style noise from a seeded generator, so runs are repeatable.
    """
    rng = random.Random(seed)
    labels = month_labels(start_year, start_month, months)
    events: list[SafetyEvent] = []
    exposure: list[MonthFlights] = []
    for index, label in enumerate(labels):
        # Seasonal flying volume: summer peak, winter dip.
        seasonal = 1.0 + 0.12 * _season_factor(index)
        flights = int(round(95000 * seasonal))
        exposure.append(MonthFlights(month=label, flights=flights))
        for category in CATEGORIES:
            rate = BASELINE_RATES[category]
            if category == drift_category and index >= drift_from_month:
                rate *= drift_factor
            # Poisson draw via Knuth's method on the expected count.
            expected = rate * flights / 10000.0
            count = _poisson(rng, expected)
            weight = SEVERITY_WEIGHTS[category]
            for _ in range(count):
                severity = max(1, min(5, weight + rng.choice((-1, 0, 0, 1))))
                events.append(
                    SafetyEvent(
                        month=label,
                        category=category,
                        severity=severity,
                        flights=flights,
                    )
                )
    return events, exposure


def _season_factor(index: int) -> float:
    """Rough summer-peak seasonality by month index (0 = January)."""
    month_of_year = index % 12
    return (1, 0, 0, 0, 1, 2, 2, 2, 1, 0, -1, -1)[month_of_year]


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth Poisson sampler; fine for the small lambdas used here."""
    import math

    limit = math.exp(-lam)
    count = 0
    product = 1.0
    while product > limit:
        product *= rng.random()
        count += 1
    return count - 1


def monthly_counts(
    events: list[SafetyEvent], exposure: list[MonthFlights]
) -> dict[str, dict[str, int]]:
    """Event counts per month per category."""
    counts: dict[str, dict[str, int]] = {
        m.month: {c: 0 for c in CATEGORIES} for m in exposure
    }
    for event in events:
        counts[event.month][event.category] += 1
    return counts
