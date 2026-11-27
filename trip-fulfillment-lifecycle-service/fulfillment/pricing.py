"""Fare quotes: base + distance + time, with dynamics (surge).

The pricing piece of the fulfillment flow. A quote is computed once at
request time, is valid for a short window, and is frozen onto the trip so
the price the rider saw is the price that is charged. All amounts are in
cents; all inputs here are synthetic examples, not real fares.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

QUOTE_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class FareQuote:
    base_cents: int
    distance_cents: int
    time_cents: int
    surge_multiplier: float
    total_cents: int
    minimum_cents: int
    currency: str = "USD"
    expires_at: datetime | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or _utcnow()) >= self.expires_at


def quote_fare(
    distance_km: float,
    duration_min: float,
    *,
    base_cents: int = 250,
    per_km_cents: int = 120,
    per_min_cents: int = 25,
    surge_multiplier: float = 1.0,
    minimum_cents: int = 500,
    now: datetime | None = None,
) -> FareQuote:
    """Price a trip from distance, duration and the dynamics multiplier.

    Raises ValueError on negative inputs or a surge multiplier below 1.
    The total is the surge-adjusted subtotal, floored at the minimum fare.
    """
    if distance_km < 0 or duration_min < 0:
        raise ValueError("distance and duration must be non-negative")
    if surge_multiplier < 1.0:
        raise ValueError("surge multiplier cannot be below 1.0")
    distance_cents = round(distance_km * per_km_cents)
    time_cents = round(duration_min * per_min_cents)
    subtotal = base_cents + distance_cents + time_cents
    total = max(minimum_cents, round(subtotal * surge_multiplier))
    moment = now or _utcnow()
    return FareQuote(
        base_cents=base_cents,
        distance_cents=distance_cents,
        time_cents=time_cents,
        surge_multiplier=surge_multiplier,
        total_cents=total,
        minimum_cents=minimum_cents,
        expires_at=moment + QUOTE_TTL,
    )
