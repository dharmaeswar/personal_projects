import pytest

from event_intel.scoring import CRITICAL_THRESHOLD, WATCH_THRESHOLD, band, score_event


def test_perfect_signal_scores_near_max():
    score = score_event(1.0, 1.0, 10, 0)
    assert score > 95
    assert band(score) == "critical"


def test_weak_signal_is_info():
    score = score_event(0.2, 0.1, 0, 0)
    assert score < WATCH_THRESHOLD
    assert band(score) == "info"


def test_mid_signal_is_watch():
    score = score_event(0.6, 0.5, 1, 0)
    assert WATCH_THRESHOLD <= score < CRITICAL_THRESHOLD
    assert band(score) == "watch"


def test_corroboration_raises_score():
    low = score_event(0.7, 0.6, 0, 0)
    high = score_event(0.7, 0.6, 5, 0)
    assert high > low


def test_recency_decay_lowers_score():
    fresh = score_event(0.9, 0.8, 3, 0)
    stale = score_event(0.9, 0.8, 3, 7200)
    assert stale < fresh
    assert stale < fresh * 0.2


def test_score_is_bounded():
    assert 0.0 <= score_event(1.0, 1.0, 100, 0) <= 100.0
    assert 0.0 <= score_event(0.0, 0.0, 0, 100000) <= 100.0


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        score_event(1.5, 0.5, 0, 0)
    with pytest.raises(ValueError):
        score_event(0.5, -0.1, 0, 0)
    with pytest.raises(ValueError):
        score_event(0.5, 0.5, -1, 0)
    with pytest.raises(ValueError):
        score_event(0.5, 0.5, 0, -5)


def test_band_boundaries():
    assert band(70.0) == "critical"
    assert band(69.99) == "watch"
    assert band(40.0) == "watch"
    assert band(39.99) == "info"
