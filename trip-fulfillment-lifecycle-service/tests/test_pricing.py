from datetime import datetime, timedelta

import pytest

from fulfillment.pricing import quote_fare


def test_base_distance_time_math():
    q = quote_fare(10.0, 20.0)
    assert q.base_cents == 250
    assert q.distance_cents == 1200
    assert q.time_cents == 500
    assert q.total_cents == 1950


def test_surge_multiplies_subtotal():
    q = quote_fare(10.0, 20.0, surge_multiplier=1.5)
    assert q.total_cents == 2925


def test_minimum_fare_floor():
    q = quote_fare(0.1, 1.0)
    assert q.total_cents == 500  # minimum, not the raw subtotal


def test_quote_expires_after_five_minutes():
    now = datetime(2026, 11, 27, 12, 0, 0)
    q = quote_fare(5.0, 10.0, now=now)
    assert not q.is_expired(now + timedelta(minutes=4))
    assert q.is_expired(now + timedelta(minutes=5))


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        quote_fare(-1.0, 10.0)
    with pytest.raises(ValueError):
        quote_fare(1.0, -5.0)
    with pytest.raises(ValueError):
        quote_fare(1.0, 5.0, surge_multiplier=0.5)
