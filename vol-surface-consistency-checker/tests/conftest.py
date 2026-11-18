"""Shared fixtures: a small clean surface built from the same total-variance
model as the sample data, plus the shipped sample surface itself."""

from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vol_surface_checker.black_scholes import bs_price
from vol_surface_checker.surface import Quote, Surface, load_surface

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample_surface.csv"

SPOT = 100.0
RATE = 0.03
TS = datetime(2024, 2, 15, 9, 30, 0)


def model_vol(strike: float, expiry: float) -> float:
    forward = SPOT * math.exp(RATE * expiry)
    k = math.log(strike / forward)
    w = (0.04 + 0.02 * expiry) * (1.0 + 0.3 * k * k)
    return math.sqrt(w / expiry)


def make_quote(strike: float, expiry: float, vol: float | None = None, **over) -> Quote:
    vol = model_vol(strike, expiry) if vol is None else vol
    fields = dict(
        timestamp=TS,
        expiry=expiry,
        strike=strike,
        spot=SPOT,
        rate=RATE,
        option_type="call",
        market_price=bs_price(SPOT, strike, expiry, RATE, vol),
        implied_vol=vol,
    )
    fields.update(over)
    return Quote(**fields)


@pytest.fixture()
def clean_surface() -> Surface:
    quotes = [
        make_quote(strike, expiry)
        for expiry in (0.25, 0.5, 1.0, 2.0)
        for strike in (80.0, 90.0, 100.0, 110.0, 120.0)
    ]
    return Surface(quotes=quotes)


@pytest.fixture()
def sample_surface() -> Surface:
    return load_surface(SAMPLE_CSV)
