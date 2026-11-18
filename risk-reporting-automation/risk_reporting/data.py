"""Synthetic positions, limits, and liquidity data.

All data is generated locally with a fixed seed. Nothing here is real
market data, a real portfolio, or data from any employer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

AS_OF_DATE = "2026-11-18"

DESKS = [
    "Rates",
    "FX",
    "Credit",
    "Secured Funding",
    "Liquidity Management",
]

RISK_TYPES = ["VaR", "DV01", "Concentration", "Liquidity Gap"]

# (desk, risk_type) pairs deliberately pushed over their limit by the
# planted large positions below. The toolkit must flag both as breaches.
PLANTED_BREACH_GROUPS = {
    ("Rates", "VaR"),
    ("FX", "Concentration"),
}

# Fixed large exposures that push the planted groups over their limits.
PLANTED_POSITIONS = [
    # trade_id, desk, risk_type, exposure_usd, notional_usd, currency
    ("TRD-9001", "Rates", "VaR", 9_400_000.0, 940_000_000.0, "USD"),
    ("TRD-9002", "Rates", "VaR", 8_700_000.0, 870_000_000.0, "USD"),
    ("TRD-9003", "FX", "Concentration", 6_200_000.0, 310_000_000.0, "EUR"),
    ("TRD-9004", "FX", "Concentration", 5_900_000.0, 295_000_000.0, "USD"),
]

# Rows that fail validation on purpose: a negative exposure and a desk
# with no limit defined. They must land in the exception queue, not in
# the limit aggregates.
PLANTED_BAD_ROWS = [
    ("TRD-9101", "Rates", "VaR", -250_000.0, 25_000_000.0, "USD"),
    ("TRD-9102", "Unknown Desk", "VaR", 1_000_000.0, 100_000_000.0, "USD"),
]


@dataclass(frozen=True)
class Position:
    trade_id: str
    desk: str
    risk_type: str
    exposure_usd: float
    notional_usd: float
    currency: str
    as_of_date: str = AS_OF_DATE


@dataclass(frozen=True)
class Limit:
    desk: str
    risk_type: str
    limit_usd: float
    warning_pct: float = 0.90  # utilisation at/above this is a warning


def generate_limits() -> list[Limit]:
    """One limit per desk x risk type, fixed values (no randomness)."""
    base = {
        "VaR": 15_000_000.0,
        "DV01": 12_000_000.0,
        "Concentration": 10_000_000.0,
        "Liquidity Gap": 20_000_000.0,
    }
    desk_factor = {
        "Rates": 1.0,
        "FX": 0.8,
        "Credit": 1.2,
        "Secured Funding": 0.9,
        "Liquidity Management": 1.1,
    }
    return [
        Limit(desk, risk_type, round(base[risk_type] * desk_factor[desk], 2))
        for desk in DESKS
        for risk_type in RISK_TYPES
    ]


def generate_positions(seed: int = 42, n_random: int = 120) -> list[Position]:
    """120 seeded random positions plus planted breach/bad rows."""
    rng = random.Random(seed)
    positions: list[Position] = []
    for i in range(n_random):
        desk = rng.choice(DESKS)
        risk_type = rng.choice(RISK_TYPES)
        # Keep ordinary exposures modest so only the planted groups breach.
        exposure = round(rng.uniform(20_000.0, 220_000.0), 2)
        positions.append(
            Position(
                trade_id=f"TRD-{1000 + i}",
                desk=desk,
                risk_type=risk_type,
                exposure_usd=exposure,
                notional_usd=round(exposure * rng.uniform(40.0, 120.0), 2),
                currency=rng.choice(["USD", "EUR", "GBP"]),
            )
        )
    for trade_id, desk, risk_type, exposure, notional, ccy in PLANTED_POSITIONS:
        positions.append(Position(trade_id, desk, risk_type, exposure, notional, ccy))
    for trade_id, desk, risk_type, exposure, notional, ccy in PLANTED_BAD_ROWS:
        positions.append(Position(trade_id, desk, risk_type, exposure, notional, ccy))
    return positions


def generate_all(seed: int = 42) -> dict:
    return {
        "positions": generate_positions(seed=seed),
        "limits": generate_limits(),
        "as_of_date": AS_OF_DATE,
    }
