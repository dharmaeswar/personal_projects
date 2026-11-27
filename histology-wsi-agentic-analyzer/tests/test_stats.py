import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsi_agent import stats  # noqa: E402


def test_wilson_interval_contains_estimate():
    lo, hi = stats.wilson_interval(60, 100)
    assert 0.0 <= lo <= 0.6 <= hi <= 1.0
    assert lo < hi


def test_wilson_interval_empty_trials():
    assert stats.wilson_interval(0, 0) == (0.0, 0.0)


def test_welch_finds_seeded_difference():
    treated = [58.0, 61.0, 57.0, 60.0, 59.0, 62.0]
    control = [44.0, 43.0, 45.0, 42.0, 46.0, 44.0]
    result = stats.welch_t_test(treated, control)
    assert result["mean_a"] > result["mean_b"]
    assert result["p_value"] < 0.05
    assert result["cohens_d"] > 1.0


def test_welch_identical_groups_not_significant():
    group = [10.0, 11.0, 9.0, 10.5, 10.0]
    result = stats.welch_t_test(group, list(group))
    assert result["t"] == 0.0
    assert result["p_value"] == 1.0


def test_welch_empty_group_raises():
    try:
        stats.welch_t_test([], [1.0, 2.0])
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty group")
