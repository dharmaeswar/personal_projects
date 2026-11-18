"""Tests for the calendar, butterfly, monotonicity, stale and smile checks."""

from datetime import datetime, timedelta

import pytest

from vol_surface_checker.black_scholes import bs_price
from vol_surface_checker.checks import (
    check_butterfly,
    check_calendar,
    check_monotonicity,
    check_stale,
    smile_rms_by_expiry,
    smile_rms_error,
)
from vol_surface_checker.surface import Quote, Surface

from conftest import RATE, SPOT, TS, make_quote


# --- calendar -------------------------------------------------------------

def test_calendar_passes_on_clean_surface(clean_surface):
    assert check_calendar(clean_surface) == []


def test_calendar_flags_decreasing_total_variance():
    # w(0.25) = 0.30^2 * 0.25 = 0.0225 > w(1.0) = 0.10^2 * 1.0 = 0.0100.
    quotes = [
        make_quote(100.0, 0.25, vol=0.30),
        make_quote(100.0, 1.0, vol=0.10),
    ]
    violations = check_calendar(Surface(quotes=quotes))
    assert len(violations) == 1
    assert violations[0].check == "calendar_arbitrage"
    assert violations[0].expiry == 1.0


# --- butterfly ------------------------------------------------------------

def test_butterfly_passes_on_clean_surface(clean_surface):
    assert check_butterfly(clean_surface) == []


def test_butterfly_flags_bumped_middle_price(clean_surface):
    quotes = []
    for q in clean_surface.quotes:
        if q.expiry == 1.0 and q.strike == 100.0:
            q = make_quote(
                q.strike,
                q.expiry,
                vol=q.implied_vol,
                market_price=q.market_price + 2.0,
            )
        quotes.append(q)
    violations = check_butterfly(Surface(quotes=quotes))
    assert violations
    assert all(v.check == "butterfly_arbitrage" for v in violations)
    assert any(v.strike == 100.0 and v.expiry == 1.0 for v in violations)


# --- monotonicity ----------------------------------------------------------

def test_monotonicity_passes_on_clean_surface(clean_surface):
    assert check_monotonicity(clean_surface) == []


def test_monotonicity_flags_rising_call_price():
    cheap = make_quote(100.0, 1.0, vol=0.20)
    pricey = make_quote(
        110.0, 1.0, vol=0.20, market_price=cheap.market_price + 1.0
    )
    violations = check_monotonicity(Surface(quotes=[cheap, pricey]))
    assert len(violations) == 1
    assert violations[0].check == "strike_monotonicity"
    assert violations[0].strike == 110.0


# --- stale quotes -----------------------------------------------------------

def test_stale_flags_old_quote(clean_surface):
    old = make_quote(
        90.0, 0.5, timestamp=TS - timedelta(days=10)
    )
    quotes = [old if (q.strike, q.expiry) == (90.0, 0.5) else q
              for q in clean_surface.quotes]
    violations = check_stale(Surface(quotes=quotes), max_age_hours=24.0)
    assert len(violations) == 1
    assert violations[0].check == "stale_quote"
    assert violations[0].strike == 90.0


def test_stale_passes_when_max_age_is_generous(clean_surface):
    old = make_quote(90.0, 0.5, timestamp=TS - timedelta(days=10))
    quotes = [old if (q.strike, q.expiry) == (90.0, 0.5) else q
              for q in clean_surface.quotes]
    assert check_stale(Surface(quotes=quotes), max_age_hours=24.0 * 30) == []


def test_stale_passes_on_clean_surface(clean_surface):
    assert check_stale(clean_surface, max_age_hours=24.0) == []


# --- RMS smile error ---------------------------------------------------------

def _smile_quotes(vol_fn, expiry=1.0):
    import math

    quotes = []
    for strike in (80.0, 90.0, 100.0, 110.0, 120.0):
        forward = SPOT * math.exp(RATE * expiry)
        k = math.log(strike / forward)
        vol = vol_fn(k)
        quotes.append(
            Quote(
                timestamp=TS,
                expiry=expiry,
                strike=strike,
                spot=SPOT,
                rate=RATE,
                option_type="call",
                market_price=bs_price(SPOT, strike, expiry, RATE, vol),
                implied_vol=vol,
            )
        )
    return quotes


def test_smile_rms_is_zero_for_exact_quadratic_smile():
    quotes = _smile_quotes(lambda k: 0.22 + 0.05 * k + 0.4 * k * k)
    assert smile_rms_error(quotes) == pytest.approx(0.0, abs=1e-10)


def test_smile_rms_grows_with_off_market_quote():
    quotes = _smile_quotes(lambda k: 0.22 + 0.05 * k + 0.4 * k * k)
    bumped = [
        make_quote(q.strike, q.expiry, vol=q.implied_vol + 0.05)
        if q.strike == 100.0
        else q
        for q in quotes
    ]
    assert smile_rms_error(bumped) > 0.01


def test_smile_rms_by_expiry_covers_all_expiries(clean_surface):
    rms = smile_rms_by_expiry(clean_surface)
    assert set(rms) == {0.25, 0.5, 1.0, 2.0}
    assert all(v >= 0.0 for v in rms.values())
