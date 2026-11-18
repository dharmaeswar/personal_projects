import math

from acceptance_eval import generate_series, to_values
from acceptance_eval.series import START
from datetime import timedelta


def test_series_length_and_dates():
    s = generate_series(n_days=30, seed=7)
    assert len(s) == 30
    assert s[0][0] == START.isoformat()
    assert s[1][0] == (START + timedelta(days=1)).isoformat()


def test_series_deterministic():
    assert generate_series(seed=7) == generate_series(seed=7)
    assert generate_series(seed=7) != generate_series(seed=8)


def test_series_rates_in_range():
    for _, rate in generate_series(n_days=365, seed=7):
        assert 0.50 <= rate <= 0.99


def test_series_has_weekly_seasonality():
    vals = to_values(generate_series(n_days=56, seed=7))
    # Average of Mondays (index 0,7,14...) vs Saturdays (5,12,19...):
    # weekend dip from the sine term should show up on average.
    mondays = [vals[i] for i in range(0, 56, 7)]
    saturdays = [vals[i] for i in range(5, 56, 7)]
    assert sum(mondays) / len(mondays) > sum(saturdays) / len(saturdays)


def test_holiday_dip_visible():
    vals = to_values(generate_series(n_days=365, seed=7))
    dip = sum(vals[60:67]) / 7
    before = sum(vals[53:60]) / 7
    assert dip < before - 0.02
