import pytest

from eval_platform.compare import (classify_failure, compare_rates,
                                     mean_interval, wilson_interval)


def test_wilson_interval_sane():
    lo, hi = wilson_interval(10, 100)
    assert 0.05 < lo < 0.10 < hi < 0.20
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_mean_interval_contains_mean():
    lo, hi = mean_interval([1, 2, 3, 4, 5])
    assert lo < 3.0 < hi
    assert mean_interval([7]) == (7, 7)


def test_clear_regression_detected_lower_is_better():
    c = compare_rates(50, 1000, 120, 1000, "intervention_rate", False)
    assert c.verdict == "regression"
    assert c.delta == pytest.approx(0.07)


def test_clear_improvement_detected_higher_is_better():
    c = compare_rates(800, 1000, 900, 1000, "mission_completion", True)
    assert c.verdict == "improvement"


def test_overlapping_intervals_inconclusive():
    c = compare_rates(12, 1000, 9, 1000, "intervention_rate", False)
    assert c.verdict == "inconclusive"
    assert c.delta == pytest.approx(-0.003)


def test_small_sample_not_comparable():
    c = compare_rates(1, 10, 0, 10, "m", True)
    assert c.verdict == "not_comparable"


def test_classify_failure_labels():
    assert classify_failure(coverage=1.0, missing_inputs=0, failed_jobs=0,
                            total_jobs=10, metric_changed=True).startswith("model:")
    assert classify_failure(coverage=0.5, missing_inputs=5, failed_jobs=0,
                            total_jobs=10, metric_changed=True).startswith("data:")
    assert classify_failure(coverage=1.0, missing_inputs=0, failed_jobs=3,
                            total_jobs=10, metric_changed=True).startswith("infrastructure:")
    assert classify_failure(coverage=1.0, missing_inputs=0, failed_jobs=0,
                            total_jobs=10, metric_changed=False).startswith("no_failure:")
