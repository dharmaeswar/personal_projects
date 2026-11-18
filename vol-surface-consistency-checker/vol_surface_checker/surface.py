"""Loading and representing an implied-volatility surface from CSV.

Input format (one option quote per row)::

    timestamp,expiry,strike,spot,rate,option_type,market_price,implied_vol

* ``timestamp``    -- ISO-8601 quote time, e.g. ``2024-02-15T09:30:00``
* ``expiry``       -- time to expiry in years (e.g. ``0.5``)
* ``strike``       -- strike price
* ``spot``         -- spot price of the underlying at quote time
* ``rate``         -- continuously compounded risk-free rate
* ``option_type``  -- ``call`` or ``put``
* ``market_price`` -- quoted market price of the option
* ``implied_vol``  -- quoted implied volatility (annualised, e.g. ``0.24``)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REQUIRED_COLUMNS = (
    "timestamp",
    "expiry",
    "strike",
    "spot",
    "rate",
    "option_type",
    "market_price",
    "implied_vol",
)


@dataclass(frozen=True)
class Quote:
    """A single option quote on the surface."""

    timestamp: datetime
    expiry: float
    strike: float
    spot: float
    rate: float
    option_type: str
    market_price: float
    implied_vol: float

    @property
    def total_variance(self) -> float:
        """Total implied variance w = sigma^2 * T."""
        return self.implied_vol**2 * self.expiry

    @property
    def log_moneyness(self) -> float:
        """Log moneyness log(K / F) against the forward."""
        import math

        forward = self.spot * math.exp(self.rate * self.expiry)
        return math.log(self.strike / forward)


@dataclass
class Surface:
    """A collection of quotes forming one implied-vol surface."""

    quotes: list[Quote] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.quotes)

    @property
    def expiries(self) -> list[float]:
        return sorted({q.expiry for q in self.quotes})

    @property
    def as_of(self) -> datetime:
        """Reference time for staleness: the newest quote timestamp."""
        return max(q.timestamp for q in self.quotes)

    def by_expiry(self, expiry: float) -> list[Quote]:
        """Quotes at one expiry, sorted by strike (calls only by default use)."""
        return sorted(
            (q for q in self.quotes if q.expiry == expiry), key=lambda q: q.strike
        )

    def by_strike(self, strike: float) -> list[Quote]:
        """Quotes at one strike across expiries, sorted by expiry."""
        return sorted(
            (q for q in self.quotes if q.strike == strike), key=lambda q: q.expiry
        )


def _parse_row(row: dict, line_no: int) -> Quote:
    try:
        return Quote(
            timestamp=datetime.fromisoformat(row["timestamp"].strip()),
            expiry=float(row["expiry"]),
            strike=float(row["strike"]),
            spot=float(row["spot"]),
            rate=float(row["rate"]),
            option_type=row["option_type"].strip().lower(),
            market_price=float(row["market_price"]),
            implied_vol=float(row["implied_vol"]),
        )
    except (ValueError, AttributeError, KeyError) as exc:
        raise ValueError(f"bad row at line {line_no}: {row!r} ({exc})") from exc


def load_surface(path: str | Path) -> Surface:
    """Load a surface CSV into a :class:`Surface`.

    Raises ``ValueError`` on missing columns or malformed rows so a bad
    input file fails loudly instead of silently producing wrong checks.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing required columns: {missing}")
        quotes = [_parse_row(row, i + 2) for i, row in enumerate(reader)]
    if not quotes:
        raise ValueError(f"{path}: no quotes found")
    return Surface(quotes=quotes)
